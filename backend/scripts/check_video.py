#!/usr/bin/env python3
"""Script temporal para verificar estado de video"""
import sys
import os
import json
sys.path.insert(0, '/app')

from google.cloud import firestore
from config.gcp_config import GCPConfig

def convert_firestore_data(obj):
    """Convertir objetos Firestore a tipos serializables"""
    if isinstance(obj, dict):
        return {k: convert_firestore_data(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_firestore_data(item) for item in obj]
    elif hasattr(obj, 'isoformat'):  # datetime objects
        return obj.isoformat()
    return obj

db = firestore.Client(project=GCPConfig().PROJECT_ID)
doc = db.collection('videos').document('b550b753-2e4a-46d5-95d2-af3ba14d8a75').get()
d = doc.to_dict()

print(f"Estado: {d.get('estado')}")
print(f"Confianza: {d.get('confianza_ia')}")
print(f"Error: {d.get('mensaje_error')}")
print(f"Actualizado: {d.get('actualizado_en')}")
print(f"\nMetadatos IA:")
if d.get('metadatos_ia'):
    metadatos = convert_firestore_data(d.get('metadatos_ia'))
    print(json.dumps(metadatos, indent=2))
else:
    print("  (sin datos)")
