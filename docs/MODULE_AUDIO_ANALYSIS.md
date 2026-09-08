# Audio Analysis Module

## Overview

The Audio Analysis module extracts, transcribes and indexes the audio content of any video uploaded by the user. It produces a verbatim, speaker-diarized transcription with per-second timestamps, an AI-generated summary, and a semantic search interface that lets users ask natural-language questions and receive timestamped answers.

The module is exposed under `/api/audio` and implemented as a Flask blueprint (`app_audio.py`). All heavy processing runs asynchronously via RQ workers on the `cu002-worker-1` service.

---

## What it offers

| Capability | Detail |
|-----------|--------|
| **Verbatim transcription** | Every spoken word including fillers, repetitions and hesitations |
| **Speaker diarization** | Who said what — real names when identifiable, `SPEAKER_N` otherwise |
| **Per-segment timestamps** | Precision to the second for each speaker turn |
| **Language detection** | Automatic before transcribing (30 s sample via STT V1) |
| **Semantic Q&A** | Ask a question → get a timestamped answer from the transcript |
| **AI summary** | Topics, key points, sentiment, action items |
| **Live progress (SSE)** | Frontend receives progress events in real-time |
| **Checkpoint recovery** | Resumes from `AUDIO_READY` or `TRANSCRIBED` if the worker crashes |
| **Content deduplication** | Same video → instant result from Redis + Firestore cache |
| **Maximum duration** | 2 hours (`MAX_AUDIO_VIDEO_DURATION_SECONDS = 7200`) |

---

## Pipeline

```
Video upload (GCS)
        │
        ▼
 Fase 0 — Checkpoint recovery
        │  If estado ∈ {AUDIO_READY, TRANSCRIBING, TRANSCRIBED, INDEXING}
        │  → skip download/extraction and resume from that point
        ▼
 Fase 1 — Download & duration validation
        │  Download video from GCS to /tmp (or AUDIO_TMP_DIR)
        │  ffprobe → video_duration
        │  Validate ≤ 2 h
        ▼
 Fase 1.5 — Content deduplication
        │  SHA-256 hash of downloaded video → key "audio:{hash}" in Redis
        │  Cache hit → clone segments (new id + analysis_id), copy metadata, COMPLETED
        ▼
 Fase 2 — Audio quality pre-check
        │  ffmpeg volumedetect + silence detection + SNR estimate + voice detection
        │  Reject if no human voice detected
        ▼
 Fase 3 — Audio extraction
        │  ffmpeg: strip video, mono, 16 kHz, FLAC → /tmp (or AUDIO_TMP_DIR)
        │  Upload FLAC to GCS: audio_analysis/{id}/audio.flac
        │  Checkpoint: AUDIO_READY (Firestore write)
        ▼
 Fase 4 — Language detection + Transcription
        │  Detect language: 30 s sample → STT V1 → 2-letter code (es/en/pt/...)
        │
        │  Transcription (3-tier fallback):
        │   1. Gemini Vision — video/audio → Files API → verbatim + diarization
        │   2. STT V2 chirp_2 + Gemini speaker enrichment
        │   3. STT V1 parallel chunks (> 15 min) or single long_running_recognize
        │
        │  Build AudioSegment entities (id, analysis_id, text, timestamps, speaker, language)
        │  Persist: guardar_segmentos_batch()
        │  If full_text > 100 KB → upload to GCS: audio_analysis/{id}/transcription.txt
        │  Checkpoint: TRANSCRIBED (Firestore write)
        ▼
 Fase 5 — Embeddings (non-critical)
        │  Generate text-embedding-004 vectors for each segment
        │  Store in Firestore (audio_segments). Degrades gracefully on failure.
        ▼
 Fase 6 — AI Summary
        │  Gemini → {topics, key_points, sentiment, duration_summary, action_items}
        │  analysis.summary = {...}
        ▼
 Fase 7 — COMPLETED
        │  Store in Redis cache (audio:{hash})
        └──▶ COMPLETED
```

### Transcription tier details

| Tier | Method | Confidence (est.) | Notes |
|------|--------|-------------------|-------|
| 1 (primary) | Gemini Vision (video or FLAC) | 0.90 (video) / 0.85 (audio) | Full verbatim + diarization in one API call. Falls back to FLAC if video codec rejected. |
| 2 (fallback 1) | STT V2 chirp_2 + Gemini speaker enrichment | Real STT confidence | `batch_recognize`. If chirp_2 rejects diarization, retries without it, then uses Gemini to assign speaker names. |
| 3 (fallback 2) | STT V1 `long_running_recognize` | Real STT confidence | Parallel chunking (5-min chunks, thread pool) for audio > 15 min. Diarization via `SpeakerDiarizationConfig`. |

