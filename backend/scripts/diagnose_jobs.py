"""Script de diagnóstico: jobs fallidos, DLQ y videos atascados."""
import sys
import os
sys.path.insert(0, '/app')

from infrastructure.services.job_queue import get_redis_connection, get_dead_letter_entries
from rq import Queue
from rq.job import Job
from rq.registry import FailedJobRegistry

r = get_redis_connection()

# ── Jobs fallidos en RQ ─────────────────────────────────────────────────────
print("=== JOBS FALLIDOS EN RQ ===")
q = Queue('video_processing', connection=r)
failed_reg = FailedJobRegistry('video_processing', connection=r)
failed_ids = failed_reg.get_job_ids()
print(f"Total fallidos: {len(failed_ids)}")
for jid in failed_ids[:10]:
    try:
        job = Job.fetch(jid, connection=r)
        meta = job.meta or {}
        vid_id = meta.get('video_id', jid)
        exc = ""
        if job.exc_info:
            exc = str(job.exc_info)[-300:]
        print(f"\n  Job: {jid}")
        print(f"  Video: {vid_id}")
        print(f"  Error: {exc[:250]}")
    except Exception as ex:
        print(f"  Error fetching {jid}: {ex}")

# ── Dead Letter Queue ───────────────────────────────────────────────────────
print("\n=== DEAD LETTER QUEUE ===")
dlq = get_dead_letter_entries(10)
print(f"Entradas en DLQ: {len(dlq)}")
for e in dlq:
    vid = str(e.get('video_id', ''))
    err = str(e.get('error', ''))[:200]
    print(f"  video_id={vid}  error={err}")

# ── Videos atascados en Firestore ─────────────────────────────────────────
print("\n=== VIDEOS ATASCADOS EN FIRESTORE ===")
try:
    from infrastructure.dependencies import get_video_repository
    from domain.entities import EstadoVideo

    repo = get_video_repository()
    # Obtener todos los videos (limitado a primeros 50 para diagnóstico)
    # Usamos una query directa a Firestore
    from google.cloud import firestore
    db = firestore.Client()
    docs = db.collection('videos').where(
        filter=firestore.FieldFilter('estado', 'in', ['pendiente', 'procesando'])
    ).limit(20).stream()

    stuck = list(docs)
    print(f"Videos en pendiente/procesando: {len(stuck)}")
    for doc in stuck:
        data = doc.to_dict()
        vid_id = doc.id
        estado = data.get('estado', '?')
        usuario = data.get('usuario', '?')
        nombre = data.get('nombre_archivo', '?')
        fecha = str(data.get('fecha_creacion', '?'))[:19]
        print(f"  [{vid_id[:16]}] estado={estado} user={usuario} file={nombre} fecha={fecha}")

    if not stuck:
        docs2 = db.collection('videos').where(
            filter=firestore.FieldFilter('estado', 'in', ['PENDIENTE', 'PROCESANDO', 'pending', 'processing'])
        ).limit(20).stream()
        stuck2 = list(docs2)
        print(f"(Con estados en mayuscula/ingles): {len(stuck2)}")
        for doc in stuck2:
            data = doc.to_dict()
            print(f"  [{doc.id[:16]}] estado={data.get('estado')} user={data.get('usuario')}")

except Exception as ex:
    print(f"Error consultando Firestore: {ex}")

print("\n=== FIN DIAGNÓSTICO ===")
