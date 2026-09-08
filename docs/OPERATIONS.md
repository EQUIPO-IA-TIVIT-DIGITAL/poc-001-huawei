# Operations — CU002 Local Offline 32B

**Stack:** Ubuntu 22.04 / 32vCPU 256GiB 8×Tesla CUDA 12.2 / Postgres 16+pgvector / MinIO 4-disk / vLLM 32B (Qwen2.5-VL-32B-AWQ TP4 + Qwen2.5-32B-AWQ TP4) / faster-whisper large-v3-turbo / Redis 7

## Quick Start

```bash
cp .env.example .env
# Edita .env: SECRET_KEY (>=64 chars), MINIO_ROOT_PASSWORD, POSTGRES_PASSWORD, REDIS_PASSWORD
# Opcional: AI_API_BASE_URL/AI_API_KEY si usas ApiLLM remota (offline funciona sin esto)

# 1. Pull modelos 32B (una vez con internet, ~70GB en volumen models)
bash scripts/pull_models.sh

# 2. Levantar stack 9 servicios
docker compose -f docker-compose.local.yml up -d --build
docker compose -f docker-compose.local.yml ps
# Espera healthchecks: postgres -> minio -> vllm-vision (120s) -> vllm-text (90s) -> backend

# 3. Migraciones
docker compose -f docker-compose.local.yml exec backend alembic upgrade head

# 4. Verificar
curl -f http://localhost:5001/health
curl -f http://localhost:5001/api/v1/status/ai   # {local:healthy, api:degraded si offline}
curl -f http://localhost:9000/minio/health/live  # MinIO
curl -f http://localhost:8000/health             # vLLM Vision 32B
curl -f http://localhost:8002/health             # vLLM Text 32B
# Frontend
open http://localhost:5173
```

## Variables Clave (.env)

| Var | Default | Nota |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://cu002:cu002-secret@postgres:5432/cu002` | PGBouncer `transaction` pool 25 |
| `STORAGE_BACKEND` | `minio` (`filesystem` fallback si no hay S3_ENDPOINT) | `s3://cu002-videos/videos/<id>.mp4` |
| `AI_PROVIDER` | `hybrid` (`local` primero, fallback `api`) | `disabled` desactiva IA |
| `AI_LOCAL_BASE_URL` | `http://vllm-vision:8000/v1` | Qwen2.5-VL-32B-AWQ TP4 |
| `VLLM_TENSOR_PARALLEL_SIZE` | `4` | 8 GPUs: vision 0-3, text 4-7 |
| `WHISPER_BASE_URL` | `http://whisper:8001/v1` | large-v3-turbo |

## Servicios y Puertos

| Servicio | Puerto | Health | Notas |
|---|---|---|---|
| frontend (nginx) | 5173:8080 | `curl :5173` | `env.js` runtime para `VITE_API_BASE_URL` |
| backend (gunicorn gthread 4×8) | 5001:5000 | `/health` | `/health/full` requiere session |
| postgres+pgvector | 5432 | `pg_isready` | `pgdata` volume, `pgBackRest` nightly a MinIO |
| minio | 9000/9001 | `/minio/health/live` | console :9001, buckets `cu002-videos` `cu002-thumbs` |
| redis | 6379 | `ping` | `REDIS_PASSWORD` requerido |
| vllm-vision 32B | 8000 | `/health` | 120s start, `AWQ` 20GB |
| vllm-text 32B | 8002 | `/health` | 90s start |
| whisper | 8001 | `/` | `large-v3-turbo` |

Escalar workers: `docker compose -f docker-compose.local.yml up -d --scale worker=4`

## Modelos Offline

```bash
# scripts/pull_models.sh descarga a volumen models (requiere internet)
huggingface-cli download Qwen/Qwen2.5-VL-32B-Instruct-AWQ --local-dir /models/Qwen2.5-VL-32B-Instruct-AWQ
huggingface-cli download Qwen/Qwen2.5-32B-Instruct-AWQ --local-dir /models/Qwen2.5-32B-Instruct-AWQ
# bge-m3 y whisper se cachean en hf_cache/whisper_models
# Luego exporta offline: docker volume export, o deja hf_cache persistente
```

## Troubleshooting

- **vLLM OOM 8×16GB:** baja a `VLLM_TENSOR_PARALLEL_SIZE=8` y `--quantization awq`, o usa `Qwen2.5-VL-7B-AWQ` (`AI_LOCAL_MODEL` env).
- **V100 sm70:** añade `VLLM_ATTENTION_BACKEND=FLASH_ATTN_V100` (ya en compose) y usa imagen `1Cat` si vLLM oficial falla: `1cat/vllm:1.2.0-cuda12.8`.
- **Postgres pgvector no existe:** `CREATE EXTENSION vector;` + `alembic upgrade head`.
- **Nvidia runtime no encontrado:** `sudo apt install nvidia-container-toolkit && sudo systemctl restart docker`.

## Logs y Observabilidad

```bash
docker compose -f docker-compose.local.yml logs -f backend worker vllm-vision
# OTel local (opcional): otel-collector -> prometheus:9090 grafana:3000 loki:3100
```

## Seguridad

- Rotar `SECRET_KEY` (>=64 chars), `MINIO_ROOT_PASSWORD`, `POSTGRES_PASSWORD` en `.env` real.
- `AZURE_*` deshabilitado local; `SECRET_KEY` requerido en prod.
- `gitleaks` + `trivy` en CI `security-audit.yml` weekly.
