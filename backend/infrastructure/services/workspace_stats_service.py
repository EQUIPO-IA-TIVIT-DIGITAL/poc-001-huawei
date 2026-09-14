"""Servicio para mantener estadísticas de workspace actualizadas por evento."""

from datetime import datetime
import logging

from domain.entities import EstadoVideo
from infrastructure.dependencies import get_video_repository
from infrastructure.repositories.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)


def recalculate_workspace_stats(workspace_id: str, touch_activity: bool = True) -> bool:
    """
    Recalcula y persiste estadísticas de un workspace desde su fuente real de videos.

    Args:
        workspace_id: ID del workspace a actualizar.
        touch_activity: Si True, actualiza ultima_actividad con timestamp actual.

    Returns:
        bool: True si se actualizó correctamente, False en caso contrario.
    """
    try:
        workspace_repo = WorkspaceRepository()
        video_repo = get_video_repository()

        workspace = workspace_repo.obtener_por_id(workspace_id)
        if not workspace:
            return False

        videos_workspace = video_repo.obtener_por_usuario_y_workspace(
            workspace.usuario,
            workspace_id,
        )

        total_videos = len(videos_workspace)
        aprobados = sum(
            1
            for v in videos_workspace
            if v.estado in (EstadoVideo.COMPLETADO, EstadoVideo.APROBADO)
        )
        rechazados = sum(
            1
            for v in videos_workspace
            if v.estado in (EstadoVideo.RECHAZADO, EstadoVideo.ERROR)
        )
        en_revision = sum(
            1
            for v in videos_workspace
            if v.estado == EstadoVideo.EN_REVISION
        )

        duracion_total = 0
        for v in videos_workspace:
            if getattr(v, "metadatos_ia", None):
                duracion_total += int(v.metadatos_ia.get("duracion_segundos", 0) or 0)

        ultima_actividad = datetime.now().isoformat() if touch_activity else (
            (workspace.estadisticas or {}).get("ultima_actividad", workspace.fecha_modificacion or "")
        )

        workspace.actualizar_estadisticas(
            total_videos=total_videos,
            aprobados=aprobados,
            rechazados=rechazados,
            en_revision=en_revision,
            duracion_total=duracion_total,
            ultima_actividad=ultima_actividad,
        )
        workspace_repo.guardar(workspace)
        return True
    except Exception as e:
        logger.warning(f"Error recalculando estadísticas de workspace {workspace_id}: {e}")
        return False
