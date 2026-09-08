"""
Worker RQ para procesamiento de videos de seguridad
Fase 3 - Mejoras Pipeline v3.0

Este worker escucha la cola de Redis y procesa videos en background.
Puede escalarse horizontalmente corriendo múltiples instancias.

Uso:
    python worker.py
    
En Docker:
    docker-compose up -d worker
"""
import os
import sys
import logging
from datetime import timedelta
from rq import Worker, Queue
from redis import Redis
from infrastructure.services.logging_service import (
    setup_logging,
    clear_request_context,
    set_request_id,
)

# Configurar logging centralizado (igual que API)
setup_logging("tivit-worker")
logger = logging.getLogger(__name__)



def process_video_job(video_id: str):
    """
    Función wrapper para procesar video en el worker.
    Esta función es encolada por job_queue.py
    """
    from use_cases.complete_security_processor import CompleteSecurityVideoProcessor
    
    clear_request_context()
    set_request_id(f"job-security-{video_id[:12]}")
    logger.info(f"🎬 Worker procesando video: {video_id}")
    
    processor = CompleteSecurityVideoProcessor()
    try:
        processor.process_video_complete(video_id)
        logger.info(f"✅ Worker completó video: {video_id}")
        return {'success': True, 'video_id': video_id}
        
    except Exception as e:
        logger.error(f"❌ Worker falló en video {video_id}: {e}", exc_info=True)
        raise  # Re-raise para que RQ lo marque como failed


def process_operational_video(analysis_id: str):
    """
    Función wrapper para procesar análisis operativo en el worker.
    Esta función es encolada por job_queue.enqueue_operational_analysis()
    """
    from use_cases.operational_analyzer import OperationalAnalyzer

    clear_request_context()
    set_request_id(f"job-operational-{analysis_id[:12]}")
    logger.info(f"📊 Worker procesando análisis operativo: {analysis_id}")

    analyzer = OperationalAnalyzer()
    try:
        analyzer.process(analysis_id)
        try:
            from infrastructure.services.job_queue import clear_active_operational_job
            clear_active_operational_job(analysis_id)
        except Exception:
            pass
        logger.info(f"✅ Worker completó análisis operativo: {analysis_id}")
        return {'success': True, 'analysis_id': analysis_id}

    except Exception as e:
        try:
            from infrastructure.services.job_queue import clear_active_operational_job
            clear_active_operational_job(analysis_id)
        except Exception:
            pass
        logger.error(f"❌ Worker falló análisis operativo {analysis_id}: {e}", exc_info=True)
        raise  # Re-raise para que RQ lo marque como failed


def process_audio_analysis(analysis_id: str):
    """
    Función wrapper para procesar análisis de audio en el worker.
    Extrae audio, transcribe con timestamps y genera resumen.
    Esta función es encolada por job_queue.enqueue_audio_analysis()
    """
    from use_cases.audio_analyzer import AudioAnalyzer

    clear_request_context()
    set_request_id(f"job-audio-{analysis_id[:12]}")
    logger.info(f"🎵 Worker procesando análisis de audio: {analysis_id}")

    analyzer = AudioAnalyzer()
    try:
        analyzer.process(analysis_id)
        try:
            from infrastructure.services.job_queue import clear_active_audio_job
            clear_active_audio_job(analysis_id)
        except Exception:
            pass
        logger.info(f"✅ Worker completó análisis de audio: {analysis_id}")
        return {'success': True, 'analysis_id': analysis_id}

    except Exception as e:
        try:
            from infrastructure.services.job_queue import clear_active_audio_job
            clear_active_audio_job(analysis_id)
        except Exception:
            pass
        logger.error(f"❌ Worker falló análisis de audio {analysis_id}: {e}", exc_info=True)
        raise  # Re-raise para que RQ lo marque como failed


