# Architecture

## Overview

CU002 uses Clean Architecture: Flask blueprints expose HTTP APIs, use cases coordinate processing, domain entities hold business rules, and infrastructure provides local services.

## Local Stack

| Component | Responsibility |
|---|---|
| PostgreSQL + pgvector | Relational persistence and vector search |
| MinIO | S3-compatible video, frame, thumbnail, and report storage |
| Redis + RQ | Job queue, cache, rate-limit state, and progress events |
| vLLM | Local multimodal, text, and embedding inference |
| Whisper | Local audio transcription |
| OpenCV + ffmpeg | Motion detection, frame extraction, and media processing |

## Processing Flow

```
Frontend -> Flask API -> PostgreSQL / MinIO
                      -> Redis queue -> RQ worker
                                      -> vLLM, Whisper, OpenCV, ffmpeg
```

Workers persist progress and results to PostgreSQL, publish progress through Redis, and store media as `s3://` object URIs or `file://` filesystem URIs. The API serves authenticated media through application endpoints or generates MinIO signed URLs where appropriate.

## Layers

| Layer | Contents |
|---|---|
| `domain/` | Entities, states, and business invariants |
| `use_cases/` | Moderation, security, operational, audio, and workspace workflows |
| `infrastructure/adapters/` | MinIO, filesystem, vLLM gateway, Whisper, OpenCV, and ffmpeg adapters |
| `infrastructure/repositories/` | SQLAlchemy repositories |
| `infrastructure/services/` | Redis, RQ, cache, logging, reports, and cleanup |
| `infrastructure/web/` | Flask blueprints and authentication decorators |

## Operations

Docker Compose runs the frontend, backend, PostgreSQL, MinIO, Redis, RQ workers, vLLM services, and Whisper. See [OPERATIONS.md](OPERATIONS.md) for deployment variables and health checks.
