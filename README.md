# TIVIT CU002

Enterprise platform for intelligent video management and moderation, powered by multimodal AI.

## Overview

TIVIT CU002 is an automated video moderation and analysis system that evaluates visual, audio, and operational content on infrastructure under the operator's control. It uses OpenCV, vLLM-compatible vision and text models, Whisper, PostgreSQL, MinIO, and Redis + RQ.

## Documentation

Extended technical documentation is available in the [docs](docs/README.md) folder:

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System design and components |
| [API Reference](docs/API.md) | Complete HTTP API documentation |
| [Operations & Deployment](docs/OPERATIONS.md) | Setup and configuration |
| [Local Infrastructure](docs/LOCAL_INFRASTRUCTURE.md) | Required variables and Docker Compose local stack |
| [Security & Compliance](docs/SECURITY_AND_COMPLIANCE.md) | Security controls and best practices |
| [Module: Workspaces](docs/MODULE_WORKSPACES.md) | Multi-project organization, soft delete, audit log |
| [Module: Audio Analysis](docs/MODULE_AUDIO_ANALYSIS.md) | Transcription pipeline, speaker diarization, AI summary, semantic Q&A |
| [Module: Operational Analysis](docs/MODULE_OPERATIONAL_ANALYSIS.md) | Operational process analysis pipeline, analysis types, events, PDF report |

## System Modules

| Module | Description |
|--------|-------------|
| **Video Moderation** | Visual analysis with local vision models, explicit content detection, OCR, and logo recognition |
| **Security** | Surveillance video processing with event detection, temporal indexing, and natural language queries |
| **Operational** | Operational process analysis with heatmaps, comparisons, and efficiency metrics |
| **Audio** | Automatic transcription with Whisper, local speaker processing, AI-generated summary, and timestamped semantic Q&A |
| **Workspaces** | Multi-project organization system with contextual AI chat per workspace |
| **Administration** | Complete dashboard with analytics, user management, manual moderation, and reports |

## Tech Stack

### Backend

| Technology | Version |
|------------|---------|
| Python | 3.11+ |
| Flask | 3.x |
| PostgreSQL + pgvector | 16 / 0.3+ |
| MinIO | S3-compatible local storage |
| vLLM | Local multimodal and text models |
| Whisper | Local transcription API |
| Redis + RQ | 5.x / 1.15+ |
| OpenCV (headless) | 4.8+ |
| ReportLab | 4.x |
| Gunicorn + gevent | (production) |

### Frontend

| Technology | Version |
|------------|---------|
| React | 19.x |
| TypeScript (strict) | 5.x |
| Vite | 7.x |
| TanStack Router | 1.142+ |
| TanStack Query | 5.90+ |
| Tailwind CSS | 4.x |
| Framer Motion | 12.x |
| Recharts | 3.6+ |
| Radix UI | 1.1+ |

### Infrastructure

| Service | Purpose |
|---------|---------|
| Docker Compose | Local development and deployment |
| PostgreSQL + pgvector | Relational data and vector search |
| MinIO | Video and asset storage |
| Redis + RQ | Asynchronous jobs and rate limiting |
| vLLM + Whisper | Local AI inference |
| GitHub Actions | CI pipeline (lint + security audit) |
| Redis | Async job queue and rate limiting |

## Architecture

```
                          +-----------------+
                          |    Internet     |
                          +--------+--------+
                                   |
                     +-------------+-------------+
                     |                           |
              +------+------+            +-------+------+
               |  Frontend   |            |  Backend     |
               |  (Nginx)    +----------->+  (Flask)     |
              +-------------+            +------+-------+
                                                |
                               +----------------+-----------------+
                               |                |                 |
                        +------+------+   +-----+------+  +------+------+
                         | PostgreSQL  |   | MinIO      |  |   Redis     |
                         | + pgvector  |   | (storage)  |  |  (Queue)    |
                        +-------------+   +------------+  +------+------+
                                                                  |
                                                           +------+------+
                                                           |  RQ Workers |
                                                           +-------------+
```

## Project Structure

```
tivit-cu002/
+-- backend/
|   +-- main.py                     # Flask app entry point + blueprint registration
|   +-- worker.py                   # RQ worker for async video processing
|   +-- Dockerfile.backend          # Backend production image
|   +-- Dockerfile.worker           # RQ worker image
|   +-- requirements.in / .txt      # Python dependencies (compiled with pip-tools)
|   +-- config/                     # Local configuration and blacklist
|   +-- domain/
|   |   +-- entities.py             # Domain entities and business rules
|   +-- use_cases/                  # Business logic orchestrators
|   |   +-- socio_video/            # Moderation pipeline (5 steps)
|   |   +-- security/               # Security analysis
|   |   +-- operational/            # Operational analysis
|   |   +-- realtime/               # RTSP streaming
|   +-- infrastructure/
|   |   +-- adapters/               # Local AI, MinIO, Whisper and OpenCV adapters
|   |   +-- repositories/           # SQLAlchemy repositories (single source of truth)
|   |   +-- services/               # Cross-cutting services (cache, observability, logging)
|   |   +-- web/                    # HTTP layer (9 blueprints)
|   +-- alembic/                    # Database migrations
|   +-- tests/                      # pytest suite (config, repositories, auth)
+-- frontend/
|   +-- src/
|       +-- main.tsx
|       +-- router.tsx              # TanStack Router routes
|       +-- pages/                  # Application pages
|       +-- components/             # Reusable UI components
|       +-- context/                # Context providers (Auth)
|       +-- services/               # API clients
|       +-- layouts/                # Application layouts
|       +-- lib/                    # Shared utilities
|   +-- package.json                # Scripts: dev, build, lint, test (tsc + vitest)
+-- docs/                           # Technical documentation
+-- .github/workflows/              # GitHub Actions (CI: lint + tests + security audit)
+-- docker-compose.yml              # Minimal dev stack (SQLite/filesystem)
+-- docker-compose.local.yml        # Full local stack (PostgreSQL, MinIO, profiles)
+-- .env.example                    # Environment variable reference
```

