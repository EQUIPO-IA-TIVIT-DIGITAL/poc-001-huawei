"""
Sistema de Cola de Trabajos con Redis + RQ
Fase 3 - Mejoras Pipeline v3.0

Permite encolar videos para procesamiento asíncrono, evitando colapsos
cuando múltiples usuarios suben videos simultáneamente.

Arquitectura:
[Frontend] → [API] → [Redis Queue] → [Worker 1]
                                   → [Worker 2]
                                   → [Worker 3]
"""
import os
import logging
import json
import time
import uuid
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Lazy imports para evitar errores si Redis no está disponible
_redis_conn = None
_video_queue = None
MAX_PENDING_OPERATIONAL_JOBS = int(os.getenv('OPERATIONAL_QUEUE_MAX_PENDING', '200'))


def is_queue_required() -> bool:
    """Determina si la cola asíncrona es obligatoria para procesar videos."""
    explicit = os.getenv('REQUIRE_ASYNC_QUEUE')
    if explicit is not None:
        return explicit.lower() in ('1', 'true', 'yes', 'on')

    app_env = os.getenv('APP_ENV', os.getenv('FLASK_ENV', 'development')).lower()
    return app_env in ('prod', 'production', 'prd')


def _active_job_key(video_id: str) -> str:
    return f"socio:active_job:{video_id}"


def _active_audio_job_key(analysis_id: str) -> str:
    return f"audio:active_job:{analysis_id}"


def _active_operational_job_key(analysis_id: str) -> str:
    return f"operational:active_job:{analysis_id}"


def _fetch_active_socio_job(video_id: str) -> Optional[str]:
    """
    Devuelve job_id activo para un video socio si sigue queued/started.
    Limpia la referencia si el job ya terminó.
    """
    try:
        from rq.job import Job

        redis_conn = get_redis_connection()
        raw = redis_conn.get(_active_job_key(video_id))
        if not raw:
            return None

        job_id = raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)
        job = Job.fetch(job_id, connection=redis_conn)
        status = job.get_status()
        if status in ('queued', 'started', 'deferred', 'scheduled'):
            return job_id

        redis_conn.delete(_active_job_key(video_id))
        return None
    except Exception:
        return None


def clear_active_socio_job(video_id: str) -> None:
    """Limpia la referencia al job activo de un video socio."""
    try:
        redis_conn = get_redis_connection()
        redis_conn.delete(_active_job_key(video_id))
    except Exception:
        pass


def _fetch_active_audio_job(analysis_id: str) -> Optional[str]:
    """
    Devuelve job_id activo para un análisis de audio si sigue queued/started.
    Limpia la referencia si el job ya terminó.
    """
    try:
        from rq.job import Job

        redis_conn = get_redis_connection()
        raw = redis_conn.get(_active_audio_job_key(analysis_id))
        if not raw:
            return None

        job_id = raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)
        job = Job.fetch(job_id, connection=redis_conn)
        status = job.get_status()
        if status in ('queued', 'started', 'deferred', 'scheduled'):
            return job_id

        redis_conn.delete(_active_audio_job_key(analysis_id))
        return None
    except Exception:
        return None


def clear_active_audio_job(analysis_id: str) -> None:
    """Limpia la referencia al job activo de un análisis de audio."""
    try:
        redis_conn = get_redis_connection()
        redis_conn.delete(_active_audio_job_key(analysis_id))
    except Exception:
        pass


def _fetch_active_operational_job(analysis_id: str) -> Optional[str]:
    """
    Devuelve job_id activo para un análisis operacional si sigue queued/started.
    Limpia la referencia si el job ya terminó.
    """
    try:
        from rq.job import Job

        redis_conn = get_redis_connection()
        raw = redis_conn.get(_active_operational_job_key(analysis_id))
        if not raw:
            return None

        job_id = raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)
        job = Job.fetch(job_id, connection=redis_conn)
        status = job.get_status()
        if status in ('queued', 'started', 'deferred', 'scheduled'):
            return job_id

        redis_conn.delete(_active_operational_job_key(analysis_id))
        return None
    except Exception:
        return None


