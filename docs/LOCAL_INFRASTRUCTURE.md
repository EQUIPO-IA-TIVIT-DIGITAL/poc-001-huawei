# Infraestructura Local

TIVIT CU002 funciona sin servicios cloud gestionados. El despliegue completo usa PostgreSQL con pgvector, MinIO, Redis + RQ, vLLM, Whisper y contenedores propios para backend y frontend.

## Requisitos

- Docker Engine y Docker Compose v2
- GPU NVIDIA con Container Toolkit para habilitar el perfil `gpu`
- Modelos ya disponibles en el volumen `models` si se opera sin acceso a Internet

## Variables Requeridas

Defina estas variables en el entorno antes de iniciar el stack:

```bash
export POSTGRES_PASSWORD='cambie-esta-clave'
export MINIO_ROOT_USER='cambie-este-usuario-minio'
export MINIO_ROOT_PASSWORD='cambie-esta-clave-larga'
export SECRET_KEY='cambie-esta-clave-de-aplicacion'
export REDIS_PASSWORD='cambie-esta-clave-redis'
```

Variables opcionales: `POSTGRES_DB`, `POSTGRES_USER`, `S3_BUCKET`, `AI_PROVIDER` y `CORS_ORIGIN`.

## Arranque

Sin GPU, se inician PostgreSQL, MinIO, Redis, backend, worker y frontend:

```bash
docker compose -f docker-compose.local.yml up -d --build
```

Con IA local en GPU:

```bash
docker compose -f docker-compose.local.yml --profile gpu up -d --build
```

El frontend queda en `http://localhost:5173`, el backend en `http://localhost:5001`, MinIO en `http://localhost:9001` y PostgreSQL queda limitado a `127.0.0.1:5432`.

## Persistencia

- PostgreSQL crea las tablas del modelo SQLAlchemy durante el arranque. Las migraciones Alembic cubren actualizaciones de instalaciones existentes.
- MinIO crea el bucket principal de forma idempotente desde el adapter al arrancar el backend. El servicio `minio-setup` es opcional (perfil `setup`) y solo crea buckets adicionales o reglas de ciclo de vida.
- Redis respalda las colas RQ y el estado temporal de trabajos.
- Los videos se identifican con URIs `s3://` o rutas `file://`; las respuestas HTTP usan `storage_path`, `storage_uri`, `video_url`, `audio_url` y `full_transcription_url`.

## Operación

- Los trabajos se encolan con Redis + RQ y se procesan en el contenedor `worker`.
- La IA local se sirve mediante APIs compatibles con OpenAI desde vLLM y Whisper.
- Para una API de IA externa opcional, configure `AI_PROVIDER=hybrid`, `AI_API_PROVIDER=openrouter`, `AI_API_BASE_URL=https://openrouter.ai/api/v1`, `AI_API_KEY`, `AI_API_TEXT_MODEL` y `AI_API_VISION_MODEL`. En `hybrid`, vLLM local responde primero y la API comercial queda como fallback.
