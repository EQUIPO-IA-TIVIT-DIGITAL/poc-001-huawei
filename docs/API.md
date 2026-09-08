# API Reference

All endpoints return JSON. Authentication is enforced by server-side session cookies. Include `credentials: 'include'` in all fetch calls from the frontend.

## Conventions

- **Base URL (local)**: `http://localhost:5001`
- **Content-Type**: `application/json` for request bodies unless otherwise noted
- **Success response**: `{ "success": true, "data": {...} }` or resource-specific shape
- **Error response**: `{ "success": false, "error": "message" }`
- **Authentication**: Session cookie (`SOCIO` role required for all non-auth endpoints)

---

## Authentication

### POST /api/auth/login

Authenticates a user and establishes a session.

**Request body**

```json
{
  "username": "string",
  "password": "string"
}
```

**Responses**

| Status | Description |
|--------|-------------|
| 200 | Login successful, session cookie set |
| 401 | Invalid credentials |
| 429 | Rate limit exceeded (10 per minute) |

Account lockout activates after 5 failed attempts within 5 minutes (15-minute lockout).

---

### POST /api/auth/logout

Destroys the current session.

**Responses**: 200 always.

---

### POST /api/auth/register

Registers a new user account.

**Request body**

```json
{
  "username": "string",
  "email": "string",
  "password": "string"
}
```

**Responses**

| Status | Description |
|--------|-------------|
| 201 | User created |
| 400 | Validation error |
| 409 | Username or email already taken |
| 429 | Rate limit exceeded (20 per hour) |

---

### GET /api/v1/auth/check

Returns the currently authenticated user.

**Responses**

| Status | Description |
|--------|-------------|
| 200 | `{ "authenticated": true, "username": "..." }` |
| 401 | Not authenticated |

---

## Video Moderation

### POST /api/v1/videos/upload-url

Generates a GCS signed URL for direct-to-bucket upload.

**Request body**

```json
{
  "filename": "string",
  "content_type": "video/mp4",
  "size": 104857600,
  "title": "string",
  "description": "string (optional)"
}
```

**Constraints**

- Maximum file size: 5 GB
- Allowed extensions: `.mp4`, `.webm`, `.mov`, `.avi`, `.mkv`

**Response 200**

```json
{
  "success": true,
  "data": {
    "video_id": "string",
    "upload_url": "https://storage.googleapis.com/...",
    "expires_at": "2026-01-27T15:00:00Z",
    "blob_name": "videos/.../..."
  }
}
```

---

### GET /socio/media/:video_id

Streams the video file from GCS through the backend. Supports HTTP Range requests for seek operations (RFC 7233).

**Authentication**: Session cookie required.

**Headers (optional)**

| Header | Description |
|--------|-------------|
| `Range` | Byte range to retrieve, e.g. `bytes=0-1048575` |

**Responses**

| Status | Description |
|--------|-------------|
| 200 | Full file stream (`Content-Type: video/mp4`) |
| 206 | Partial content (range request honored) |
| 403 | Video does not belong to the authenticated user |
| 404 | Video not found or GCS object missing |

**Notes**

This endpoint replaces GCS Signed URLs, which require a service account private key unavailable in Application Default Credentials (ADC) environments. The backend streams GCS blob content in 1 MB chunks. The `video_url` field returned by all other endpoints is a relative path (`/socio/media/<video_id>`) that points here.

---

### GET /video/:video_id/status

Polls the processing status of a video.

**Response 200**

```json
{
  "success": true,
  "status": "procesando | completado | error | en_revision",
  "metadatos_ia": {}
}
```

---

### POST /video/:video_id/cancel

Requests cancellation of an active processing job.

**Responses**

| Status | Description |
|--------|-------------|
| 200 | Cancellation request received |
| 400 | Missing video ID |

---

## Security Module

### POST /api/security/upload/init

Initiates a resumable upload for a surveillance video and creates the database record.

**Request body**

```json
{
  "filename": "video_12h.mp4",
  "content_type": "video/mp4",
  "nombre_camara": "ENTRADA_PRINCIPAL_CAM_01",
  "ubicacion": "Edificio Central - Piso 1",
  "fecha_grabacion": "2026-02-04T06:00:00"
}
```

**Response 200**

```json
{
  "success": true,
  "video_id": "sec_video_20260204_060000_a1b2c3d4",
  "upload_url": "https://storage.googleapis.com/...",
  "gcs_path": "gs://bucket/path",
  "expiration_hours": 24
}
```

---

### POST /api/security/upload/complete

Marks the upload as complete and enqueues processsing.

**Request body**

```json
{ "video_id": "string" }
```

---

### GET /api/security/videos

Lists all security videos belonging to the authenticated user.

---

### GET /api/security/videos/:video_id

