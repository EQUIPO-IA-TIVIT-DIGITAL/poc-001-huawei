"""
Script para re-encolar todos los videos atascados en estado pendiente/procesando.
También permite forzar eliminación de videos atascados si se pasa --delete.
"""
import sys
import os
sys.path.insert(0, '/app')

from google.cloud import firestore
from infrastructure.services.job_queue import enqueue_socio_video

db = firestore.Client()
DELETE_MODE = '--delete' in sys.argv

print(f"Modo: {'ELIMINAR' if DELETE_MODE else 'RE-ENCOLAR'}")
print()

# Obtener videos atascados
docs = db.collection('videos').where(
    filter=firestore.FieldFilter('estado', 'in', ['pendiente', 'procesando', 'PENDIENTE', 'PROCESANDO'])
).limit(50).stream()

stuck = list(docs)
print(f"Videos atascados encontrados: {len(stuck)}")

if not stuck:
    print("No hay videos atascados.")
    sys.exit(0)

for doc in stuck:
    data = doc.to_dict()
    vid_id = doc.id
    estado = data.get('estado', '?')
    usuario = data.get('usuario', '?')
    nombre = data.get('nombre_archivo', '?')
    ruta = data.get('ruta_archivo', '')
    fecha = str(data.get('fecha_creacion', '?'))[:19]

    print(f"\n  [{vid_id[:16]}] estado={estado} user={usuario} file={nombre} fecha={fecha}")

    if DELETE_MODE:
        # Eliminar de Firestore
        db.collection('videos').document(vid_id).delete()
        # Intentar eliminar archivo local si existe
        if ruta and os.path.exists(ruta):
            try:
                os.remove(ruta)
                print(f"    → Archivo local eliminado: {ruta}")
            except Exception as e:
                print(f"    → No se pudo eliminar archivo local: {e}")
        print(f"    → Video eliminado de Firestore")
    else:
        # Re-encolar para procesamiento
        # Verificar si el archivo local existe
        if ruta and os.path.exists(ruta):
            job_id = enqueue_socio_video(vid_id, priority=0)
            if job_id:
                print(f"    → Re-encolado OK: job={job_id[:20]}")
            else:
                print(f"    → ERROR al encolar")
        else:
            print(f"    → Archivo local NO existe: {ruta}")
            print(f"    → Este video no puede procesarse (archivo perdido)")
            if not DELETE_MODE:
                print(f"    → Ejecuta con --delete para limpiar de la BD")

print("\n=== LISTO ===")
