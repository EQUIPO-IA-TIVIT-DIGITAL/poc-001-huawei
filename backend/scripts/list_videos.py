import os, sys
sys.path.insert(0, '/app')
os.chdir('/app')

from google.cloud import firestore
db = firestore.Client()
videos = list(db.collection('videos').limit(5).stream())
print(f'Total videos: {len(videos)}')
for v in videos:
    d = v.to_dict()
    estado = d.get('estado', 'N/A')
    titulo = d.get('titulo', 'N/A')
    gcs = d.get('metadatos_ia', {}).get('gcs_uri', 'N/A')
    confianza = d.get('analisis_ia', {}).get('confianza', 0)
    print(f'  ID: {v.id}')
    print(f'  Estado: {estado}')
    print(f'  Titulo: {titulo}')
    print(f'  GCS URI: {gcs}')
    print(f'  Confianza IA: {confianza}%')
    print()
