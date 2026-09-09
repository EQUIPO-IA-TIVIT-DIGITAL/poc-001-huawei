"""
Repositorio de Videos de Seguridad con SQLAlchemy (PostgreSQL/SQLite)
Persistencia para videos largos de cámaras de seguridad (12h+)
"""

from typing import List, Optional, Dict, Any
from threading import Lock, RLock
import logging
from datetime import datetime

from cachetools import TTLCache

from domain.entities import SecurityVideo, EventoSeguridad, EstadoSecurityVideo
from infrastructure.db.session import SessionLocal
from infrastructure.db.models import SecurityVideoModel, SecurityEventModel

logger = logging.getLogger(__name__)


class SecurityVideoRepository:
    """
    Repositorio de videos de seguridad con persistencia local (PostgreSQL/SQLAlchemy).

    Tablas:
    - security_videos: Registro de video de seguridad (dict completo en `result`)
    - security_events: Eventos de un video (dict completo en `metadata_json`)
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        """Implementación del patrón Singleton"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Inicializa el repositorio con conexión a SQLAlchemy"""
        if self._initialized:
            return

        # Cache con TTL para evitar crecimiento indefinido
        # Videos: máximo 100 items, expiran en 1 hora
        # Eventos: máximo 1000 items, expiran en 30 minutos
        self._cache: TTLCache = TTLCache(maxsize=100, ttl=3600)
        self._eventos_cache: TTLCache = TTLCache(maxsize=1000, ttl=1800)
        self._lock_repo = RLock()  # RLock permite reentrada (mismo hilo)
        self._initialized = True

        logger.info("✅ SecurityVideoRepository conectado a SQLAlchemy (PostgreSQL/SQLite)")

    def is_available(self) -> bool:
        """Verifica si la base de datos local está disponible"""
        return True

    # ========== OPERACIONES DE SECURITY_VIDEOS ==========

    def guardar_video(self, video: SecurityVideo) -> Optional[SecurityVideo]:
        """Guarda un video de seguridad"""
        with self._lock_repo:
            # Validar que el ID no esté vacío
            if not video.id or not video.id.strip():
                logger.error("❌ Intentando guardar video con ID vacío")
                raise ValueError("El ID del video no puede estar vacío")

            # Persistir en PostgreSQL/SQLite
            try:
                db = SessionLocal()
                try:
                    m = db.get(SecurityVideoModel, video.id)
                    if m is None:
                        m = SecurityVideoModel(id=video.id)
                        db.add(m)
                    m.usuario = video.usuario
                    m.estado = video.estado.value
                    m.s3_uri = video.storage_path
                    m.result = self._video_to_dict(video)
                    db.commit()
                    self._cache[video.id] = video
                    logger.info(f"✅ SecurityVideo guardado: {video.id}")
                except Exception as e:
                    db.rollback()
                    raise e
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"❌ Error guardando security_video: {e}")
                return None

            return video

    def obtener_video(self, video_id: str) -> Optional[SecurityVideo]:
        """Obtiene un video de seguridad por ID"""
        with self._lock_repo:
            # Buscar en cache
            if video_id in self._cache:
                return self._cache[video_id]

            # Buscar en PostgreSQL/SQLite
            try:
                db = SessionLocal()
                try:
                    m = db.get(SecurityVideoModel, video_id)
                    if m:
                        video = self._model_to_video(m)
                        self._cache[video_id] = video
                        return video
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"❌ Error obteniendo security_video: {e}")

            return None

    def obtener_por_usuario(self, usuario: str, limit: int = 50) -> List[SecurityVideo]:
        """Obtiene videos de seguridad de un usuario"""
        try:
            db = SessionLocal()
            try:
                rows = (
                    db.query(SecurityVideoModel)
                    .filter(SecurityVideoModel.usuario == usuario)
                    .order_by(SecurityVideoModel.created_at.desc())
                    .limit(limit)
                    .all()
                )
                videos = []
                for m in rows:
                    video = self._model_to_video(m)
                    self._cache[video.id] = video
                    videos.append(video)
                return videos
            finally:
                db.close()
        except Exception as e:
            logger.error(f"❌ Error obteniendo videos por usuario: {e}")

        # Fallback a cache
        with self._lock_repo:
            return [v for v in self._cache.values() if v.usuario == usuario][:limit]

    def obtener_por_estado(self, estado: EstadoSecurityVideo, limit: int = 50) -> List[SecurityVideo]:
        """Obtiene videos por estado"""
        try:
            db = SessionLocal()
            try:
                rows = (
                    db.query(SecurityVideoModel)
                    .filter(SecurityVideoModel.estado == estado.value)
                    .limit(limit)
                    .all()
                )
                videos = []
                for m in rows:
                    video = self._model_to_video(m)
                    self._cache[video.id] = video
                    videos.append(video)
                return videos
            finally:
                db.close()
        except Exception as e:
            logger.error(f"❌ Error obteniendo videos por estado: {e}")

        # Fallback a cache
        with self._lock_repo:
            return [v for v in self._cache.values() if v.estado == estado][:limit]

    def actualizar_estado(self, video_id: str, nuevo_estado: EstadoSecurityVideo) -> bool:
        """Actualiza el estado de un video"""
        video = self.obtener_video(video_id)
        if not video:
            return False

        video.actualizar_estado(nuevo_estado)
        return self.guardar_video(video) is not None

    def eliminar_video(self, video_id: str) -> bool:
        """Elimina un video de seguridad"""
        with self._lock_repo:
            # Eliminar de cache
            if video_id in self._cache:
                del self._cache[video_id]

            try:
                db = SessionLocal()
                try:
                    # Eliminar eventos asociados
                    db.query(SecurityEventModel).filter(SecurityEventModel.video_id == video_id).delete()

                    # Eliminar video
                    m = db.get(SecurityVideoModel, video_id)
                    if m:
                        db.delete(m)
                    db.commit()
                    logger.info(f"✅ SecurityVideo eliminado: {video_id}")
                    return True
                except Exception as e:
                    db.rollback()
                    logger.error(f"❌ Error eliminando security_video: {e}")
                    return False
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"❌ Error eliminando security_video: {e}")
                return False

    # ========== OPERACIONES DE EVENTOS ==========

    def guardar_evento(self, evento: EventoSeguridad) -> Optional[EventoSeguridad]:
        """Guarda un evento de seguridad (individual - NO actualiza el video)"""
        with self._lock_repo:
            # Validar IDs no vacíos
            if not evento.id or not evento.id.strip():
                logger.error("❌ Intentando guardar evento con ID vacío")
                raise ValueError("El ID del evento no puede estar vacío")
            if not evento.security_video_id or not evento.security_video_id.strip():
                logger.error("❌ Intentando guardar evento con security_video_id vacío")
                raise ValueError("El security_video_id del evento no puede estar vacío")

            # Persistir en PostgreSQL/SQLite
            try:
                db = SessionLocal()
                try:
                    m = db.get(SecurityEventModel, evento.id)
                    if m is None:
                        m = SecurityEventModel(id=evento.id)
                        db.add(m)
                    m.video_id = evento.security_video_id
                    m.timestamp = float(evento.timestamp_inicio)
                    m.event_type = (evento.acciones_detectadas[0] if evento.acciones_detectadas else 'detection')[:64]
                    m.description = evento.descripcion
                    m.metadata_json = self._evento_to_dict(evento)
                    db.commit()
                    self._eventos_cache[evento.id] = evento

                    logger.debug(f"✅ Evento guardado: {evento.id}")
                except Exception as e:
                    db.rollback()
                    raise e
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"❌ Error guardando evento: {e}")
                return None

            return evento

    def guardar_eventos_batch(self, video_id: str, eventos: List[EventoSeguridad]) -> int:
        """
        Guarda múltiples eventos en batch (optimizado para rendimiento).
        Actualiza el video una sola vez al final.

        Retorna: número de eventos guardados exitosamente
        """
        if not eventos:
            return 0

        guardados = 0

        with self._lock_repo:
            # Validar video_id
            if not video_id or not video_id.strip():
                logger.error("❌ video_id vacío en batch")
                raise ValueError("El video_id no puede estar vacío")

            try:
                db = SessionLocal()
                try:
                    for evento in eventos:
                        # Validar cada evento
                        if not evento.id or not evento.id.strip():
                            logger.warning("⚠️ Saltando evento con ID vacío")
                            continue

                        # Agregar a cache
                        self._eventos_cache[evento.id] = evento

                        m = db.get(SecurityEventModel, evento.id)
                        if m is None:
                            m = SecurityEventModel(id=evento.id)
                            db.add(m)
                        m.video_id = video_id
                        m.timestamp = float(evento.timestamp_inicio)
                        m.event_type = (evento.acciones_detectadas[0] if evento.acciones_detectadas else 'detection')[:64]
                        m.description = evento.descripcion
                        m.metadata_json = self._evento_to_dict(evento)
                        guardados += 1

                    db.commit()
                    logger.info(f"✅ Batch: {guardados} eventos guardados")

                    # ✅ Actualizar el video UNA SOLA VEZ al final
                    video = self.obtener_video(video_id)
                    if video:
                        for evento in eventos:
                            if evento.id and evento.id.strip():
                                video.agregar_evento(evento.id)
                        self.guardar_video(video)
                        logger.info(f"✅ Video actualizado con {len(eventos)} eventos")

                    logger.info(f"✅ Batch completo: {guardados} eventos guardados")

                except Exception as e:
                    db.rollback()
                    logger.error(f"❌ Error guardando eventos en batch: {e}", exc_info=True)
                    raise
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"❌ Error guardando eventos en batch: {e}", exc_info=True)
                raise

        return guardados

    def obtener_evento(self, video_id: str, evento_id: str) -> Optional[EventoSeguridad]:
        """Obtiene un evento específico"""
        cache_key = f"{video_id}_{evento_id}"

        # Buscar en cache
        if cache_key in self._eventos_cache:
            return self._eventos_cache[cache_key]

        # Buscar en PostgreSQL/SQLite
        try:
            db = SessionLocal()
            try:
                m = db.get(SecurityEventModel, evento_id)
                if m and m.video_id == video_id:
                    evento = self._model_to_evento(m)
                    self._eventos_cache[cache_key] = evento
                    return evento
            finally:
                db.close()
        except Exception as e:
            logger.error(f"❌ Error obteniendo evento: {e}")

        return None

    def obtener_eventos_video(self, video_id: str) -> List[EventoSeguridad]:
        """Obtiene todos los eventos de un video"""
        try:
            db = SessionLocal()
            try:
                rows = (
                    db.query(SecurityEventModel)
                    .filter(SecurityEventModel.video_id == video_id)
                    .order_by(SecurityEventModel.timestamp)
                    .limit(5000)
                    .all()
                )
                eventos = []
                for m in rows:
                    evento = self._model_to_evento(m)
                    cache_key = f"{video_id}_{evento.id}"
                    self._eventos_cache[cache_key] = evento
                    eventos.append(evento)
                return eventos
            finally:
                db.close()
        except Exception as e:
            logger.error(f"❌ Error obteniendo eventos: {e}")
            return []

    def obtener_eventos_por_objeto(
        self, video_id: str, objeto: str
    ) -> List[EventoSeguridad]:
        """Obtiene eventos de un video filtrados por objeto detectado"""
        eventos = self.obtener_eventos_video(video_id)
        return [e for e in eventos if objeto in e.objetos_detectados]

    def obtener_eventos_por_accion(
        self, video_id: str, accion: str
    ) -> List[EventoSeguridad]:
        """Obtiene eventos de un video filtrados por acción detectada"""
        eventos = self.obtener_eventos_video(video_id)
        return [e for e in eventos if accion in e.acciones_detectadas]

    # ========== CONVERSIONES ==========

    @staticmethod
    def _sanitize_for_json(data):
        """Sanitiza datos recursivamente para JSON: claves de dict deben ser strings no vacíos"""
        if isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                key = str(k) if not isinstance(k, str) else k
                if not key:  # Clave vacía
                    key = '_empty_'
                sanitized[key] = SecurityVideoRepository._sanitize_for_json(v)
            return sanitized
        elif isinstance(data, list):
            return [SecurityVideoRepository._sanitize_for_json(item) for item in data]
        elif isinstance(data, set):
            return list(data)
        elif isinstance(data, (str, int, float, bool)) or data is None:
            return data
        else:
            return str(data)  # Fallback: convertir a string

    def _video_to_dict(self, video: SecurityVideo) -> Dict[str, Any]:
        """Convierte SecurityVideo a diccionario para almacenar en la columna result"""
        raw = {
            'id': video.id,
            'usuario': video.usuario,
            'nombre_camara': video.nombre_camara,
            'ubicacion': video.ubicacion,
            'fecha_grabacion': video.fecha_grabacion,
            'duracion_segundos': video.duracion_segundos,
            'storage_path': video.storage_path,
            'estado': video.estado.value,
            'metadata_tecnico': video.metadata_tecnico,
            'eventos': video.eventos,
            'estadisticas': video.estadisticas,
            'reporte_txt_url': video.reporte_txt_url or '',
            'reporte_pdf_url': video.reporte_pdf_url or '',
            'fecha_creacion': video.fecha_creacion or datetime.utcnow().isoformat(),
            'fecha_procesamiento': video.fecha_procesamiento,
            'tiempo_procesamiento_segundos': video.tiempo_procesamiento_segundos,
            'configuracion': video.configuracion,
        }
        return self._sanitize_for_json(raw)

    def _dict_to_video(self, data: Dict[str, Any]) -> SecurityVideo:
        """Convierte diccionario de la columna result a SecurityVideo (tolerante a campos faltantes)"""
        try:
            return SecurityVideo(
                id=data.get('id'),
                usuario=data.get('usuario', ''),
                nombre_camara=data.get('nombre_camara', ''),
                ubicacion=data.get('ubicacion', ''),
                fecha_grabacion=data.get('fecha_grabacion', ''),
                duracion_segundos=data.get('duracion_segundos', 0) or 0,
                storage_path=data.get('storage_path', ''),
                estado=EstadoSecurityVideo(data.get('estado', 'uploading')),
                metadata_tecnico=data.get('metadata_tecnico', {}) or {},
                eventos=data.get('eventos', []) or [],
                estadisticas=data.get('estadisticas', {}) or {},
                reporte_txt_url=data.get('reporte_txt_url', '') or '',
                reporte_pdf_url=data.get('reporte_pdf_url', '') or '',
                fecha_creacion=data.get('fecha_creacion'),
                fecha_procesamiento=data.get('fecha_procesamiento'),
                tiempo_procesamiento_segundos=data.get('tiempo_procesamiento_segundos'),
                configuracion=data.get('configuracion', {}) or {},
            )
        except Exception:
            return SecurityVideo(
                id=data['id'],
                usuario=data['usuario'],
                nombre_camara="",
                ubicacion="",
                fecha_grabacion="",
                duracion_segundos=0,
                storage_path="",
                estado=EstadoSecurityVideo.UPLOADING,
            )

    def _model_to_video(self, m: SecurityVideoModel) -> SecurityVideo:
        """Convierte SecurityVideoModel a SecurityVideo, priorizando el dict completo en result"""
        data = m.result or {}
        data = dict(data)
        data.setdefault('id', m.id)
        data.setdefault('usuario', m.usuario)
        if 'estado' not in data or not data.get('estado'):
            data['estado'] = m.estado or 'uploading'
        return self._dict_to_video(data)

    def _evento_to_dict(self, evento: EventoSeguridad) -> Dict[str, Any]:
        """Convierte EventoSeguridad a diccionario para almacenar en metadata_json"""
        return self._sanitize_for_json({
            'id': evento.id,
            'security_video_id': evento.security_video_id,
            'timestamp_inicio': evento.timestamp_inicio,
            'timestamp_fin': evento.timestamp_fin,
            'duracion': evento.duracion,
            'objetos_detectados': evento.objetos_detectados,
            'acciones_detectadas': evento.acciones_detectadas,
            'personas_count': evento.personas_count,
            'vehiculos_count': evento.vehiculos_count,
            'descripcion': evento.descripcion,
            'confianza': evento.confianza,
            'analisis_detallado': evento.analisis_detallado,
            'clip_url': getattr(evento, 'clip_url', ''),
            'frames_urls': getattr(evento, 'frames_urls', []),
            'metadata': getattr(evento, 'metadata', {}),
        })

    def _dict_to_evento(self, data: Dict[str, Any]) -> EventoSeguridad:
        """Convierte diccionario de metadata_json a EventoSeguridad (tolerante a campos faltantes)"""
        try:
            return EventoSeguridad(
                id=data.get('id'),
                security_video_id=data.get('security_video_id', ''),
                timestamp_inicio=data.get('timestamp_inicio', 0) or 0,
                timestamp_fin=data.get('timestamp_fin', 0) or 0,
                duracion=data.get('duracion', 1) or 1,
                objetos_detectados=data.get('objetos_detectados', []) or [],
                acciones_detectadas=data.get('acciones_detectadas', []) or [],
                personas_count=data.get('personas_count', 0) or 0,
                vehiculos_count=data.get('vehiculos_count', 0) or 0,
                descripcion=data.get('descripcion', '') or '',
                confianza=data.get('confianza', 0.0) or 0.0,
                analisis_detallado=data.get('analisis_detallado', {}) or {},
            )
        except Exception:
            evento = EventoSeguridad.__new__(EventoSeguridad)
            evento.id = data.get('id', '')
            evento.security_video_id = data.get('security_video_id', '')
            evento.timestamp_inicio = data.get('timestamp_inicio', 0) or 0
            evento.timestamp_fin = data.get('timestamp_fin', 0) or 0
            evento.duracion = data.get('duracion', 1) or 1
            evento.objetos_detectados = data.get('objetos_detectados', []) or []
            evento.acciones_detectadas = data.get('acciones_detectadas', []) or []
            evento.personas_count = data.get('personas_count', 0) or 0
            evento.vehiculos_count = data.get('vehiculos_count', 0) or 0
            evento.descripcion = data.get('descripcion', '') or ''
            evento.confianza = data.get('confianza', 0.0) or 0.0
            evento.analisis_detallado = data.get('analisis_detallado', {}) or {}
            evento.clip_url = data.get('clip_url', '') or ''
            evento.frames_urls = data.get('frames_urls', []) or []
            evento.metadata = data.get('metadata', {}) or {}
            return evento

    def _model_to_evento(self, m: SecurityEventModel) -> EventoSeguridad:
        """Convierte SecurityEventModel a EventoSeguridad, priorizando metadata_json"""
        data = m.metadata_json or {}
        data = dict(data)
        data.setdefault('id', m.id)
        data.setdefault('security_video_id', m.video_id)
        if not data.get('timestamp_inicio'):
            data['timestamp_inicio'] = m.timestamp if m.timestamp is not None else 0
        return self._dict_to_evento(data)