def clear_active_operational_job(analysis_id: str) -> None:
    """Limpia la referencia al job activo de un análisis operativo."""
    try:
        redis_conn = get_redis_connection()
        redis_conn.delete(_active_operational_job_key(analysis_id))
    except Exception:
        pass


def register_socio_dead_letter(video_id: str, error: str, job_id: Optional[str] = None) -> None:
    """Registra fallos terminales en una dead-letter queue simple basada en Redis list."""
    try:
        redis_conn = get_redis_connection()
        payload = {
            'id': str(uuid.uuid4()),
            'video_id': video_id,
            'job_id': job_id,
            'error': error[:2000],
            'timestamp': int(time.time()),
            'type': 'socio_video',
        }
        redis_conn.lpush('dlq:video_processing', json.dumps(payload))
        redis_conn.ltrim('dlq:video_processing', 0, 999)
    except Exception:
        pass


def get_job_status_by_id(job_id: str) -> dict:
    """Alias explícito para estado de job individual."""
    return get_job_status(job_id)


def get_dead_letter_entries(limit: int = 100) -> List[Dict[str, Any]]:
    """Lista entradas de DLQ más recientes (head first)."""
    try:
        redis_conn = get_redis_connection()
        limit = max(1, min(limit, 500))
        raw_entries = redis_conn.lrange('dlq:video_processing', 0, limit - 1)

        entries = []
        for raw in raw_entries:
            text = raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)
            try:
                item = json.loads(text)
                if 'id' not in item:
                    item['id'] = f"legacy:{hash(text)}"
                entries.append(item)
            except Exception:
                entries.append({
                    'id': f"raw:{hash(text)}",
                    'raw': text,
                    'type': 'unknown',
                })
        return entries
    except Exception as e:
        logger.error(f"❌ Error leyendo DLQ: {e}")
        return []


def remove_dead_letter_entry(entry_id: str) -> bool:
    """Elimina una entrada de DLQ por id."""
    try:
        redis_conn = get_redis_connection()
        raw_entries = redis_conn.lrange('dlq:video_processing', 0, -1)

        for raw in raw_entries:
            text = raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)
            try:
                item = json.loads(text)
                if item.get('id') == entry_id:
                    redis_conn.lrem('dlq:video_processing', 1, raw)
                    return True
            except Exception:
                continue
        return False
    except Exception as e:
        logger.error(f"❌ Error eliminando entrada DLQ {entry_id}: {e}")
        return False


def retry_dead_letter_video(video_id: str, priority: int = 0) -> Optional[str]:
    """Reencola un video fallido de DLQ y limpia la primera entrada asociada si encola bien."""
    job_id = enqueue_socio_video(video_id=video_id, priority=priority)
    if not job_id:
        return None

    try:
        redis_conn = get_redis_connection()
        raw_entries = redis_conn.lrange('dlq:video_processing', 0, -1)
        for raw in raw_entries:
            text = raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)
            try:
                item = json.loads(text)
                if item.get('video_id') == video_id:
                    redis_conn.lrem('dlq:video_processing', 1, raw)
                    break
            except Exception:
                continue
    except Exception:
        pass

    return job_id


def get_redis_connection():
    """Obtiene conexión a Redis (singleton)"""
    global _redis_conn
    if _redis_conn is None:
        try:
            from redis import Redis
            redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
            _redis_conn = Redis.from_url(redis_url, socket_connect_timeout=3, socket_timeout=3)
            # Test de conexión
            _redis_conn.ping()
            logger.info(f"✅ Redis conectado: {redis_url}")
        except ImportError:
            logger.error("❌ redis-py no instalado. Instalar con: pip install redis")
            raise
        except Exception as e:
            logger.error(f"❌ Error conectando a Redis: {e}")
            raise
    return _redis_conn


