"""
Repositorio de Videos con persistencia local
Cache en memoria + persistencia en PostgreSQL/SQLAlchemy
"""

from typing import List, Optional, Dict, Any
from threading import Lock
import logging

from domain.entities import Video, EstadoVideo

logger = logging.getLogger(__name__)


class VideoRepositoryFirestore:
    """
    Repositorio de videos con persistencia en la base de datos local.

    Implementa el patrón Singleton con cache en memoria para rendimiento.
    Todos los cambios se persisten en PostgreSQL/SQLAlchemy automáticamente.

    Estructura en la base de datos:
    - tabla de videos → Video
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
        """Inicializa el repositorio con cache en memoria"""
        if self._initialized:
            return

        self._cache: Dict[str, Video] = {}
        self._lock_repo = Lock()
        self._firestore = None
        self._initialized = True

    def _init_firestore(self):
        self._firestore = None

    def guardar(self, video: Video) -> Video:
        """
        Guarda un video en la base de datos y cache.

        Args:
            video: Video a guardar

        Returns:
            Video guardado
        """
        with self._lock_repo:
            # Guardar en cache
            self._cache[video.id] = video

            # Persistir en la base de datos
            if self._firestore and self._firestore.is_available():
                try:
                    self._firestore.save_video(video)
                    logger.debug(f"✅ Video guardado en la base de datos: {video.id}")
                except Exception as e:
                    logger.error(f"❌ Error guardando video en la base de datos: {e}")

            return video

    def obtener_por_id(self, video_id: str) -> Optional[Video]:
        """Obtiene un video por ID"""
        with self._lock_repo:
            # Primero buscar en cache
            if video_id in self._cache:
                return self._cache[video_id]

            # Si no está en cache, buscar en la base de datos
            if self._firestore and self._firestore.is_available():
                try:
                    video = self._firestore.get_video(video_id)
                    if video:
                        self._cache[video_id] = video
                        return video
                except Exception as e:
                    logger.error(f"Error buscando video: {e}")

            return None

    def obtener_todos(self, limit: int = 100) -> List[Video]:
        """Obtiene todos los videos (sin paginación, para compatibilidad)"""
        if self._firestore and self._firestore.is_available():
            try:
                videos, _ = self._firestore.get_all_videos(limit=limit)
                # Actualizar cache
                for video in videos:
                    self._cache[video.id] = video
                return videos
            except Exception as e:
                logger.error(f"Error obteniendo videos: {e}")

        # Fallback a cache
        with self._lock_repo:
            return list(self._cache.values())[:limit]

    def obtener_todos_paginado(self, limit: int = 20, cursor: str = None) -> tuple[List[Video], str]:
        """
        Obtiene videos con paginación mediante cursor.
        
        Args:
            limit: Número de videos por página (max 100)
            cursor: ID del último video de la página anterior
            
        Returns:
            tuple: (Lista de videos, cursor para siguiente página o None)
        """
        limit = min(limit, 100)  # Limitar máximo
        
        if self._firestore and self._firestore.is_available():
            try:
                videos, next_cursor = self._firestore.get_all_videos(limit=limit, cursor=cursor)
                # Actualizar cache
                for video in videos:
                    self._cache[video.id] = video
                return videos, next_cursor
            except Exception as e:
                logger.error(f"Error obteniendo videos paginados: {e}")

        # Fallback a cache (paginación simple por offset)
        with self._lock_repo:
            all_videos = list(self._cache.values())
            start_idx = 0
            if cursor:
                for i, v in enumerate(all_videos):
                    if v.id == cursor:
                        start_idx = i + 1
                        break
            
            page = all_videos[start_idx:start_idx + limit]
            next_cursor = page[-1].id if len(page) == limit and start_idx + limit < len(all_videos) else None
            return page, next_cursor

    def obtener_por_usuario(self, usuario: str) -> List[Video]:
        """Obtiene todos los videos de un usuario"""
        if self._firestore and self._firestore.is_available():
            try:
                videos = self._firestore.get_videos_by_socio(usuario)
                for video in videos:
                    self._cache[video.id] = video
                return videos
            except Exception as e:
                logger.error(f"Error obteniendo videos del usuario: {e}")

        # Fallback a cache
        with self._lock_repo:
            return [v for v in self._cache.values() if v.usuario.lower() == usuario.lower()]

    def obtener_por_usuario_y_workspace(self, usuario: str, workspace_id: str) -> List[Video]:
        """Obtiene videos de un usuario filtrado por workspace directamente en DB"""
        if self._firestore and self._firestore.is_available():
            try:
                videos = self._firestore.get_videos_by_workspace(usuario, workspace_id)
                for video in videos:
                    self._cache[video.id] = video
                return videos
            except Exception as e:
                logger.error(f"Error obteniendo videos por workspace: {e}")
                
        # Fallback a cache
        with self._lock_repo:
            return [v for v in self._cache.values() 
                    if v.usuario.lower() == usuario.lower() 
                    and getattr(v, 'workspace_id', 'general') == workspace_id]


    def obtener_por_estado(self, estado: EstadoVideo) -> List[Video]:
        """Obtiene videos por estado"""
        if self._firestore and self._firestore.is_available():
            try:
                if estado == EstadoVideo.PENDIENTE:
                    return self._firestore.get_pending_videos()
            except Exception as e:
                logger.error(f"Error obteniendo videos por estado: {e}")

        # Fallback a cache
        with self._lock_repo:
            return [v for v in self._cache.values() if v.estado == estado]

    def obtener_pendientes(self) -> List[Video]:
        """Obtiene videos pendientes de revisión"""
        return self.obtener_por_estado(EstadoVideo.EN_REVISION)

    def eliminar(self, video_id: str) -> bool:
        """Elimina un video"""
        with self._lock_repo:
            # Eliminar de cache
            if video_id in self._cache:
                del self._cache[video_id]

            # Eliminar de la base de datos
            if self._firestore and self._firestore.is_available():
                try:
                    return self._firestore.delete_video(video_id)
                except Exception as e:
                    logger.error(f"Error eliminando video: {e}")
                    return False

            return True

    def actualizar_estado(self, video_id: str, nuevo_estado: EstadoVideo) -> bool:
        """Actualiza el estado de un video"""
        video = self.obtener_por_id(video_id)
        if not video:
            return False

        try:
            video.actualizar_estado(nuevo_estado)
            self.guardar(video)
            return True
        except Exception as e:
            logger.error(f"Error actualizando estado: {e}")
            return False

    def contar_total(self) -> int:
        """Cuenta el total de videos"""
        if self._firestore and self._firestore.is_available():
            try:
                stats = self._firestore.get_statistics()
                return stats.get("videos", {}).get("total", 0)
            except Exception as e:
                logger.debug(f"Could not get database statistics: {e}")

        with self._lock_repo:
            return len(self._cache)

    def obtener_estadisticas(self) -> Dict[str, Any]:
        """Obtiene estadísticas de videos"""
        if self._firestore and self._firestore.is_available():
            try:
                return self._firestore.get_statistics()
            except Exception as e:
                logger.error(f"Error obteniendo estadísticas: {e}")

        # Fallback a cache
        with self._lock_repo:
            total = len(self._cache)
            por_estado = {}
            for video in self._cache.values():
                if video.estado == EstadoVideo.COMPLETADO:
                    res_ia = video.metadatos_ia.get("resultado_ia")
                    if res_ia == "RECHAZADO":
                        estado = "rechazado"
                    else:
                        estado = "aprobado"
                else:
                    estado = (
                        video.estado.value
                        if hasattr(video.estado, "value")
                        else str(video.estado)
                    )
                por_estado[estado] = por_estado.get(estado, 0) + 1

            return {"available": True, "videos": {"total": total, **por_estado}}

    # --- Métodos de Analytics ---

    def obtener_stats_diarias(self, dias: int = 7) -> List[Dict[str, Any]]:
        """
        Obtiene el conteo de videos procesados por día.
        Retorna lista de {fecha: "YYYY-MM-DD", total: int, aprobados: int, rechazados: int}
        """
        from datetime import datetime, timedelta
        import re

        # Asegurar que tenemos datos
        videos = self.obtener_todos(limit=1000)

        # Inicializar estructura de fechas
        today = datetime.now().date()
        stats_map = {}
        for i in range(dias):
            date_key = (today - timedelta(days=i)).isoformat()
            stats_map[date_key] = {
                "fecha": date_key,
                "total": 0,
                "aprobados": 0,
                "rechazados": 0,
                "en_revision": 0,
            }

        # Agrupar videos
        for video in videos:
            # Intentar obtener fecha de subida o procesamiento
            fecha_str = None
            
            if video.metadatos_ia:
                # Intentar fecha_subida primero (es la más común)
                fecha_raw = video.metadatos_ia.get("fecha_subida") or video.metadatos_ia.get("fecha_procesamiento")
                
                if fecha_raw:
                    try:
                        # Parsear fecha (puede ser string ISO, timestamp, datetime object, etc.)
                        if isinstance(fecha_raw, str):
                            # Extraer solo la parte de fecha (YYYY-MM-DD)
                            # Soporta formatos: "2026-01-09", "2026-01-09 22:28:00", "2026-01-09T22:28:00+00:00"
                            match = re.match(r'(\d{4}-\d{2}-\d{2})', fecha_raw)
                            if match:
                                fecha_str = match.group(1)
                        elif hasattr(fecha_raw, 'date'):
                            # Es un objeto datetime
                            fecha_str = fecha_raw.date().isoformat()
                        else:
                            # Último recurso: convertir a string y buscar patrón
                            fecha_str_temp = str(fecha_raw)
                            match = re.match(r'(\d{4}-\d{2}-\d{2})', fecha_str_temp)
                            if match:
                                fecha_str = match.group(1)
                    except Exception as e:
                        logger.warning(f"Error parseando fecha para video {video.id}: {e}")

            # Si aún no tenemos fecha y el video tiene created_at
            if not fecha_str and hasattr(video, "created_at") and video.created_at:
                try:
                    fecha_str_temp = str(video.created_at)
                    match = re.match(r'(\d{4}-\d{2}-\d{2})', fecha_str_temp)
                    if match:
                        fecha_str = match.group(1)
                except Exception as e:
                    logger.debug(f"Could not parse video date: {e}")

            # Si la fecha está en nuestro rango, contar
            if fecha_str and fecha_str in stats_map:
                stats_map[fecha_str]["total"] += 1

                # Check Aprobados (Status APROBADO or COMPLETADO + resultado_ia=APROBADO)
                if video.estado == EstadoVideo.APROBADO:
                    stats_map[fecha_str]["aprobados"] += 1
                elif video.estado == EstadoVideo.COMPLETADO:
                    if video.metadatos_ia.get("resultado_ia") == "RECHAZADO":
                        stats_map[fecha_str]["rechazados"] += 1
                    else:
                        stats_map[fecha_str]["aprobados"] += 1
                # Check Rechazados (Status RECHAZADO)
                elif video.estado == EstadoVideo.RECHAZADO:
                    stats_map[fecha_str]["rechazados"] += 1
                # Check En Revisión
                elif video.estado == EstadoVideo.EN_REVISION:
                    stats_map[fecha_str]["en_revision"] += 1

        # Convertir a lista ordenada
        resultado = list(stats_map.values())
        resultado.sort(key=lambda x: x["fecha"])
        return resultado

    def obtener_top_usuarios(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Obtiene los usuarios con más actividad.
        """
        videos = self.obtener_todos(limit=1000)
        user_counts = {}

        for video in videos:
            if not video.usuario:
                continue

            user = video.usuario
            if user not in user_counts:
                user_counts[user] = {
                    "usuario": user,
                    "videos": 0,
                    "aprobados": 0,
                    "rechazados": 0,
                }

            user_counts[user]["videos"] += 1

            if video.estado == EstadoVideo.APROBADO:
                user_counts[user]["aprobados"] += 1
            elif video.estado == EstadoVideo.COMPLETADO:
                if video.metadatos_ia.get("resultado_ia") != "RECHAZADO":
                    user_counts[user]["aprobados"] += 1
                else:
                    user_counts[user]["rechazados"] += 1
            elif video.estado == EstadoVideo.RECHAZADO:
                user_counts[user]["rechazados"] += 1

        # Ordenar por total de videos
        sorted_users = sorted(
            user_counts.values(), key=lambda x: x["videos"], reverse=True
        )
        return sorted_users[:limit]

    def sync_videos_from_disk(self, upload_dir: str, usuario: str, workspace_id: str = None) -> Dict[str, Any]:
        """
        Escanea el directorio de uploads y re-indexa archivos huérfanos en la base de datos.
        
        Args:
            upload_dir: Ruta al directorio de uploads
            usuario: Username al que asignar los videos
            workspace_id: ID del workspace (si None, se usa el General del usuario)
            
        Returns:
            Dict con estadísticas del sync
        """
        import os
        from pathlib import Path
        from datetime import datetime
        
        EXTENSIONES_VIDEO = {'.mp4', '.avi', '.mov', '.webm', '.mkv', '.flv', '.wmv'}
        
        upload_path = Path(upload_dir)
        if not upload_path.exists():
            return {"synced": 0, "skipped": 0, "errors": 0, "message": "Upload directory not found"}
        
        # Resolver workspace_id si no se proporcionó
        if not workspace_id:
            try:
                from infrastructure.repositories.workspace_repository import WorkspaceRepositoryFirestore
                ws_repo = WorkspaceRepositoryFirestore()
                ws_general = ws_repo.obtener_workspace_general(usuario)
                workspace_id = ws_general.id
            except Exception as e:
                logger.error(f"Error obteniendo workspace general: {e}")
                workspace_id = "general"
        
        synced = 0
        skipped = 0
        errors = 0
        
        for archivo in upload_path.iterdir():
            if not archivo.is_file():
                continue
            
            ext = archivo.suffix.lower()
            if ext not in EXTENSIONES_VIDEO:
                continue
            
            # Extraer video_id del nombre (formato: UUID.ext)
            video_id = archivo.stem
            
            # Verificar si ya existe en la base de datos
            existing = self.obtener_por_id(video_id)
            if existing:
                skipped += 1
                continue
            
            try:
                # Obtener fecha de modificación del archivo como fecha de creación
                file_mtime = datetime.fromtimestamp(archivo.stat().st_mtime)
                file_size = archivo.stat().st_size
                
                video = Video(
                    id=video_id,
                    usuario=usuario,
                    ruta_archivo=str(archivo),
                    descripcion="Video recuperado (sync automático)",
                    metadatos_ia={
                        "nombre_archivo": archivo.name,
                        "tamanio_bytes": file_size,
                        "fecha_subida": file_mtime.isoformat(),
                        "sync_recovery": True,
                    },
                    estado=EstadoVideo.PENDIENTE,
                    nombre_archivo=archivo.name,
                    workspace_id=workspace_id,
                    fecha_creacion=file_mtime.isoformat(),
                )
                
                self.guardar(video)
                synced += 1
                logger.info(f"🔄 Video sincronizado: {video_id} ({archivo.name})")
                
            except Exception as e:
                errors += 1
                logger.error(f"❌ Error sincronizando {video_id}: {e}")
        
        result = {
            "synced": synced,
            "skipped": skipped,
            "errors": errors,
            "total_files": synced + skipped + errors,
            "usuario": usuario,
            "workspace_id": workspace_id,
        }
        
        if synced > 0:
            logger.info(f"🔄 Sync completado: {synced} videos recuperados, {skipped} ya existían, {errors} errores")
            
            # Actualizar estadísticas del workspace
            try:
                from infrastructure.services.workspace_stats_service import recalculate_workspace_stats
                recalculate_workspace_stats(workspace_id, touch_activity=True)
            except Exception as e:
                logger.error(f"Error actualizando estadísticas del workspace: {e}")
        
        return result

    def obtener_razones_rechazo(self) -> List[Dict[str, Any]]:
        """
        Obtiene las razones de rechazo más comunes.
        """
        videos = self.obtener_todos(limit=1000)
        reasons = {}

        for video in videos:
            is_rechazado = video.estado == EstadoVideo.RECHAZADO
            if not is_rechazado and video.estado == EstadoVideo.COMPLETADO:
                if video.metadatos_ia.get("resultado_ia") == "RECHAZADO":
                    is_rechazado = True

            if is_rechazado and video.metadatos_ia:
                razon = video.metadatos_ia.get(
                    "razon_rechazo"
                ) or video.metadatos_ia.get("razon_decision")
                if razon:
                    # Simplificar razones muy largas o específicas
                    razon_key = razon.split(".")[0] if "." in razon else razon
                    razon_key = razon_key[:50]  # Truncar
                    reasons[razon_key] = reasons.get(razon_key, 0) + 1

        # Formatear salida
        result = [{"razon": k, "cantidad": v} for k, v in reasons.items()]
        result.sort(key=lambda x: x["cantidad"], reverse=True)
        return result


# Alias para compatibilidad
VideoRepositoryMemory = VideoRepositoryFirestore