## Tests And Quality

```bash
# Backend (28 tests: config, repositories, pagination, auth)
cd backend
pip install pip-tools
pip-compile requirements.in -o requirements.txt
pip-compile requirements-dev.in -o requirements-dev.txt
pip install -r requirements-dev.txt
pytest
flake8 .

# Frontend (test = typecheck + vitest unit tests)
cd ../frontend
npm ci
npm test
npm run test:unit        # unit tests only (vitest)
npm run lint
npm run build
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Docker-compatible host with sufficient CPU, memory, and GPU capacity for the selected vLLM models

### Local Setup

```bash
# Clone the repository
git clone https://github.com/EQUIPO-IA-TIVIT-DIGITAL/poc-001-huawei.git
cd poc-001-huawei

# Copy and configure environment variables
cp .env.example .env
# Edit .env and fill in the required values
```

#### Execution Profiles

| Profile | Command | Includes |
|---------|---------|----------|
| **Base (CPU, no AI)** | `docker compose -f docker-compose.local.yml up -d --build` | PostgreSQL + pgvector, MinIO, Redis, backend, worker, frontend |
| **Full (GPU, local AI)** | `docker compose -f docker-compose.local.yml --profile gpu up -d --build` | Base + vLLM vision (Qwen2.5-VL-32B-AWQ), vLLM text (Qwen2.5-32B-AWQ), Whisper |

Notes:

- The GPU profile requires an NVIDIA host with the nvidia container runtime and at least 8 GPUs (2× TP4 groups) plus ~200 GB for the models volume. Pre-pull models offline with `backend/scripts/pull_models.sh`.
- Without `--profile gpu`, the backend starts correctly but local AI and Whisper are **not** available. Set `AI_PROVIDER=api` (with `AI_API_BASE_URL`/`AI_API_KEY`) or `AI_PROVIDER=disabled` in `.env` accordingly.
- Optional helpers: `--profile setup` (creates MinIO buckets) and `--profile pool` (pgBouncer).
- Run Alembic migrations after the database is up: `docker compose -f docker-compose.local.yml exec backend alembic upgrade head`.

### Development Services

| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:5173 | React application (Vite Dev Server) |
| Backend | http://localhost:5001 | Flask API |
| Redis | localhost:6379 | Job queue (internal only) |
| Workers | - | RQ worker for async processing (scalable with `--scale worker=N`) |

Health probes: `/health` and `/livez` are lightweight process checks; `/readyz` validates configured database and storage dependencies; `/startupz` confirms basic application startup.

### Required Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | Yes | - | Flask session secret key (min. 64 chars) |
| `REDIS_PASSWORD` | Yes | - | Redis password |
| `DATABASE_URL` | Yes | - | PostgreSQL connection URL |
| `S3_ENDPOINT` | Yes | `http://minio:9000` | MinIO S3 endpoint |
| `S3_BUCKET` | No | `cu002-videos` | MinIO bucket |
| `AI_PROVIDER` | No | `hybrid` | `local`, `api`, `hybrid`, or `disabled` |
| `AI_LOCAL_BASE_URL` | No | `http://vllm-vision:8000/v1` | vLLM vision endpoint |
| `AI_API_PROVIDER` | No | `openrouter` | Commercial OpenAI-compatible provider |
| `AI_API_BASE_URL` | No | `https://openrouter.ai/api/v1` | Optional commercial API fallback |
| `AI_API_KEY` | Only with `AI_PROVIDER=api` | - | Commercial API key |
| `WHISPER_BASE_URL` | No | `http://whisper:8001/v1` | Whisper endpoint |
| `CORS_ORIGIN` | No | `http://localhost` | Allowed CORS origin |
| `VITE_API_BASE_URL` | No | `http://localhost:5001` | Backend URL for the frontend |

See [.env.example](.env.example) for the full list of configurable variables.

## CI Pipeline

The project uses **GitHub Actions** for continuous integration on every push and pull request.

| Workflow | Trigger | Jobs |
|----------|---------|------|
| `ci.yml` | Push (non-main) / PR to main | Backend lint (flake8), Frontend lint (ESLint + tsc) |
| `security-audit.yml` | Push to main/develop, weekly | pip-audit, npm audit, bandit (SAST), Trivy |

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Organization

**TIVIT S.A.** - Brazilian multinational leader in digital transformation and enterprise IT solutions.

## Engineering Lead

- **Name**: Manuel Juda Aliaga Aliaga
- **Email**: manuel.aliaga@tivit.com
- **Location**: Lima, Peru