def get_video_queue():
    """Obtiene la cola de procesamiento de videos (singleton)"""
    global _video_queue
    if _video_queue is None:
        try:
            from rq import Queue
            redis_conn = get_redis_connection()
            _video_queue = Queue('video_processing', connection=redis_conn)
            logger.info("✅ Cola de videos inicializada")
        except ImportError:
            logger.error("❌ rq no instalado. Instalar con: pip install rq")
            raise
        except Exception as e:
            logger.error(f"❌ Error inicializando cola: {e}")
            raise
    return _video_queue


def enqueue_video_analysis(video_id: str) -> Optional[str]:
    """
    Encola un video para procesamiento asíncrono.
    
    Args:
        video_id: ID del video a procesar
        
    Returns:
        job_id: ID del trabajo en la cola (o None si falla)
    """
    try:
        queue = get_video_queue()
        
        # Encolar trabajo con timeout de 6 horas (videos largos pueden tardar)
        job = queue.enqueue(
            'worker.process_video_job',
            video_id,
            job_timeout='6h',  # 6 horas máximo
            result_ttl=86400,  # Mantener resultado 24 horas
            failure_ttl=86400  # Mantener errores 24 horas
        )
        
        logger.info(f"📋 Video {video_id} encolado - Job ID: {job.id}")
        return job.id
        
    except Exception as e:
        logger.error(f"❌ Error encolando video {video_id}: {e}")
        return None


def enqueue_operational_analysis(analysis_id: str) -> Optional[str]:
    """
    Encola un análisis operativo para procesamiento asíncrono.
    
    Args:
        analysis_id: ID del OperationalAnalysis a procesar
        
    Returns:
        job_id: ID del trabajo en la cola (o None si falla)
    """
    try:
        queue = get_video_queue()

        # Idempotencia: evita encolar duplicados del mismo análisis
        active_job_id = _fetch_active_operational_job(analysis_id)
        if active_job_id:
            logger.info(f"♻️ Análisis operativo {analysis_id} ya tiene job activo: {active_job_id}")
            return active_job_id
        
        job = queue.enqueue(
            'worker.process_operational_video',
            analysis_id,
            job_timeout='6h',
            result_ttl=86400,
            failure_ttl=86400
        )

        # Track por 6h (timeout + margen)
        redis_conn = get_redis_connection()
        redis_conn.setex(_active_operational_job_key(analysis_id), 21600, job.id)
        
        logger.info(f"📋 Análisis operativo {analysis_id} encolado - Job ID: {job.id}")
        return job.id
        
    except Exception as e:
        logger.error(f"❌ Error encolando análisis operativo {analysis_id}: {e}")
        return None


def enqueue_audio_analysis(analysis_id: str) -> Optional[str]:
    """
    Encola un análisis de audio para procesamiento asíncrono.
    
    Args:
        analysis_id: ID del AudioAnalysis a procesar
        
    Returns:
        job_id: ID del trabajo en la cola (o None si falla)
    """
    try:
        queue = get_video_queue()
        from worker import process_audio_analysis

        # Idempotencia: evita encolar duplicados del mismo análisis
        active_job_id = _fetch_active_audio_job(analysis_id)
        if active_job_id:
            logger.info(f"♻️ Análisis de audio {analysis_id} ya tiene job activo: {active_job_id}")
            return active_job_id
        
        job = queue.enqueue(
            process_audio_analysis,
            analysis_id,
            job_timeout='4h',
            result_ttl=86400,
            failure_ttl=86400
        )

        # Track por 6h (timeout + margen)
        redis_conn = get_redis_connection()
        redis_conn.setex(_active_audio_job_key(analysis_id), 21600, job.id)
        
        logger.info(f"📋 Análisis de audio {analysis_id} encolado - Job ID: {job.id}")
        return job.id
        
    except Exception as e:
        logger.error(f"❌ Error encolando análisis de audio {analysis_id}: {e}")
        return None


