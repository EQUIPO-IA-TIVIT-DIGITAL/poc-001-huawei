#!/usr/bin/env python3
"""Script para resetear un video y volver a procesarlo"""
import sys
sys.path.insert(0, '/app')

from google.cloud import firestore
from config.gcp_config import GCPConfig
from infrastructure.services.job_queue import enqueue_socio_video

VIDEO_ID = 'b550b753-2e4a-46d5-95d2-af3ba14d8a75'

db = firestore.Client(project=GCPConfig().PROJECT_ID)
doc_ref = db.collection('videos').document(VIDEO_ID)

# Limpiar errores y resetear estado
updates = {
    'estado': 'pendiente',
    'metadatos_ia.error': firestore.DELETE_FIELD,
    'metadatos_ia.error_procesamiento': firestore.DELETE_FIELD,
    'metadatos_ia.decision_gemini': firestore.DELETE_FIELD,
    'metadatos_ia.analisis_ia': firestore.DELETE_FIELD,
    'metadatos_ia.razon_decision': firestore.DELETE_FIELD,
    'metadatos_ia.resultado_ia': firestore.DELETE_FIELD,
}

doc_ref.update(updates)
print(f"✅ Video {VIDEO_ID} reseteado a pendiente")

# Re-encolar
job_id = enqueue_socio_video(VIDEO_ID, priority=0)
print(f"✅ Video encolado con job_id: {job_id}")
