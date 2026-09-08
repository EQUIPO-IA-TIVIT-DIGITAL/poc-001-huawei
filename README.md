# TIVIT CU002

Enterprise platform for intelligent video management and moderation, powered by multimodal AI.

## Overview

TIVIT CU002 is an automated video content moderation and analysis system that leverages multiple AI services to evaluate visual, audio, and operational content. It integrates Google Cloud Video Intelligence API, Gemini Vision, Speech-to-Text, and language models to provide contextual evaluation, automated moderation workflows, and real-time security analysis.

## Documentation

Extended technical documentation is available in the [docs](docs/README.md) folder:

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System design and components |
| [API Reference](docs/API.md) | Complete HTTP API documentation |
| [Operations & Deployment](docs/OPERATIONS.md) | Setup and configuration |
| [Security & Compliance](docs/SECURITY_AND_COMPLIANCE.md) | Security controls and best practices |
| [Module: Workspaces](docs/MODULE_WORKSPACES.md) | Multi-project organization, soft delete, audit log |
| [Module: Audio Analysis](docs/MODULE_AUDIO_ANALYSIS.md) | Transcription pipeline, speaker diarization, AI summary, semantic Q&A |
| [Module: Operational Analysis](docs/MODULE_OPERATIONAL_ANALYSIS.md) | Operational process analysis pipeline, analysis types, events, PDF report |

## System Modules

| Module | Description |
|--------|-------------|
| **Video Moderation** | Visual analysis with Gemini Vision, explicit content detection, OCR, and logo recognition |
| **Security** | Surveillance video processing with event detection, temporal indexing, and natural language queries |
| **Operational** | Operational process analysis with heatmaps, comparisons, and efficiency metrics |
| **Audio** | Automatic transcription with Speech-to-Text V2/V1, Gemini speaker diarization, AI-generated summary, and timestamped semantic Q&A |
| **Workspaces** | Multi-project organization system with contextual AI chat per workspace |
| **Administration** | Complete dashboard with analytics, user management, manual moderation, and reports |

## Tech Stack

### Backend

| Technology | Version |
|------------|---------|
| Python | 3.11+ |
| Flask | 3.x |
| Google Cloud Firestore | 2.14+ |
| Google Cloud Storage | 2.14+ |
| Google Cloud Video Intelligence | 2.11+ |
| Google Cloud Speech-to-Text | 2.21+ |
| Google Generative AI (Gemini) | 1.x |
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
| Google Cloud Run | Serverless containers (backend + frontend) |
| Artifact Registry | Docker image registry |
| Cloud Storage | Video and asset storage |
| Firestore | NoSQL database |
| Secret Manager | Credential management |
| Cloud Trace | Distributed tracing (OpenTelemetry) |
| Cloud Profiler | CPU/memory profiling |
| Cloud Monitoring | Metrics and alerting |
| GitHub Actions | CI pipeline (lint + security audit) |
| Docker Compose | Local development environment |
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
              |  Cloud Run  |            |  Cloud Run   |
              |  Frontend   +----------->+  Backend     |
              |  (Vite)     |            |  (Flask)     |
              +-------------+            +------+-------+
                                                |
                               +----------------+-----------------+
                               |                |                 |
                        +------+------+   +-----+------+  +------+------+
                        |  Firestore  |   | Cloud      |  |   Redis     |
                        |  (NoSQL DB) |   | Storage    |  |  (Queue)    |
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
|   +-- Dockerfile                  # Production image (multi-stage)
|   +-- Dockerfile.dev              # Development image
|   +-- requirements.txt            # Python dependencies
|   +-- requirements-dev.txt        # Dev/linting dependencies
|   +-- config/                     # GCP config, blacklist, lifecycle rules
|   +-- domain/
|   |   +-- entities.py             # Domain entities and business rules
|   +-- use_cases/                  # Business logic orchestrators
|   |   +-- video_processor.py
|   |   +-- security_video_processor.py
|   |   +-- complete_security_processor.py
|   |   +-- operational_analyzer.py
|   |   +-- audio_analyzer.py
|   |   +-- security_query_engine.py
|   +-- infrastructure/
|       +-- adapters/               # GCP, Gemini, OpenCV adapters
|       +-- repositories/           # Firestore repositories
|       +-- services/               # Cross-cutting services (cache, observability, logging)
|       +-- web/                    # HTTP layer (10 blueprints)
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
+-- docs/                           # Technical documentation
+-- .github/workflows/              # GitHub Actions (CI: lint + security audit)
+-- docker-compose.yml              # 4 services: backend, frontend, redis, worker
+-- .env.example                    # Environment variable reference
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- GCP Service Account with access to: Cloud Storage, Firestore, Video Intelligence API, Speech-to-Text API
- Gemini API Key

### Local Setup

```bash
# Clone the repository
git clone https://codeberg.org/mjaliaga/CU002.git
cd CU002

# Copy and configure environment variables
cp .env.example .env
# Edit .env and fill in the required values

# Place your GCP service account key
cp /path/to/service-account.json backend/gcp-credentials.json

# Start all services
docker compose up -d
```

### Development Services

| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:5173 | React application (Vite Dev Server) |
| Backend | http://localhost:5001 | Flask API |
| Redis | localhost:6379 | Job queue (internal only) |
| Workers | - | RQ worker for async processing (scalable with `--scale worker=N`) |

### Required Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | Yes | - | Flask session secret key (min. 64 chars) |
| `GCP_PROJECT_ID` | Yes | - | GCP project ID |
| `REDIS_PASSWORD` | Yes | - | Redis password |
| `GCP_BUCKET_NAME` | No | `tivit-cu002-prd-videos` | GCS bucket name |
| `GCP_REGION` | No | `us-central1` | GCP region |
| `GEMINI_API_KEY` | No | - | Gemini API key for AI analysis |
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
