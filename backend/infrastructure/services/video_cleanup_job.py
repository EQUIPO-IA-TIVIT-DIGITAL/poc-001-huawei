"""
Job de limpieza periódica de videos expirados.
Elimina videos con más de 24 horas de antigüedad usando el stack local
(SQLAlchemy + MinIO/Filesystem). Se ejecuta cada hora vía RQ Scheduler.
"""
import os
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

def cleanup_expired_videos():
    """
    Job programado: elimina videos solo cuando VIDEO_RETENTION_HOURS es positivo.
    Se re-programa automáticamente para ejecutarse cada hora.
    """
    try:
        retention_hours = float(os.getenv("VIDEO_RETENTION_HOURS", "0"))
    except ValueError:
        retention_hours = 0
    if retention_hours <= 0:
        logger.info("🧹 Limpieza de videos deshabilitada (VIDEO_RETENTION_HOURS no configurado)")
        return {"success": True, "deleted": 0, "disabled": True}

    logger.info("🧹 Iniciando limpieza de videos expirados (>%sh)...", retention_hours)

    try:
        from main import create_app
        app = create_app()

        with app.app_context():
            from infrastructure.repositories.sqlalchemy_repositories import SQLAlchemyVideoRepository
            from infrastructure.dependencies import get_storage_adapter
            from infrastructure.db.session import SessionLocal
            from infrastructure.db.models import VideoModel

            video_repo = SQLAlchemyVideoRepository()
            storage = get_storage_adapter()

            cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)

            # Consultar videos con fecha previa al corte
            db = SessionLocal()
            try:
                rows = db.query(VideoModel).filter(
                    VideoModel.created_at < cutoff
                ).limit(200).all()
            except Exception as e:
                logger.error(f"Error consultando videos expirados: {e}")
                _reschedule()
                return {'success': False, 'error': str(e)}
            finally:
                db.close()

            deleted_count = 0
            errors = 0

            for m in rows:
                video_id = m.id

                # Eliminar archivo de storage (MinIO/Filesystem)
                if storage and storage.is_available():
                    try:
                        storage_uri = m.storage_uri or m.s3_uri
                        if storage_uri:
                            if storage_uri.startswith("file://"):
                                path = storage_uri.removeprefix("file://")
                                if hasattr(storage, "base_dir"):
                                    path = str(os.path.relpath(path, storage.base_dir))
                                storage.delete_file(path)
                            else:
                                path = storage_uri.split("://", 1)[-1].split("/", 1)[-1]
                                storage.delete_file(path)
                        # También eliminar thumbnail
                        storage.delete_file(f"thumbnails/{video_id}.jpg")
                    except Exception as e:
                        logger.warning(f"Error eliminando blobs de {video_id}: {e}")

                # Eliminar registro de BD
                try:
                    if video_repo.eliminar(video_id):
                        deleted_count += 1
                        logger.info(f"🗑️ Video expirado eliminado: {video_id}")
                    else:
                        errors += 1
                except Exception as e:
                    logger.error(f"Error eliminando video {video_id}: {e}")
                    errors += 1

            logger.info(f"🧹 Limpieza completada: {deleted_count} eliminados, {errors} errores")

            # Re-programar siguiente ejecución
            _reschedule()

            return {'success': True, 'deleted': deleted_count, 'errors': errors}

    except Exception as e:
        logger.error(f"❌ Error en limpieza de videos: {e}", exc_info=True)
        _reschedule()
        return {'success': False, 'error': str(e)}


def _reschedule():
    """Re-programa la siguiente ejecución de limpieza en 1 hora."""
    try:
        from redis import Redis
        from rq import Queue

        redis_conn = Redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
        q = Queue('video_processing', connection=redis_conn)
        q.enqueue_in(
            timedelta(hours=1),
            cleanup_expired_videos,
            job_id=f"cleanup_expired_videos_{int(datetime.now().timestamp())}",
            job_timeout=300,
        )
        logger.info("🔄 Siguiente limpieza programada en 1 hora")
    except Exception as e:
        logger.warning(f"⚠️ No se pudo re-programar limpieza: {e}")