### Checkpoint states

| State | Meaning | Resume point |
|-------|---------|-------------|
| `AUDIO_READY` | FLAC extracted and in GCS | Skip download + extraction |
| `TRANSCRIBED` | Segments saved to Firestore | Skip transcription, re-run embeddings + summary |
| `INDEXING` | Embeddings done | Re-run summary only |

---

## Domain Entities

### `AudioAnalysis`

Main Firestore document in `audio_analyses`.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Format: `aud_YYYYMMDD_HHMMSS_{8hex}` |
| `video_filename` | `str` | Original uploaded filename |
| `video_duration` | `float` | Seconds |
| `video_gcs_url` | `str` | `gs://bucket/...` |
| `video_size_mb` | `float` | File size in MB |
| `audio_gcs_url` | `str` | `gs://bucket/audio_analysis/{id}/audio.flac` |
| `estado` | `EstadoAudioAnalysis` | Pipeline state enum |
| `progress` | `float` | 0–100 |
| `current_phase` | `str` | Human-readable phase label |
| `error_message` | `str` | Set on `ERROR` state |
| `full_transcription` | `str` | Full text (or 600-char preview if > 100 KB) |
| `full_transcription_gcs_url` | `str` | GCS URL when transcription > 100 KB |
| `total_segments` | `int` | Number of `AudioSegment` documents |
| `detected_language` | `str` | Primary language (`"es"`, `"en"`, ...) |
| `detected_languages` | `List[str]` | All languages by frequency (descending) |
| `average_confidence` | `float` | Mean confidence across segments |
| `embeddings_generated` | `bool` | Whether vector embeddings were created |
| `summary` | `Dict` | AI-generated summary object |
| `titulo` | `str` | User-supplied or generated title |
| `descripcion` | `str` | Optional description |
| `created_at` / `started_at` / `completed_at` | `str` | ISO 8601 UTC |
| `tiempo_procesamiento_segundos` | `float` | Wall-clock processing time |
| `usuario` | `str` | Owning user |

### `AudioSegment`

One document per speaker turn in `audio_segments`.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | `{analysis_id}_seg_{NNNN}` |
| `analysis_id` | `str` | Parent analysis ID |
| `text` | `str` | Verbatim transcribed text |
| `start_time` | `float` | Seconds from video start |
| `end_time` | `float` | Seconds from video start |
| `confidence` | `float` | 0–1 |
| `speaker` | `str` | Real name or `SPEAKER_N` |
| `language` | `str` | BCP-47 language of this segment |
| `words` | `List[Dict]` | Word-level timestamps (`{word, start_time, end_time, confidence}`) |
| `search_terms` | `List[str]` | Normalized lowercase tokens for text search |

### `EstadoAudioAnalysis` (enum)

```
PENDING → UPLOADING → EXTRACTING_AUDIO → AUDIO_READY
       → TRANSCRIBING → TRANSCRIBED → INDEXING → COMPLETED
                                               ↘ ERROR / CANCELLED
```

---

## API Endpoints

All endpoints under `/api/audio`. Authentication: session cookie (`api_socio_requerido`).

### Upload flow (3 steps)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/upload/init` | Creates `AudioAnalysis` (PENDING). Returns `{analysis_id, upload_url}` |
| `POST` | `/upload/stream` | Proxy stream upload to GCS (CORS workaround) |
| `POST` | `/upload/complete` | Finalizes upload, enqueues RQ job, returns `{analysis_id}` |

### Analysis management

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/analyses` | List analyses for current user (paginated) |
| `GET` | `/analyses/<id>` | Full detail of one analysis |
| `DELETE` | `/analyses/<id>` | Delete analysis + segments + GCS files |
| `GET` | `/analyses/<id>/status` | Lightweight status poll (estado, progress, phase) |
| `POST` | `/analyses/<id>/reprocess` | Re-enqueue a failed analysis |

### Content endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/analyses/<id>/segments` | Paginated `AudioSegment` list. Query params: `page`, `per_page`, `speaker`, `search` |
| `GET` | `/analyses/<id>/transcription` | Full transcription text (downloads from GCS if needed) |
| `POST` | `/analyses/<id>/query` | Semantic Q&A. Body: `{question}`. Returns `{answer, segments, confidence}` |

### Real-time progress

The `GET /analyses/<id>/status` endpoint also supports **SSE** when the `Accept: text/event-stream` header is present. Events are published via Redis pub/sub on channel `audio_progress:{id}`. The frontend (`AudioAnalysisDetail.tsx`) connects to SSE and falls back to polling every 3 s if the connection drops.

