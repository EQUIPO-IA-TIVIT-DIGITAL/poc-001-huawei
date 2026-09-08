"""
Job de limpieza periódica de videos expirados.
Elimina videos de Firestore y GCS con más de 24 horas de antigüedad.
Se ejecuta cada hora vía RQ Scheduler.
"""
import os
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Retención máxima de videos (horas)
VIDEO_RETENTION_HOURS = 24


def cleanup_expired_videos():
    """
    Job programado: elimina videos de Firestore y GCS con más de 24 horas.
    Se re-programa automáticamente para ejecutarse cada hora.
    """
    logger.info("🧹 Iniciando limpieza de videos expirados (>24h)...")

    try:
        from main import create_app
        app = create_app()

        with app.app_context():
            from infrastructure.adapters.gcp_firestore import FirestoreAdapter
            from infrastructure.dependencies import get_storage_adapter
            from config.gcp_config import GCPConfig

            firestore_adapter = FirestoreAdapter(GCPConfig())
            storage = get_storage_adapter()

            if not firestore_adapter.is_available():
                logger.warning("⚠️ Firestore no disponible, saltando limpieza")
                _reschedule()
                return {'success': False, 'reason': 'Firestore no disponible'}

            cutoff = datetime.now(timezone.utc) - timedelta(hours=VIDEO_RETENTION_HOURS)
            deleted_count = 0
            errors = 0

            # Consultar videos con fecha_subida anterior al corte
            try:
                from google.cloud.firestore_v1.base_query import FieldFilter
                query = firestore_adapter.db.collection("videos") \
                    .where(filter=FieldFilter("fecha_subida", "<", cutoff)) \
                    .limit(200)
                docs = list(query.stream())
            except Exception as e:
                logger.error(f"Error consultando videos expirados: {e}")
                _reschedule()
                return {'success': False, 'error': str(e)}

            for doc in docs:
                video_id = doc.id
                data = doc.to_dict()

                # Eliminar archivo de GCS
                if storage and storage.is_available():
                    try:
                        formato = data.get("formato", "mp4")
                        blob_name = f"videos/{video_id}.{formato}"
                        storage.delete_file(blob_name)
                        # También eliminar thumbnail
                        storage.delete_file(f"thumbnails/{video_id}.jpg")
                    except Exception as e:
                        logger.warning(f"Error eliminando blobs de {video_id}: {e}")

                # Eliminar documento de Firestore
                try:
                    doc.reference.delete()
                    deleted_count += 1
                    logger.info(f"🗑️ Video expirado eliminado: {video_id}")
                except Exception as e:
                    logger.error(f"Error eliminando doc {video_id}: {e}")
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
