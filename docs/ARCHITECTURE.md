# Architecture

## Overview

TIVIT CU002 follows a **Clean Architecture** pattern on the backend, with a clear boundary between domain logic, use cases, and infrastructure. The frontend is a single-page application that communicates exclusively with the backend REST API.

## Architectural Layers (Backend)

```
+-------------------------------------------------------+
|  HTTP Layer  (infrastructure/web — Flask blueprints)  |
+-------------------------------------------------------+
|  Use Cases   (use_cases/ — orchestrators)             |
+-------------------------------------------------------+
|  Domain      (domain/entities.py — business rules)    |
+-------------------------------------------------------+
|  Infrastructure  (adapters, repositories, services)   |
+-------------------------------------------------------+
```

### Domain Layer

- `domain/entities.py` — All domain entities, enumerations, and business invariants.
- Pure Python with no framework dependencies.
- Entities: `Video`, `SecurityVideo`, `OperationalAnalysis`, `AudioAnalysis`, `Workspace`, `Usuario`.
- Business rule enforcement at construction time via `__post_init__` and state machine methods.

### Use Cases Layer

Orchestrates domain entities and infrastructure adapters to fulfill one business operation each.

| Use Case | Responsibility |
|----------|---------------|
| `video_processor.py` | Standard video moderation pipeline |
| `security_video_processor.py` | Surveillance video upload and trigger |
| `complete_security_processor.py` | Full surveillance analysis (motion detection, segmentation, Gemini analysis, report) |
| `operational_analyzer.py` | Operational process analysis pipeline (dense scan + Gemini + report) |
| `audio_analyzer.py` | Audio/video transcription pipeline |
| `security_query_engine.py` | Natural language queries over indexed security events |
| `socio_video_service.py` | Video moderation service for standard uploads |

### Infrastructure Layer

#### Adapters

| Adapter | GCP Service |
|---------|-------------|
| `gcp_storage.py` | Cloud Storage |
| `gcp_firestore.py` | Firestore |
| `gcp_speech.py` | Speech-to-Text |
| `gcp_video_intelligence.py` | Video Intelligence API |
| `gemini_adapter.py` | Gemini (google-genai SDK) |
| `cloud_tasks_adapter.py` | Cloud Tasks |
| `opencv_motion_detector.py` | OpenCV (local, headless) |
| `video_segmentation.py` | ffmpeg-based segmentation |

#### Repositories

All repositories persist to Firestore. Each repository maps one Firestore collection.

| Repository | Firestore Collection |
|------------|---------------------|
| `video_repository.py` | `videos` |
| `security_video_repository.py` | `security_videos`, `security_events` |
| `operational_analysis_repository.py` | `operational_analyses`, `operational_events` |
| `audio_analysis_repository.py` | `audio_analyses` |
| `workspace_repository.py` | `workspaces` |
| `user_repository.py` | `users` |

#### Services

Cross-cutting concerns that are not business logic:

| Service | Responsibility |
|---------|---------------|
| `logging_service.py` | Centralized structured logging; redirects `print()` in production |
| `security_logger.py` | Dedicated rotating logger for the security analysis pipeline |
| `gcp_observability.py` | Cloud Trace (OpenTelemetry), Cloud Profiler, Cloud Monitoring |
| `job_queue.py` | RQ queue connection and job enqueue helpers |
| `redis_cache.py` | Redis cache instance (analysis results) |
| `analysis_cache_manager.py` | TTL-based cache for completed analyses |
| `rate_limiter.py` | Flask-Limiter configuration (Redis-backed) |
| `notification_service.py` | SMTP email notifications |
| `multipart_upload_service.py` | Multipart upload coordination |
| `resumable_upload_service.py` | GCS resumable upload URL generation |
| `gcs_service.py` | Signed URL generation for direct-to-GCS uploads |
| `cleanup_service.py` | Expired resource cleanup |
| `firestore_ttl.py` | Firestore document TTL management |

#### HTTP Layer

Flask blueprints, one per domain area. All JSON APIs; no server-side rendering.

| Blueprint | URL Prefix | Domain |
|-----------|-----------|--------|
| `app_auth.py` | `/api/auth` | Authentication |
| `app_socio.py` | `/` | Standard video moderation |
| `app_upload.py` | `/api/v1/videos` | Signed URL video upload |
| `app_security.py` | `/api/security` | Surveillance video |
| `app_operational.py` | `/api/operational` | Operational analysis |
| `app_audio.py` | `/api/audio` | Audio transcription |
| `app_workspaces.py` | `/workspaces` | Workspace management |
| `app_workspace_chat.py` | `/workspaces` | AI context validation chat |
| `api_v1.py` | `/api/v1` | Versioned REST API |

