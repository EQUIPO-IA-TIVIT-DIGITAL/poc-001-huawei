#!/usr/bin/env python3
"""Script para limpiar cache de un video específico y reprocesarlo"""
import sys
sys.path.insert(0, '/app')

import redis
from google.cloud import firestore
from config.gcp_config import GCPConfig
from infrastructure.services.job_queue import enqueue_socio_video

VIDEO_ID = 'b550b753-2e4a-46d5-95d2-af3ba14d8a75'
VIDEO_HASH = '9297e5b9c96eded20c2dc63c4cc84152346b9b3e8aeddeb6facd3adaf7070d2a'

# Conectar a Redis
redis_client = redis.Redis(
    host='redis',
    port=6379,
    password='***REMOVED***',
    decode_responses=True
)

# Limpiar cache de Redis para este video
cache_keys = [
    f'video_analysis:{VIDEO_HASH}',
    f'video_analysis:{VIDEO_ID}',
    f'video_metadata:{VIDEO_HASH}',
    f'video_metadata:{VIDEO_ID}',
]

deleted = 0
for key in cache_keys:
    if redis_client.delete(key):
        deleted += 1
        print(f"🗑️  Cache eliminado: {key}")

print(f"✅ {deleted} entradas de cache eliminadas")

# Limpiar metadatos y resetear estado en Firestore
db = firestore.Client(project=GCPConfig().PROJECT_ID)
doc_ref = db.collection('videos').document(VIDEO_ID)

updates = {
    'estado': 'pendiente',
    'metadatos_ia.error': firestore.DELETE_FIELD,
    'metadatos_ia.error_procesamiento': firestore.DELETE_FIELD,
    'metadatos_ia.decision_gemini': firestore.DELETE_FIELD,
    'metadatos_ia.analisis_ia': firestore.DELETE_FIELD,
    'metadatos_ia.razon_decision': firestore.DELETE_FIELD,
    'metadatos_ia.resultado_ia': firestore.DELETE_FIELD,
    'metadatos_ia.fecha_procesamiento': firestore.DELETE_FIELD,
}

doc_ref.update(updates)
print(f"✅ Video {VIDEO_ID} reseteado a pendiente (metadatos limpiados)")

# Re-encolar
job_id = enqueue_socio_video(VIDEO_ID, priority=0)
print(f"✅ Video encolado con job_id: {job_id}")
print(f"🎬 El video será procesado SIN CACHE - ejecutará Gemini Vision real")
