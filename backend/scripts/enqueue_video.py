import sys
sys.path.insert(0, '/app')

from redis import Redis
from rq import Queue
import os

# Conectar a Redis
redis_url = os.getenv('REDIS_URL', 'redis://:myredispass@redis:6379/0')
conn = Redis.from_url(redis_url)

# Obtener cola
q = Queue('video_processing', connection=conn)

video_id = "b550b753-2e4a-46d5-95d2-af3ba14d8a75"

# Encolar job
from use_cases.video_processor import VideoProcessor
from infrastructure.dependencies import obtener_procesador

processor = obtener_procesador()

job = q.enqueue(
    'use_cases.video_processor.procesar_video_job',
    args=(video_id,),
    job_timeout='30m',
    result_ttl=500,
    job_id=f'video_processing_{video_id}'
)

print(f"✅ Video encolado en RQ:")
print(f"  Job ID: {job.id}")
print(f"  Estado: {job.get_status()}")
print(f"  Cola: {q.name}")
print(f"  Jobs pendientes: {len(q)}")