def process_socio_video(video_id: str):
    """
    Función wrapper para procesar video de socio en el worker (v4.0).
    Pipeline optimizado: 5 pasos, sin Video Intelligence, con cache y compresión.
    Esta función es encolada por job_queue.enqueue_socio_video()
    """
    clear_request_context()
    set_request_id(f"job-socio-{video_id[:12]}")
    logger.info(f"🎬 Worker procesando video socio: {video_id}")

    job_id = None
    retries_left = 0
    try:
        from rq import get_current_job

        current_job = get_current_job()
        if current_job:
            job_id = current_job.id
            retries_left = int(getattr(current_job, 'retries_left', 0) or 0)
    except Exception:
        pass

    try:
        from infrastructure.worker_dependencies import get_worker_container
        from infrastructure.services.job_queue import clear_active_socio_job
        
        container = get_worker_container()
        v_repo = container.video_repository
        procesador = container.video_processor

        vid = v_repo.obtener_por_id(video_id)

        if not vid:
            logger.error(f"Video {video_id} no encontrado en BD")
            clear_active_socio_job(video_id)
            return {'success': False, 'error': 'Video no encontrado'}

        blacklist_path = os.getenv("BLACKLIST_PATH", "config/blacklist.json")

        # Inicializar progreso (5 pasos v4.0)
        vid.agregar_metadatos("progreso", {
            "step": 0, "total_steps": 5,
            "message": "Iniciando...", "status": "pending",
        })
        v_repo.guardar(vid)

        # Callback de progreso (guarda en Firestore)
        progress_state = {'last_step': None, 'last_status': None}

        def progress_callback(step, total, msg, status, details=None):
            try:
                if (
                    progress_state['last_step'] == step
                    and progress_state['last_status'] == status
                ):
                    return
                progress_state['last_step'] = step
                progress_state['last_status'] = status

                vid_snap = v_repo.obtener_por_id(video_id)
                vid_snap.agregar_metadatos("progreso", {
                    "status": "processing", "step": step,
                    "total_steps": total, "message": msg,
                    "stepStatus": status, "details": details,
                })
                v_repo.guardar(vid_snap)
            except Exception:
                pass

        # Resetear estado si está en ERROR o no es PENDIENTE
        from domain.entities import EstadoVideo
        if vid.estado == EstadoVideo.ERROR:
            # Transición válida: ERROR -> PENDIENTE
            vid.actualizar_estado(EstadoVideo.PENDIENTE)
            v_repo.guardar(vid)
        elif vid.estado not in [EstadoVideo.PENDIENTE]:
            # Forzar a PENDIENTE si está en otro estado inesperado
            vid.estado = EstadoVideo.PENDIENTE
            v_repo.guardar(vid)

        video_procesado = procesador.ejecutar(
            vid, blacklist_path,
            progress_callback=progress_callback,
        )
        v_repo.guardar(video_procesado)

        clear_active_socio_job(video_id)

        logger.info(f"✅ Worker completó video socio: {video_id}")
        return {'success': True, 'video_id': video_id}

    except Exception as e:
        logger.error(f"❌ Worker falló video socio {video_id}: {e}", exc_info=True)

        # Persistir error
        try:
            from infrastructure.worker_dependencies import get_worker_container
            from domain.entities import EstadoVideo
            from infrastructure.services.job_queue import (
                clear_active_socio_job,
                register_socio_dead_letter,
            )
            v_repo = get_worker_container().video_repository
            vf = v_repo.obtener_por_id(video_id)
            if vf:
                vf.estado = EstadoVideo.ERROR
                vf.agregar_metadatos("error_procesamiento", str(e))
                v_repo.guardar(vf)

            # Registrar en DLQ solo cuando no queden más retries
            if retries_left <= 0:
                register_socio_dead_letter(video_id=video_id, error=str(e), job_id=job_id)
            clear_active_socio_job(video_id)
        except Exception:
            pass

        try:
            from infrastructure.services.job_queue import clear_active_socio_job
            clear_active_socio_job(video_id)
        except Exception:
            pass
        raise


def main():
    """Inicia el worker RQ"""
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    try:
        # Conectar a Redis
        redis_conn = Redis.from_url(redis_url)
        redis_conn.ping()
        logger.info(f"✅ Conectado a Redis: {redis_url}")
        
        # Crear worker
        queues = [Queue('video_processing', connection=redis_conn)]
        worker = Worker(queues, connection=redis_conn)
        
        logger.info("🚀 Worker RQ iniciado - Esperando videos...")
        logger.info(f"📋 Colas monitoreadas: {[q.name for q in queues]}")

        # Programar limpieza periódica de videos expirados (cada hora)
        try:
            from infrastructure.services.video_cleanup_job import cleanup_expired_videos

            queue = queues[0]
            queue.enqueue_in(
                timedelta(minutes=5),  # Primera ejecución en 5 min
                cleanup_expired_videos,
                job_timeout=300,
            )
            logger.info("🧹 Limpieza de videos expirados programada (en 5 min, luego cada hora)")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo programar limpieza automática: {e}")
        
        # Iniciar worker (loop infinito)
        worker.work(with_scheduler=True)
        
    except KeyboardInterrupt:
        logger.info("⚠️ Worker detenido por usuario")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Error en worker: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