Returns details and processing status of a security video.

---

### DELETE /api/security/videos/:video_id

Deletes a security video and its associated events and GCS objects.

---

### GET /api/security/videos/:video_id/events

Returns the indexed events extracted from the video.

**Query params**: `page`, `per_page`

---

### POST /api/security/videos/:video_id/query

Queries the indexed events using natural language.

**Request body**

```json
{ "pregunta": "When did the person in the red jacket enter?" }
```

**Response 200**

```json
{
  "pregunta": "string",
  "eventos_encontrados": 3,
  "respuesta": "string",
  "eventos_detallados": [...]
}
```

---

### POST /api/security/process (internal)

Worker callback endpoint. Requires `X-Internal-Worker-Token` header.

---

## Operational Analysis Module

### GET /api/operational/types

Returns the list of supported analysis types.

**Response 200**

```json
{
  "types": [
    { "key": "ACCESS_CONTROL", "label": "Access Control" },
    { "key": "OCCUPANCY", "label": "Occupancy" },
    { "key": "PEOPLE_FLOW", "label": "People Flow" },
    { "key": "MERCHANDISE_CONTROL", "label": "Merchandise Control" },
    { "key": "PARKING", "label": "Parking" },
    { "key": "WORK_SUPERVISION", "label": "Work Supervision" }
  ]
}
```

---

### POST /api/operational/upload/init

Initiates a resumable upload for an operational process video.

**Request body**

```json
{
  "filename": "string",
  "content_type": "video/mp4",
  "analysis_type": "ACCESS_CONTROL | OCCUPANCY | PEOPLE_FLOW | MERCHANDISE_CONTROL | PARKING | WORK_SUPERVISION",
  "custom_context": "string (optional, max 2000 chars)"
}
```

**Constraints**: max `OPERATIONAL_MAX_UPLOAD_GB` GB (default 2 GB); max 10 uploads per user per hour.

**Response 200**

```json
{
  "success": true,
  "analysis_id": "string",
  "upload_url": "https://storage.googleapis.com/...",
  "gcs_path": "gs://bucket/path"
}
```

---

### POST /api/operational/upload/stream

Proxies file content directly to GCS. Alternative to the resumable upload flow for smaller files or clients that cannot follow the GCS resumable upload protocol.

---

### POST /api/operational/upload/complete

Marks the upload as complete and enqueues analysis.

**Request body**

```json
{ "analysis_id": "string" }
```

**Response 200**

```json
{ "success": true, "analysis_id": "string", "status": "uploaded" }
```

---

### GET /api/operational/analyses

Lists operational analyses for the authenticated user.

**Query params**: `page`, `per_page`

---

### GET /api/operational/analyses/:analysis_id

Returns full analysis detail including events and report URL. Completed analyses are served from Redis cache (5-minute TTL).

---

### DELETE /api/operational/analyses/:analysis_id

Deletes analysis, associated events, and GCS objects.

---

### GET /api/operational/analyses/:analysis_id/status

Polling endpoint for real-time status updates.

**Response 200**

```json
{
  "estado": "uploading | uploaded | analyzing | generating_report | completed | error",
  "progreso": 0.75,
  "fase_actual": "string",
  "mensaje": "string"
}
```

---

### GET /api/operational/analyses/:analysis_id/events

Returns detected operational events with pagination. Supports cursor-based pagination (recommended for large event sets) or offset-based pagination.

**Query params**

| Param | Type | Description |
|-------|------|-------------|
| `page` | int | Page number (offset-based) |
| `per_page` | int | Items per page (default 50) |
| `cursor` | string | Cursor token from previous response (cursor-based) |

**Response 200**

```json
{
  "events": [...],
  "next_cursor": "string | null",
  "total": 1240
}
```

---

### GET /api/operational/analyses/:analysis_id/video-url

Returns a GCS Signed URL for direct video playback. Requires a service account with Storage Object Viewer permissions and a private key. In ADC-only environments, use the `stream-video` endpoint instead.

---

### GET /api/operational/analyses/:analysis_id/stream-video

Redirects to the GCS video stream URL (302 redirect).

---

### GET /api/operational/analyses/:analysis_id/heatmap

Returns pre-materialized activity timeline data for charting.

**Response 200**

```json
{
  "buckets": [
    { "timestamp": 0.0, "count": 3, "max_severity": "advertencia" }
  ],
  "interval_seconds": 30
}
```

---

### GET /api/operational/analyses/:analysis_id/stream

Server-Sent Events (SSE) stream for real-time progress updates. The frontend connects once and receives events until the analysis reaches a terminal state.

**Event format**

```
data: {"estado": "analyzing", "progreso": 0.45, "fase_actual": "segment_analysis", "mensaje": "Analyzing segment 18/40"}
```

