"""
Repositorio de Videos de Seguridad con Firestore
Persistencia para videos largos de cámaras de seguridad (12h+)
"""

from typing import List, Optional, Dict, Any
from threading import Lock, RLock
import logging
from datetime import datetime

from cachetools import TTLCache

from domain.entities import SecurityVideo, EventoSeguridad, EstadoSecurityVideo

logger = logging.getLogger(__name__)


class SecurityVideoRepository:
    """
    Repositorio de videos de seguridad con persistencia en Firestore.

    Colecciones en Firestore:
    - security_videos/{video_id} → Documento de video de seguridad
    - security_videos/{video_id}/eventos/{evento_id} → Subcolección de eventos
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
        """Inicializa el repositorio con conexión a Firestore"""
        if self._initialized:
            return

        # Cache con TTL para evitar crecimiento indefinido
        # Videos: máximo 100 items, expiran en 1 hora
        # Eventos: máximo 1000 items, expiran en 30 minutos
        self._cache: TTLCache = TTLCache(maxsize=100, ttl=3600)
        self._eventos_cache: TTLCache = TTLCache(maxsize=1000, ttl=1800)
        self._lock_repo = RLock()  # RLock permite reentrada (mismo hilo)
        self._db = None
        self._initialized = True

        self._init_firestore()

    def _init_firestore(self):
        """Inicializa la conexión a Firestore"""
        try:
            from google.cloud import firestore
            import os

            credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            if credentials_path and os.path.exists(credentials_path):
                self._db = firestore.Client()
                logger.info("✅ SecurityVideoRepository conectado a Firestore")
            else:
                logger.warning("⚠️ Firestore credentials no encontradas - usando modo local")
        except Exception as e:
            logger.error(f"❌ Error conectando a Firestore: {e}")
            self._db = None

    def is_available(self) -> bool:
        """Verifica si Firestore está disponible"""
        return self._db is not None

    # ========== OPERACIONES DE SECURITY_VIDEOS ==========

    def guardar_video(self, video: SecurityVideo) -> SecurityVideo:
        """Guarda un video de seguridad"""
        with self._lock_repo:
            # Validar que el ID no esté vacío
            if not video.id or not video.id.strip():
                logger.error("❌ Intentando guardar video con ID vacío")
                raise ValueError("El ID del video no puede estar vacío")
            
            # Guardar en cache
            self._cache[video.id] = video

            # Persistir en Firestore
            if self.is_available():
                try:
                    video_dict = self._video_to_dict(video)
                    self._db.collection('security_videos').document(video.id).set(video_dict)
                    logger.info(f"✅ SecurityVideo guardado: {video.id}")
                except Exception as e:
                    logger.error(f"❌ Error guardando security_video: {e}")

            return video

    def obtener_video(self, video_id: str) -> Optional[SecurityVideo]:
        """Obtiene un video de seguridad por ID"""
        with self._lock_repo:
            # Buscar en cache
            if video_id in self._cache:
                return self._cache[video_id]

            # Buscar en Firestore
            if self.is_available():
                try:
                    doc = self._db.collection('security_videos').document(video_id).get()
                    if doc.exists:
                        video = self._dict_to_video(doc.to_dict())
                        self._cache[video_id] = video
                        return video
                except Exception as e:
                    logger.error(f"❌ Error obteniendo security_video: {e}")

            return None

    def obtener_por_usuario(self, usuario: str, limit: int = 50) -> List[SecurityVideo]:
        """Obtiene videos de seguridad de un usuario"""
        if self.is_available():
            try:
                from google.cloud import firestore
                from google.cloud.firestore_v1.base_query import FieldFilter
                docs = (
                    self._db.collection('security_videos')
                    .where(filter=FieldFilter('usuario', '==', usuario))
                    .order_by('fecha_creacion', direction=firestore.Query.DESCENDING)
                    .limit(limit)
                    .stream()
                )
                videos = []
                for doc in docs:
                    video = self._dict_to_video(doc.to_dict())
                    self._cache[video.id] = video
                    videos.append(video)
                return videos
            except Exception as e:
                logger.error(f"❌ Error obteniendo videos por usuario: {e}")

        # Fallback a cache
        with self._lock_repo:
            return [v for v in self._cache.values() if v.usuario == usuario][:limit]

    def obtener_por_estado(self, estado: EstadoSecurityVideo, limit: int = 50) -> List[SecurityVideo]:
        """Obtiene videos por estado"""
        if self.is_available():
            try:
                from google.cloud.firestore_v1.base_query import FieldFilter
                docs = (
                    self._db.collection('security_videos')
                    .where(filter=FieldFilter('estado', '==', estado.value))
                    .limit(limit)
                    .stream()
                )
                videos = []
                for doc in docs:
                    video = self._dict_to_video(doc.to_dict())
                    self._cache[video.id] = video
                    videos.append(video)
                return videos
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
        self.guardar_video(video)
        return True

    def eliminar_video(self, video_id: str) -> bool:
        """Elimina un video de seguridad"""
        with self._lock_repo:
            # Eliminar de cache
            if video_id in self._cache:
                del self._cache[video_id]

            # Eliminar de Firestore
            if self.is_available():
                try:
                    # Eliminar eventos asociados
                    eventos_ref = self._db.collection('security_videos').document(video_id).collection('eventos')
                    for evento_doc in eventos_ref.stream():
                        evento_doc.reference.delete()

                    # Eliminar video
                    self._db.collection('security_videos').document(video_id).delete()
                    logger.info(f"✅ SecurityVideo eliminado: {video_id}")
                    return True
                except Exception as e:
                    logger.error(f"❌ Error eliminando security_video: {e}")
                    return False

            return True

    # ========== OPERACIONES DE EVENTOS ==========

    def guardar_evento(self, evento: EventoSeguridad) -> EventoSeguridad:
        """Guarda un evento de seguridad (individual - NO actualiza el video)"""
        with self._lock_repo:
            # Validar IDs no vacíos
            if not evento.id or not evento.id.strip():
                logger.error("❌ Intentando guardar evento con ID vacío")
                raise ValueError("El ID del evento no puede estar vacío")
            if not evento.security_video_id or not evento.security_video_id.strip():
                logger.error("❌ Intentando guardar evento con security_video_id vacío")
                raise ValueError("El security_video_id del evento no puede estar vacío")
            
            # Guardar en cache
            self._eventos_cache[evento.id] = evento

            # Persistir en Firestore
            if self.is_available():
                try:
                    evento_dict = self._evento_to_dict(evento)
                    self._db.collection('security_videos').document(evento.security_video_id).collection('eventos').document(evento.id).set(evento_dict)
                    
                    # ✅ NO actualizar el video aquí (optimización)
                    # El video se actualiza una vez al final con guardar_eventos_batch
                    
                    logger.debug(f"✅ Evento guardado: {evento.id}")
                except Exception as e:
                    logger.error(f"❌ Error guardando evento: {e}")

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
            
            if self.is_available():
                try:
                    # Usar batch writes de Firestore (máx 500 por batch)
                    from google.cloud.firestore import WriteBatch
                    
                    batch_size = 500
                    for i in range(0, len(eventos), batch_size):
                        batch_eventos = eventos[i:i+batch_size]
                        batch: WriteBatch = self._db.batch()
                        
                        for evento in batch_eventos:
                            # Validar cada evento
                            if not evento.id or not evento.id.strip():
                                logger.warning(f"⚠️ Saltando evento con ID vacío")
                                continue
                            
                            # Agregar a cache
                            self._eventos_cache[evento.id] = evento
                            
                            # Agregar al batch de Firestore
                            evento_dict = self._evento_to_dict(evento)
                            evento_ref = (
                                self._db.collection('security_videos')
                                .document(video_id)
                                .collection('eventos')
                                .document(evento.id)
                            )
                            batch.set(evento_ref, evento_dict)
                            guardados += 1
                        
                        # Commit del batch
                        batch.commit()
                        logger.info(f"✅ Batch {i//batch_size + 1}: {len(batch_eventos)} eventos guardados")
                    
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
                    logger.error(f"❌ Error guardando eventos en batch: {e}", exc_info=True)
                    raise
            else:
                # Sin Firestore, solo guardar en cache
                for evento in eventos:
                    if evento.id and evento.id.strip():
                        self._eventos_cache[evento.id] = evento
                        guardados += 1
        
        return guardados

    def obtener_evento(self, video_id: str, evento_id: str) -> Optional[EventoSeguridad]:
        """Obtiene un evento específico"""
        cache_key = f"{video_id}_{evento_id}"
        
        # Buscar en cache
        if cache_key in self._eventos_cache:
            return self._eventos_cache[cache_key]

        # Buscar en Firestore
        if self.is_available():
            try:
                doc = self._db.collection('security_videos').document(video_id).collection('eventos').document(evento_id).get()
                if doc.exists:
                    evento = self._dict_to_evento(doc.to_dict())
                    self._eventos_cache[cache_key] = evento
                    return evento
            except Exception as e:
                logger.error(f"❌ Error obteniendo evento: {e}")

        return None

    def obtener_eventos_video(self, video_id: str) -> List[EventoSeguridad]:
        """Obtiene todos los eventos de un video"""
        if self.is_available():
            try:
                docs = (
                    self._db.collection('security_videos')
                    .document(video_id)
                    .collection('eventos')
                    .order_by('timestamp_inicio')
                    .limit(5000)
                    .stream()
                )
                eventos = []
                for doc in docs:
                    evento = self._dict_to_evento(doc.to_dict())
                    cache_key = f"{video_id}_{evento.id}"
                    self._eventos_cache[cache_key] = evento
                    eventos.append(evento)
                return eventos
            except Exception as e:
                logger.error(f"❌ Error obteniendo eventos: {e}")
                return []

        # Fallback a cache
        return [e for e in self._eventos_cache.values() if e.security_video_id == video_id]

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
    def _sanitize_for_firestore(data):
        """Sanitiza datos recursivamente para Firestore: claves de dict deben ser strings no vacíos"""
        if isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                key = str(k) if not isinstance(k, str) else k
                if not key:  # Clave vacía
                    key = '_empty_'
                sanitized[key] = SecurityVideoRepository._sanitize_for_firestore(v)
            return sanitized
        elif isinstance(data, list):
            return [SecurityVideoRepository._sanitize_for_firestore(item) for item in data]
        elif isinstance(data, set):
            return list(data)
        elif isinstance(data, (str, int, float, bool)) or data is None:
            return data
        else:
            return str(data)  # Fallback: convertir a string

    def _video_to_dict(self, video: SecurityVideo) -> Dict[str, Any]:
        """Convierte SecurityVideo a diccionario para Firestore"""
        raw = {
            'id': video.id,
            'usuario': video.usuario,
            'nombre_camara': video.nombre_camara,
            'ubicacion': video.ubicacion,
            'fecha_grabacion': video.fecha_grabacion,
            'duracion_segundos': video.duracion_segundos,
            'ruta_gcs': video.ruta_gcs,
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
        return self._sanitize_for_firestore(raw)

    def _dict_to_video(self, data: Dict[str, Any]) -> SecurityVideo:
        """Convierte diccionario de Firestore a SecurityVideo"""
        return SecurityVideo(
            id=data['id'],
            usuario=data['usuario'],
            nombre_camara=data['nombre_camara'],
            ubicacion=data['ubicacion'],
            fecha_grabacion=data['fecha_grabacion'],
            duracion_segundos=data['duracion_segundos'],
            ruta_gcs=data['ruta_gcs'],
            estado=EstadoSecurityVideo(data['estado']),
            metadata_tecnico=data.get('metadata_tecnico', {}),
            eventos=data.get('eventos', []),
            estadisticas=data.get('estadisticas', {}),
            reporte_txt_url=data.get('reporte_txt_url', ''),
            reporte_pdf_url=data.get('reporte_pdf_url', ''),
            fecha_creacion=data.get('fecha_creacion'),
            fecha_procesamiento=data.get('fecha_procesamiento'),
            tiempo_procesamiento_segundos=data.get('tiempo_procesamiento_segundos'),
            configuracion=data.get('configuracion', {}),
        )

    def _evento_to_dict(self, evento: EventoSeguridad) -> Dict[str, Any]:
        """Convierte EventoSeguridad a diccionario para Firestore"""
        return {
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
        }

    def _dict_to_evento(self, data: Dict[str, Any]) -> EventoSeguridad:
        """Convierte diccionario de Firestore a EventoSeguridad"""
        return EventoSeguridad(
            id=data['id'],
            security_video_id=data['security_video_id'],
            timestamp_inicio=data['timestamp_inicio'],
            timestamp_fin=data['timestamp_fin'],
            duracion=data['duracion'],
            objetos_detectados=data.get('objetos_detectados', []),
            acciones_detectadas=data.get('acciones_detectadas', []),
            personas_count=data.get('personas_count', 0),
            vehiculos_count=data.get('vehiculos_count', 0),
            descripcion=data.get('descripcion', ''),
            confianza=data.get('confianza', 0.0),
            analisis_detallado=data.get('analisis_detallado', {})
        )