def enqueue_socio_video(video_id: str, priority: int = 0) -> Optional[str]:
    """
    Encola un video de socio para procesamiento con pipeline v4.0.
    
    Args:
        video_id: ID del video a procesar
        priority: Posición en la cola (0 = más prioritario, videos más pequeños primero)
        
    Returns:
        job_id: ID del trabajo en la cola (o None si falla)
    """
    try:
        queue = get_video_queue()

        # Idempotencia: evita encolar duplicados si ya hay un job activo para este video
        active_job_id = _fetch_active_socio_job(video_id)
        if active_job_id:
            logger.info(f"♻️ Video socio {video_id} ya tiene job activo: {active_job_id}")
            return active_job_id
        
        # Si priority=0, encolar al frente (at_front=True)
        at_front = (priority == 0)

        from rq import Retry

        job_id = f"socio:{video_id}:{int(time.time())}"
        
        job = queue.enqueue(
            'worker.process_socio_video',
            video_id,
            job_id=job_id,
            job_timeout='1h',    # 1 hora (videos de 60s max)
            result_ttl=86400,    # 24h
            failure_ttl=86400,   # 24h
            at_front=at_front,
            retry=Retry(max=3, interval=[30, 120, 300]),
            meta={'priority': priority, 'type': 'socio', 'video_id': video_id},
        )

        # Track de job activo por 2h para deduplicación de start_processing repetidos
        redis_conn = get_redis_connection()
        redis_conn.setex(_active_job_key(video_id), 7200, job.id)
        
        logger.info(f"📋 Video socio {video_id} encolado (prioridad={priority}) - Job ID: {job.id}")
        return job.id
        
    except Exception as e:
        logger.error(f"❌ Error encolando video socio {video_id}: {e}")
        return None


def get_job_status(job_id: str) -> dict:
    """
    Obtiene el estado de un trabajo en la cola.
    
    Args:
        job_id: ID del trabajo
        
    Returns:
        dict con: status, progress, result/error
    """
    try:
        from rq.job import Job
        redis_conn = get_redis_connection()
        
        job = Job.fetch(job_id, connection=redis_conn)
        
        return {
            'id': job.id,
            'status': job.get_status(),  # 'queued', 'started', 'finished', 'failed'
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'ended_at': job.ended_at.isoformat() if job.ended_at else None,
            'result': job.result if job.is_finished else None,
            'error': str(job.exc_info) if job.is_failed else None,
            'position': job.get_position() if job.is_queued else None
        }
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo estado de job {job_id}: {e}")
        return {'status': 'unknown', 'error': str(e)}


def get_queue_info() -> dict:
    """
    Obtiene información sobre el estado de la cola.
    
    Returns:
        dict con estadísticas de la cola
    """
    try:
        queue = get_video_queue()
        
        return {
            'name': queue.name,
            'count': len(queue),  # Videos en espera
            'started_jobs': queue.started_job_registry.count,
            'finished_jobs': queue.finished_job_registry.count,
            'failed_jobs': queue.failed_job_registry.count,
            'scheduled_jobs': queue.scheduled_job_registry.count
        }
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo info de cola: {e}")
        return {'error': str(e)}


def is_redis_available() -> bool:
    """Verifica si Redis está disponible"""
    try:
        redis_conn = get_redis_connection()
        redis_conn.ping()
        return True
    except Exception:
        return False


def can_enqueue_operational_analysis() -> tuple:
    """Valida si la cola operacional tiene capacidad para aceptar nuevos trabajos."""
    try:
        queue = get_video_queue()
        pending = len(queue)
        started = queue.started_job_registry.count
        allowed = pending < MAX_PENDING_OPERATIONAL_JOBS
        return allowed, {
            'pending_jobs': pending,
            'started_jobs': started,
            'max_pending_jobs': MAX_PENDING_OPERATIONAL_JOBS,
        }
    except Exception as e:
        return True, {
            'warning': f'queue_capacity_unknown: {e}'
        }