The stream closes automatically when `estado` is `completed` or `error`. Maximum stream duration: 40 minutes (600 retries × 4-second poll interval).

---

### POST /api/operational/analyses/:analysis_id/cancel

Requests cancellation of an in-progress analysis. The worker checks for cancellation flags between processing phases.

---

### POST /api/operational/analyses/:analysis_id/reprocess

Re-queues a failed analysis. Only valid when `estado` is `error`.

---

### POST /api/operational/analyses/compare

Compares two analyses side-by-side. Returns aggregated statistics and a Gemini-generated comparison narrative.

**Request body**

```json
{ "analysis_id_a": "string", "analysis_id_b": "string" }
```

---

### POST /api/operational/estimate-time

Estimates processing time for a given file size and analysis type. This endpoint is unauthenticated.

**Request body**

```json
{
  "file_size_bytes": 524288000,
  "duration_seconds": 3600,
  "analysis_type": "OCCUPANCY"
}
```

**Response 200**

```json
{
  "estimated_minutes": 12,
  "phases": {
    "download": 1,
    "scan": 2,
    "segment_analysis": 7,
    "cross_analysis": 1,
    "report": 1
  }
}
```

## Audio Analysis Module

### POST /api/audio/upload/init

Initiates upload and creates the audio analysis record.

**Request body**

```json
{
  "filename": "string",
  "content_type": "audio/mp3"
}
```

**Supported formats**: `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`, `.mp3`, `.wav`, `.aac`, `.m4a`, `.flac`, `.ogg`, `.opus`, `.wma`, and others.

**Constraints**: max `AUDIO_MAX_PROXY_UPLOAD_BYTES` (default 10 GB); max 10 uploads per user per hour.

---

### POST /api/audio/upload/stream

Proxies the file upload to GCS (for CORS-restricted clients).

---

### POST /api/audio/upload/complete

Completes upload and enqueues transcription processing.

---

### GET /api/audio/analyses

Lists audio analyses for the authenticated user.

---

### GET /api/audio/analyses/:analysis_id

Returns full analysis detail.

`analysis_id` format: `aud_YYYYMMDD_HHMMSS_<8hex>`

---

### DELETE /api/audio/analyses/:analysis_id

Deletes analysis and associated GCS objects.

---

### GET /api/audio/analyses/:analysis_id/status

Polling endpoint for processing status.

---

### GET /api/audio/analyses/:analysis_id/segments

Returns transcription segments with timestamps, paginated.

**Query params**: `page`, `per_page`

---

### GET /api/audio/analyses/:analysis_id/transcription

Returns the full transcription as plain text or structured JSON.

---

### POST /api/audio/analyses/:analysis_id/query

Queries the transcription content using natural language.

**Request body**

```json
{ "query": "What was discussed about the Q3 budget?" }
```

**Response 200**

```json
{
  "query": "string",
  "answer": "string",
  "relevant_segments": [
    { "start": 120.5, "end": 145.0, "text": "string" }
  ]
}
```

---

### POST /api/audio/analyses/:analysis_id/reprocess

Re-queues a failed transcription.

---

## Workspaces Module

### POST /workspaces

Creates a new workspace.

**Request body**

```json
{
  "nombre": "string (3-50 chars)",
  "descripcion": "string (optional)",
  "categoria": "string (optional)",
  "nivel_tolerancia": "bajo | medio | alto",
  "tipo_contenido": "string (optional)"
}
```

**Constraints**: max 20 workspaces per user; max 100 videos per workspace.

---

### GET /workspaces

Lists all workspaces belonging to the authenticated user.

---

### GET /workspaces/:workspace_id

Returns workspace details including video counts and stats.

---

### PUT /workspaces/:workspace_id

Updates workspace metadata.

---

### DELETE /workspaces/:workspace_id

Deletes workspace. Videos inside are not deleted but become unassigned.

---

### POST /workspaces/:workspace_id/chat/validate

Initiates AI-driven validation of workspace context configuration. Gemini analyzes the workspace settings and returns clarifying questions or a validation summary.

**Request body**: none (uses current workspace configuration)

**Response 200**

```json
{
  "success": true,
  "validation": {
    "is_sufficient": true,
    "questions": [],
    "summary": "string"
  }
}
```

---

## Rate Limits

| Endpoint category | Default limit |
|-------------------|--------------|
| Login | 10 per minute |
| Registration | 20 per hour |
| File uploads | 20 per hour |
| General API | 60 per minute |
| AI chat (Gemini) | 15 per minute |
| Status polling | 3000 per minute |
| Video details | 120 per minute |
| Global (per-user) | 100 per minute / 1000 per hour / 10000 per day |

All limits are enforced by Flask-Limiter backed by Redis. Exceeding a limit returns HTTP `429`.
