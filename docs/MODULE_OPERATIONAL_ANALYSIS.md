# Operational Analysis Module

## Overview

The Operational Analysis module enables contextual video intelligence on surveillance recordings. A user selects an analysis type (e.g., access control, occupancy), optionally provides a plain-text context describing the camera location and scenario, and uploads the video. The backend runs a five-phase pipeline — dense motion scan, parallel Gemini segment analysis, cross-analysis consolidation, report generation — and stores all events and a structured summary in Firestore.

The module is exposed under `/api/operational` and implemented as a Flask blueprint (`app_operational.py`). Heavy processing runs asynchronously via RQ workers.

---

## Analysis Types

| Key | Name | Description |
|-----|------|-------------|
| `ACCESS_CONTROL` | Control de Acceso | Entries, exits, fotcheck usage, unauthorized access |
| `OCCUPANCY` | Aforo | Simultaneous occupancy, capacity alerts, peak hours |
| `PEOPLE_FLOW` | Flujo de Personas | Traffic by hour, peak periods, bottlenecks |
| `MERCHANDISE_CONTROL` | Control de Mercancía | Objects entering/leaving, loading events |
| `PARKING` | Estacionamiento | Vehicle counts, occupancy, dwell time |
| `WORK_SUPERVISION` | Supervisión de Obra/Trabajo | Workers present, PPE compliance, safety violations |

---

## Pipeline

```
Video upload (GCS)
        │
        ▼
 Fase 0 — Download & Metadata
        │  ffprobe → duration, fps, resolution
        │  fallback: OpenCV
        ▼
 Fase 1 — Dense Scan (OperationalScanner)
        │  Sample every 0.5 s
        │  5 layers: frame diff, MOG2, contours, zones, temporal
        │  → motion_segments, detected_events_map
        ▼
 Fase 2 — Gemini Segment Analysis (OperationalSegmentAnalyzer)
        │  3 parallel workers, up to 3 retries with exponential backoff
        │  Each segment: extract clip (FFmpeg) → upload clip to GCS →
        │  pass gs:// URI to Gemini (base64 frames as fallback)
        │  → List[OperationalEvent] with frame_urls
        ▼
 Fase 3 — Cross-Analysis (OperationalCrossAnalyzer)
        │  All segment results → single consolidated JSON
        │  Uses ThinkingConfig (MEDIUM) — dedicated method
        │  Chunked (30 segs/chunk) if > 40 segments
        ▼
 Fase 4 — Report + Persist (OperationalReporter)
        │  PDF report → GCS (operational/{analysis_id}/report.pdf)
        │  Firestore: operational_analyses + operational_events
        └──▶ COMPLETED
```

### Phase Details

| Phase | Class | State | Progress |
|-------|-------|-------|----------|
| 0 — Download | `OperationalDownloader` | `downloading` | 2% |
| 1 — Dense Scan | `OperationalScanner` | `scanning` | 10–20% |
| 2 — Gemini Analysis | `OperationalSegmentAnalyzer` | `analyzing` | 25–80% |
| 3 — Cross-Analysis | `OperationalCrossAnalyzer` | `cross_analyzing` | 80% |
| 4 — Report | `OperationalReporter` | `generating_report` | 95–100% |

### Segment Limits

The Dense Scanner caps the number of Gemini segments based on video duration to control cost and latency.

| Video duration | Max segments |
|---------------|-------------|
| ≤ 10 min | 30 |
| ≤ 30 min | 60 |
| ≤ 1 h | 100 |
| ≤ 2 h | 150 |
| ≤ 4 h | 220 |
| ≤ 8 h | 300 |
| > 8 h | 400 |

---

## Deduplication and Concurrency

### Content-Based Cache (Redis)

Before entering Fase 1, the pipeline computes a SHA-256 hash of the downloaded video file. The key `op:{hash}:{analysis_type}` is looked up in Redis.