---

## GCS Storage Layout

```
{bucket}/
└── audio_analysis/
    └── {analysis_id}/
        ├── audio.flac                # Extracted mono 16 kHz audio
        └── transcription.txt         # Full transcription text (only if > 100 KB)
```

> The original video is **not** stored here — it lives under the bucket path provided at upload time.

---

## Firestore Collections

### `audio_analyses`

- **Document ID**: `analysis_id` (`aud_YYYYMMDD_HHMMSS_{8hex}`)
- **Queries used**: `usuario == ?` + `created_at DESC`, single doc by ID

### `audio_segments`

- **Document ID**: `{analysis_id}_seg_{NNNN}`
- **Queries used**:
  - `analysis_id == ?` (list segments for an analysis)
  - `analysis_id == ? AND speaker == ?` (filter by speaker)
  - `analysis_id == ? AND search_terms ARRAY_CONTAINS ?` (text search)
- **Pagination**: `start_after` cursor pattern, `per_page` default 50

---

## Deduplication and Concurrency

### Content-Based Cache (Redis)

Before transcribing, the pipeline computes a SHA-256 hash of the downloaded video and looks up key `audio:{hash}` in Redis.

- **Cache hit**: metadata is copied to the new `AudioAnalysis`. Each `AudioSegment` is **deep-cloned** (`copy.copy()`) with a new `id` (`{new_analysis_id}_seg_{NNNN}`) and `analysis_id` assigned before calling `guardar_segmentos_batch()`. This prevents the original cached segments from being mutated and ensures queries by the new `analysis_id` return the correct results. Completes in seconds.
- **Cache miss**: full pipeline runs. On `COMPLETED`, result is stored in Redis (TTL: configurable).

### Redis Query Cache (`_redis`)

`AudioAnalyzer` maintains a Redis client (`self._redis`) to cache Gemini query results within `query()`. Cache keys are derived from `{analysis_id}:{question_hash}`. Disabled gracefully if Redis is unavailable.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Google AI Studio API key (required for transcription) |
| `GEMINI_TRANSCRIBE_MODEL` | `gemini-2.5-pro` | Primary transcription model |
| `GEMINI_TRANSCRIBE_MODELS` | — | Comma-separated fallback model list (overrides single model) |
| `GCP_BUCKET_NAME` | — | GCS bucket for audio and transcription files |
| `GCP_PROJECT_ID` | — | GCP project for STT V2 and Firestore |
| `GCP_REGION` | `us-central1` | Region for STT V2 batch_recognize endpoint |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection for cache, pub/sub, queue |
| `AUDIO_TMP_DIR` | `tempfile.gettempdir()` | Override directory for temporary audio/video files |
| `AUDIO_MAX_PROXY_UPLOAD_BYTES` | `10 GB` | Max size for stream-upload proxy |
| `AUDIO_MAX_ANALYSES_PER_HOUR` | `10` | Per-user rate limit on new analysis requests |

---

## Infrastructure Notes

### Credential model

The Audio Analysis module uses **two distinct Gemini credential paths**:

| Credential | Used for |
|------------|----------|
| `GEMINI_API_KEY` (Google AI Studio) | Transcription — `GeminiTranscribeAdapter` calls the Gemini Files API with the API key. Falls back to STT if the key is absent. |
| Vertex AI ADC (service account / user OAuth) | AI summary, speaker enrichment, and semantic Q&A — these go through `GeminiAdapter` with `GOOGLE_GENAI_USE_VERTEXAI=True`. |

STT V2 and STT V1 calls also use **Application Default Credentials** via the standard GCP Speech client libraries.

### Gemini Files API

Transcription uploads the full video (or FLAC fallback) to the Gemini Files API (`client.files.upload()`). The pipeline polls until the file state is `ACTIVE` (exponential backoff, max 600 s / 10 min). The file is deleted immediately after content generation to avoid accumulation.

### Segment merging

After Gemini transcription, consecutive segments from the same speaker with a gap ≤ 0.35 s are merged into a single segment to reduce artificial fragmentation.

### Large transcriptions

If the full transcription text exceeds 100 KB, it is uploaded to GCS (`audio_analysis/{id}/transcription.txt`) and only a 600-character preview is stored in the Firestore document (to stay well under the 1 MB document limit). `GET /analyses/<id>/transcription` transparently downloads from GCS when `full_transcription_gcs_url` is set.

### Worker concurrency

The `cu002-worker-1` service runs 2 replicas. Each replica processes one job at a time. Long-running analyses (60–120 min videos) can occupy a worker for 5–15 minutes depending on Gemini response time.