## Async Processing

Heavy workloads (video analysis, transcription, report generation) are processed asynchronously to avoid HTTP timeout.

```
HTTP Request          Redis Queue           RQ Worker
     |                     |                     |
     | POST /upload/init   |                     |
     +-------------------->|                     |
     | 202 Accepted        |                     |
     |<--------------------| enqueue(task)       |
     |                     +-------------------->|
     |                     |                     | process()
     |                     |                     | write to Firestore
     |                     |                     |
     | GET /status         |                     |
     +-------------------->|                     |
     | {status: completed} |                     |
     |<--------------------|                     |
```

One RQ worker service (`worker`) runs alongside the backend. It can be scaled horizontally with `docker compose up --scale worker=N`.

Cloud Tasks is used as an alternative trigger mechanism for production webhook-style job dispatch.

## Frontend Architecture

- **Routing**: TanStack Router v1 with file-based type-safe routes (`router.tsx`).
- **Data fetching**: TanStack Query v5; queries invalidated on mutations.
- **Auth state**: React Context (`AuthContext`) wrapping the router.
- **Component library**: Radix UI primitives styled with Tailwind CSS v4.
- **Animation**: Framer Motion.
- **Charts**: Recharts.
- **Video client processing**: `@ffmpeg/ffmpeg` (WASM) for client-side pre-processing where needed.
- **Build**: Vite 7 with manual chunk splitting (`vendor-tanstack`, `vendor-viz`, `vendor-ffmpeg`).

### GCP Credentials

The backend resolves GCP credentials in the following priority order:

1. **`GCP_CREDENTIALS_B64`** — Base64-encoded service account JSON injected as an environment variable (via Secret Manager). Decoded at startup into a temporary file with `0o600` permissions.
2. **`GCP_CREDENTIALS_JSON`** — Raw JSON string.
3. **`GOOGLE_APPLICATION_CREDENTIALS` / ADC** — If neither variable is set, the GCP SDK uses Application Default Credentials. In local development this resolves to an OAuth user token obtained via `gcloud auth application-default login`.

**ADC limitation**: OAuth user tokens do not contain a service account private key. Operations that require RSA signing — specifically GCS Signed URL generation — are unavailable in this credential mode. Endpoints that previously generated Signed URLs now delegate to the server-side GCS streaming proxy described below.

### GCS Streaming Proxy

Video playback is served via a server-side proxy endpoint (`GET /socio/media/<video_id>`) rather than GCS Signed URLs. The proxy:

- Authenticates the request via session cookie.
- Validates resource ownership before accessing GCS (IDOR prevention).
- Reads the HTTP `Range` header and passes `start`/`end` byte offsets to `blob.download_as_bytes()`.
- Streams content in 1 MB chunks, returning `206 Partial Content` for range requests.

This pattern eliminates the private key dependency and works identically across local (ADC) and production (service account) credential modes.

## Project Configuration

| Resource | Legacy GCP (deshabilitado local) | Local Offline 32B (`APP_ENV=local`) |
|----------|----------------------------------|--------------------------------------|
| Project ID | `tivit-cu002-prd` / `tivit-mira-prd` | `cu002-local` (`AppConfig.GCP_PROJECT_ID`, solo compat) |
| Region | `us-central1` | `us-central1` (no usado) |
| Storage | GCS `tivit-cu002-prd-videos` | MinIO `s3://cu002-videos` (`S3_ENDPOINT=http://minio:9000`) o `filesystem ./uploads` |
| Database | Firestore Native | Postgres 16 + pgvector (`DATABASE_URL`) o SQLite fallback |
| AI | Gemini `gemini-2.5-flash` Vertex AI | vLLM `Qwen2.5-VL-32B-AWQ` TP4 (`AI_LOCAL_BASE_URL`) + Whisper `large-v3-turbo` + `bge-m3` |

Ver `docs/OPERATIONS.md` y `config/app_config.py` para feature flags `STORAGE_BACKEND/DB_BACKEND/AI_PROVIDER`.

## Storage Lifecycle Policy

> **Local:** MinIO ILM `mc ilm add --expiry-days 7 --prefix 'tmp/'` (ver `docker-compose.local.yml:minio-setup`). `config/lifecycle.json` legacy GCP solo.



| Age | Storage class | Approximate cost |
|-----|--------------|-----------------|
| 0-30 days | STANDARD | Baseline |
| 30-90 days | NEARLINE | ~50% saving |
| 90+ days | COLDLINE | ~70% saving |
| Temp objects | Deleted after 7 days | - |

Lifecycle rules are applied via `config/lifecycle.json` and managed by `firestore_ttl.py`.

---

**Last Updated**: May 15, 2026  
**Version**: 3.3.0