- **Cache hit**: the previous `summary`, `scan_stats`, and `report_pdf_url` are copied directly to the new `OperationalAnalysis` document. All events from the original analysis are **cloned** (new `id` + new `analysis_id`) and written to Firestore under the new analysis ID. The pipeline completes in seconds without re-running Gemini.
- **Cache miss**: the pipeline runs in full. On successful completion, the result is stored in Redis (TTL: 7 days by default).

### Distributed Lock

After a cache miss, the pipeline acquires a Redis `SET NX` lock on `op_lock:{cache_key}` with a 2-hour TTL. This prevents two workers from running identical pipelines concurrently if the same video is uploaded twice in quick succession before the first run completes.

---

## GCS Storage Layout

```
{bucket}/
  operational/
    {analysis_id}/
      report.pdf                        # Generated report
      seg_{NNN}/
        frame_{NN}.jpg                  # Key frames extracted during Fase 2
    tmp_clips/
      {analysis_id}/
        clip_{NNNN}.mp4                 # Temporary per-segment clips (cleaned up after Gemini call)
```

Frame objects are stored with `gs://` URIs in `OperationalEvent.frame_urls`. The `/frames/` proxy endpoint converts them to authenticated HTTP URLs at query time (see [Frame Proxy](#frame-proxy) below).

---

## Code Structure

```
use_cases/
  operational_analyzer.py       # Main orchestrator — OperationalAnalyzer.process()
  operational/
    downloader.py               # Fase 0: GCS download, ffprobe metadata
    scanner.py                  # Fase 1: DenseVideoScanner wrapper
    segment_analyzer.py         # Fase 2: parallel Gemini calls, frame extraction
    cross_analyzer.py           # Fase 3: consolidation LLM call
    reporter.py                 # Fase 4: PDF generation, GCS upload

infrastructure/
  adapters/
    gemini_adapter.py           # analyze_video_clip() + analyze_text_with_thinking()
    gemini_operational_prompts.py  # build_segment_prompt(), build_cross_analysis_prompt()
  repositories/
    operational_analysis_repository.py  # Firestore CRUD for analyses and events
  services/
    dense_scanner.py            # 5-layer frame-level motion detector
    log_utils.py                # sanitize_context_for_log()
  web/blueprints/
    app_operational.py          # Flask blueprint — all REST endpoints
```

---

## Domain Entities

### `OperationalAnalysis`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Format: `op_{YYYYMMDD}_{HHMMSS}_{uuid8}` |
| `usuario` | `str` | Owner username |
| `analysis_type` | `str` | One of the six analysis type keys |
| `custom_context` | `str` | User-supplied context (max 2,000 chars) |
| `custom_questions` | `List[str]` | Optional extra questions (max 5 × 200 chars each) |
| `nombre_camara` | `str` | Camera identifier |
| `ubicacion` | `str` | Physical location description |
| `video_filename` | `str` | Original uploaded filename |
| `video_gcs_url` | `str` | GCS path (`gs://bucket/...`) |
| `video_duration` | `float` | Duration in seconds |
| `video_size_mb` | `float` | File size in MB |
| `estado` | `EstadoOperationalAnalysis` | Current pipeline state |
| `progress` | `float` | 0–100 completion percentage |
| `current_phase` | `str` | Human-readable phase description |
| `eventos` | `List[str]` | IDs of `OperationalEvent` documents (max 300 inline) |
| `summary` | `dict` | Structured output from Fase 3 cross-analysis |
| `scan_stats` | `dict` | Dense scan statistics + materialized heatmap |
| `report_pdf_url` | `str` | GCS URI of the generated PDF |
| `tiempo_procesamiento_segundos` | `float` | Wall-clock pipeline duration |
| `started_at` / `completed_at` | `str` | ISO-8601 timestamps |

### `OperationalEvent`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Format: `op_ev_{uuid12}` |
| `analysis_id` | `str` | Parent analysis ID |
| `timestamp_start` / `timestamp_end` | `float` | Seconds into the video |
| `event_type` | `str` | `ENTRY`, `EXIT`, `FOTCHECK_USED`, `FOTCHECK_SKIPPED`, `MOVEMENT`, etc. |
| `scanner_event_type` | `str` | Raw dense-scanner classification |
| `person_description` | `str` | Gemini-generated description |
| `carried_objects` | `str` | Objects being carried |
| `direction` | `str` | `IN`, `OUT`, `THROUGH`, `STATIONARY` |
| `zone` | `str` | Area within the frame |
| `confidence` | `str` | `HIGH`, `MEDIUM`, or `LOW` |
| `details` | `dict` | Additional structured metadata from Gemini |
| `frame_urls` | `List[str]` | GCS URIs of key frames (served via proxy) |

### `EstadoOperationalAnalysis`

| Value | Meaning |
|-------|---------|
| `pending` | Queued, not yet started |
| `downloading` | Fase 0 — downloading from GCS |
| `scanning` | Fase 1 — dense motion scan |
| `analyzing` | Fase 2 — Gemini segment calls |
| `cross_analyzing` | Fase 3 — cross-analysis consolidation |
| `generating_report` | Fase 4 — PDF creation and upload |
| `completed` | Pipeline finished successfully |
| `cancelled` | Cancelled by the user |
| `error` | Pipeline failed |

---

## API Reference

All endpoints require a valid session cookie (`SOCIO` role). All responses are JSON.

Base path: `/api/operational`

---

### GET /types

Returns the list of available analysis types.

**Response 200**

```json
{
  "success": true,
  "types": {
    "ACCESS_CONTROL": {
      "name": "Control de Acceso",
      "description": "...",
      "icon": "🚪",
      "key_metrics": ["Entradas únicas", "..."],
      "estimated_minutes_per_hour": 8
    }
  },
  "max_context_length": 2000
}
```

---

### POST /upload/init

Creates the analysis record and generates a GCS resumable upload URL.

**Rate limit**: 10 analyses per user per hour.

**Request body**

```json
{
  "filename": "camara_entrada_20260511.mp4",
  "analysis_type": "ACCESS_CONTROL",
  "content_type": "video/mp4",
  "custom_context": "Puerta principal, Piso 18, lunes a viernes 07:00–20:00",
  "custom_questions": ["¿Hubo tailgating?"],
  "nombre_camara": "ENTRADA_P18_CAM_01",
  "ubicacion": "Edificio Central — Piso 18"
}
```

| Field | Required | Constraints |
|-------|----------|-------------|
| `filename` | Yes | — |
| `analysis_type` | Yes | Must be a valid type key |
| `content_type` | No | Defaults to `video/mp4`; must start with `video/` |
| `custom_context` | No | Max 2,000 characters |
| `custom_questions` | No | Max 5 questions, 200 chars each |

**Response 200**

```json
{
  "success": true,
  "analysis_id": "op_20260511_155400_2df30261",
  "upload_url": "https://storage.googleapis.com/...",
  "gcs_path": "gs://bucket/operational/...",
  "bucket": "tivit-mira-prd-videos",
  "blob_name": "operational/...",
  "expiration_hours": 12
}
```

**Error responses**

| Status | Cause |
|--------|-------|
| 400 | Missing required field, invalid `analysis_type`, or `custom_context` too long |
| 400 | `content_type` does not start with `video/` |
| 429 | Rate limit exceeded (10 per hour) |
| 500 | GCS or Firestore unavailable |

---

### POST /upload/stream

Uploads a video file directly through the backend (used when GCS resumable upload is unavailable or for smaller files).

Files ≤ 100 MB use a simple upload. Files > 100 MB use parallel 50 MB chunks via multipart upload.

**Request**: `multipart/form-data`

| Field | Description |
|-------|-------------|
| `analysis_id` | ID returned by `/upload/init` |
| `file` | Video binary |

**Response 200**

```json
{
  "success": true,
  "analysis_id": "op_...",
  "bytes_uploaded": 52428800,
  "status": "pending"
}
```

**Error responses**

| Status | Cause |
|--------|-------|
| 400 | Missing `analysis_id`, empty file, invalid MIME type, or invalid file signature |
| 403 | Analysis belongs to a different user |
| 404 | Analysis not found |
| 413 | File exceeds `OPERATIONAL_MAX_UPLOAD_GB` (default: 100 GB) |

---

### POST /upload/complete

Verifies the GCS upload and enqueues the analysis pipeline in the RQ job queue.

**Request body**

```json
{
  "analysis_id": "op_20260511_155400_2df30261",
  "auto_process": true
}
```

**Response 200**

```json
{
  "success": true,
  "analysis_id": "op_...",
  "status": "processing",
  "job_id": "rq:job:...",
  "message": "Análisis operativo iniciado"
}
```

**Error responses**

| Status | Cause |
|--------|-------|
| 400 | File not fully present in GCS |
| 403 | Ownership mismatch |
| 503 | Redis unavailable or queue at capacity |

---

### GET /analyses

Lists all analyses for the authenticated user.

**Query parameters**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `analysis_type` | — | Filter by type key |
| `limit` | 50 | Maximum results to return |

**Response 200**

```json
{
  "success": true,
  "analyses": [
    {
      "id": "op_...",
      "analysis_type": "ACCESS_CONTROL",
      "estado": "completed",
      "progress": 100,
      "video_filename": "camara.mp4",
      "created_at": "2026-05-11T15:54:00Z"
    }
  ],
  "count": 1
}
```

---

### GET /analyses/:analysis_id

Returns full detail of a single analysis including the `summary` block produced by Fase 3.

**Response 200**: Full `OperationalAnalysis` serialized as JSON.

**Error responses**: 403 (ownership), 404 (not found).

---

### GET /analyses/:analysis_id/status

Lightweight polling endpoint. Returns only `estado`, `progress`, `current_phase`, and `error_message`.

**Response 200**

```json
{
  "success": true,
  "estado": "analyzing",
  "progress": 54.3,
  "current_phase": "Segmento 12/22",
  "error_message": ""
}
```

---

### GET /analyses/:analysis_id/progress/stream

Server-Sent Events (SSE) endpoint for real-time progress updates. The client receives events until the analysis reaches `completed`, `cancelled`, or `error`.

**Event shape**

```
data: {"estado": "analyzing", "progress": 67.5, "current_phase": "Segmento 15/22"}
```

The stream closes automatically when a terminal state is reached.

---

### GET /analyses/:analysis_id/events

Returns the detected events for an analysis, with paginated or cursor-based navigation. Frame `gs://` URIs are converted to authenticated proxy URLs before returning.

**Query parameters**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `page` | 1 | Page number (1-based) |
| `per_page` | 20 | Results per page (max 100) |
| `cursor` | — | Firestore document cursor for keyset pagination |
| `event_type` | — | Filter by event type string |

**Response 200**

```json
{
  "success": true,
  "events": [
    {
      "id": "op_ev_abc123",
      "analysis_id": "op_...",
      "timestamp_start": 6.0,
      "timestamp_end": 34.0,
      "event_type": "FOTCHECK_USED",
      "direction": "IN",
      "person_description": "Hombre joven, camiseta gris",
      "carried_objects": "Mochila negra a la espalda",
      "confidence": "HIGH",
      "frame_urls": [
        "http://localhost:5001/api/operational/analyses/op_.../frames/operational/op_.../seg_001/frame_01.jpg"
      ]
    }
  ],
  "total": 11,
  "page": 1,
  "per_page": 20,
  "next_cursor": "..."
}
```

---

### GET /analyses/:analysis_id/frames/:blob_path

Authenticated frame image proxy. Fetches the JPEG from GCS using ADC credentials and serves it directly to the browser. Required because ADC OAuth user tokens cannot sign GCS URLs.

**Security**:
- Session cookie required.
- Ownership validated against the analysis record.
- `blob_path` must start with `operational/{analysis_id}/` (path traversal prevention).
- Response includes `Cache-Control: private, max-age=3600`.

**Frontend usage**: `<img src="..." crossOrigin="use-credentials">` is required because Cross-Origin Isolation headers (`COEP: credentialless`) suppress automatic cookie forwarding for cross-origin image requests.

---

### GET /analyses/:analysis_id/heatmap

Returns a temporal activity heatmap over the video timeline, computed from all events.

**Response 200**

```json
{
  "success": true,
  "heatmap": {
    "buckets": [0, 2, 5, 3, 1],
    "bucket_size": 120,
    "max_count": 5,
    "total_events": 11,
    "video_duration": 684.0
  }
}
```

`bucket_size` is in seconds; it is chosen so there are approximately 20 buckets across the video duration, with a minimum of 30 seconds per bucket. Results are cached in Redis for 5 minutes.

---

### DELETE /analyses/:analysis_id

Soft-deletes the analysis and its events from Firestore. The GCS video and report objects are **not** deleted.

**Response 200**: `{ "success": true }`.

---

### POST /analyses/:analysis_id/cancel

Requests cancellation of an in-progress analysis. The running worker checks the Firestore state at checkpoints and stops gracefully.

**Response 200**: `{ "success": true, "message": "Cancelación solicitada" }`.

---

### POST /analyses/:analysis_id/reprocess

Re-enqueues a failed analysis for reprocessing.

**Constraints**: Only analyses in `error` or `cancelled` state can be reprocessed.

**Response 200**: `{ "success": true, "job_id": "rq:job:..." }`.

---

## Firestore Data Model

### Collection: `operational_analyses`

Document ID: `{analysis_id}` (e.g., `op_20260511_155400_2df30261`).

All fields of `OperationalAnalysis` serialized as a flat Firestore document. `eventos` stores up to 300 event IDs inline; beyond that, events are queried from the `operational_events` collection directly.

### Collection: `operational_events`

Document ID: `{event_id}` (e.g., `op_ev_abc123def456`).

Indexed field: `analysis_id` (equality filter used by all event queries). Events are ordered by `timestamp_start` client-side after retrieval.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPERATIONAL_TMP_DIR` | system temp | Base directory for temporary video and clip files. In Cloud Run, where `/tmp` is limited to 512 MB, mount a volume and point this variable to it. |
| `OPERATIONAL_MAX_UPLOAD_GB` | `100` | Maximum video upload size in GB enforced by `/upload/stream`. |

---

## Infrastructure Notes

### Gemini Usage per Phase

| Phase | Method | ThinkingConfig |
|-------|--------|---------------|
| Fase 2 (segment) | `analyze_video_clip()` | None — disabled for throughput |
| Fase 3 (cross-analysis) | `analyze_text_with_thinking()` | MEDIUM, max 32,768 output tokens |

Fase 2 passes video to Gemini preferentially as a `gs://` URI (Vertex AI reads directly from GCS). If GCS upload fails, it falls back to base64-encoded JPEG frames (up to 5 per segment).

### GCS Frame Proxy

GCS Signed URLs require a service account private key. In environments using Application Default Credentials (OAuth user token), no private key is available. The module addresses this by:

1. Storing `gs://bucket/blob` URIs in `OperationalEvent.frame_urls` at write time.
2. Converting URIs to `/api/operational/analyses/{id}/frames/{blob_path}` proxy URLs at read time (`_resolve_frame_urls()`).
3. Serving images via `blob.download_as_bytes()` inside the authenticated proxy endpoint.

This pattern requires `crossOrigin="use-credentials"` on frontend `<img>` elements due to `Cross-Origin-Embedder-Policy: credentialless` required for FFmpeg.wasm.

### Cross-Origin Isolation (FFmpeg.wasm)

The frontend uses `@ffmpeg/ffmpeg` (WASM) for client-side video pre-processing, which requires `SharedArrayBuffer`. The following headers are set on both the Vite dev server and the production nginx image:

```
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: credentialless
```

`credentialless` (rather than `require-corp`) allows CDN resources to load without `Cross-Origin-Resource-Policy` headers, while still enabling `SharedArrayBuffer`.

---

**Last Updated**: May 15, 2026  
**Version**: 2.0.0
