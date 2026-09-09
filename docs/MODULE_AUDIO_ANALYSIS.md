# Audio Analysis Module

## Overview

The audio module extracts audio from uploaded media, transcribes it with Whisper, indexes segments in PostgreSQL with pgvector, and uses the local vLLM gateway for summaries and semantic answers. Processing runs asynchronously through Redis + RQ.

## Pipeline

```
Upload -> MinIO/filesystem -> RQ worker -> ffmpeg extraction
       -> Whisper transcription -> PostgreSQL + pgvector -> vLLM summary and Q&A
```

1. The API creates an analysis record and stores the upload as `s3://` or `file://`.
2. A worker validates duration and audio quality, then extracts mono 16 kHz audio with ffmpeg.
3. Whisper returns timestamped transcription segments.
4. Segments, metadata, and vector embeddings are stored in PostgreSQL + pgvector.
5. The local AI gateway produces summaries and answers semantic queries using relevant segments.
6. Redis caches completed work and publishes progress for polling or SSE clients.

## Storage

Temporary audio and long transcription files are stored under `audio_analysis/<analysis_id>/` in MinIO or the configured filesystem. PostgreSQL stores analysis metadata and segments; Redis holds short-lived cache and progress data.

## Configuration

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection URL |
| `S3_ENDPOINT`, `S3_BUCKET` | MinIO endpoint and bucket |
| `WHISPER_BASE_URL`, `WHISPER_MODEL` | Whisper service configuration |
| `AI_LOCAL_BASE_URL` | vLLM multimodal endpoint |
| `REDIS_URL` | RQ, cache, and progress connection |
| `AUDIO_TMP_DIR` | Optional temporary-media directory |

## API

The module is available under `/api/audio`: upload initialization, streaming upload, completion, status, analysis listing, segment retrieval, transcription retrieval, semantic query, and reprocessing. See [API.md](API.md) for request and response shapes.
