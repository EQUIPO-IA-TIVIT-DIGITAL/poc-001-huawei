# Security and Compliance

## Authentication

### Session-based Authentication

The system uses server-side sessions via Flask's signed cookie mechanism (`SECRET_KEY`). There are no JWT tokens. The session stores the authenticated username and role.

- Sessions expire on browser close unless explicitly extended.
- `SECRET_KEY` must be at least 64 characters and generated with a CSPRNG (e.g., `secrets.token_hex(32)`).

### Password Storage

Passwords are hashed with **bcrypt** at a configurable cost factor (`BCRYPT_ROUNDS`, default 12). Plain-text passwords are never stored or logged.

### Account Lockout

Failed login attempts are tracked in a Redis sorted set using a sliding window:

- **Threshold**: 5 failed attempts within 5 minutes (`AUTH_MAX_FAILED_ATTEMPTS`, `AUTH_LOCKOUT_WINDOW_SECONDS`).
- **Lockout duration**: 15 minutes (`AUTH_LOCKOUT_DURATION_SECONDS`).
- Redis TTL-based auto-eviction prevents unbounded memory growth (`TTLCache` fallback for single-process dev).
- Lockout keys use normalized usernames to prevent case-variation bypass.

### Authorization

A single `SOCIO` role is the only user role. All moderation and analysis endpoints require `@api_socio_requerido` or `@socio_requerido` decorators. Users can only access their own resources — ownership is validated at the repository/entity level on every read and write.

---

## Transport Security

- All inter-service communication in production occurs over HTTPS (Cloud Run enforces TLS).
- CORS is configured via `CORS_ORIGIN`, which restricts `Access-Control-Allow-Origin` to the declared frontend origin. Wildcard origins are not permitted in production.
- The `ProxyFix` middleware is applied to correctly handle `X-Forwarded-For` headers from the Cloud Run load balancer.

---

## Security Headers

The following headers are injected on every response via an `after_request` hook in `main.py`:

| Header | Value |
|--------|-------|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `X-XSS-Protection` | `1; mode=block` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` (production only) |
| `Content-Security-Policy` | See policy below |

**CSP policy**:
```
default-src 'self';
script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;
style-src 'self' 'unsafe-inline';
img-src 'self' data: https: blob:;
connect-src 'self' https://storage.googleapis.com;
media-src 'self' https://storage.googleapis.com blob:;
object-src 'none';
frame-ancestors 'none'
```

---

## Input Validation

### File Uploads

- File extensions are validated against an explicit allowlist before any processing begins.
- MIME type is not trusted from the `Content-Type` header; `python-magic` validates against file magic bytes for standard video uploads.
- Maximum upload sizes are enforced at the application layer before files reach GCS.
- Filenames are sanitized with `werkzeug.utils.secure_filename` before use.

### Text Input Sanitization

User-supplied text fields (workspace names, descriptions, context strings) are processed by `infrastructure/validators/text_sanitizer.py` before persistence:

- Control characters and null bytes are stripped.
- Injection patterns (inline scripts, `<iframe>`, event handler attributes) are detected and rejected; injection attempts are logged at WARNING level.
- HTML special characters are escaped with `html.escape()`.
- Filesystem-unsafe characters (`/ \ < > : " | ? *`) are rejected in name fields.
- Per-field length limits are enforced after sanitization (name: 50 chars, description: 200 chars, context: 1 000 chars).

### ID Format Validation

Sensitive path parameters are validated against strict regular expressions before any database access:

- `analysis_id` for audio: `^aud_\d{8}_\d{6}_[a-f0-9]{8}$`
- `video_id` for security: `^sec_video_\d{8}_\d{6}_[a-f0-9]{8}$`

This prevents path traversal and injection via resource identifiers (OWASP A01).

### Request Bodies

All JSON request bodies are parsed with `request.get_json()` which returns `None` on malformed input. Required fields are checked explicitly; missing fields return `400` before any business logic executes.

---

## Rate Limiting

Flask-Limiter is backed by **Redis** in all environments where `REDIS_URL` is configured. This ensures limits are shared across all worker processes.

Rate limit keys are derived from:
1. Authenticated user identity (session-based, preferred).
2. `X-Forwarded-For` first IP.
3. `request.remote_addr` as fallback.

CORS preflight (`OPTIONS`) requests are exempted from rate limiting via `@limiter.request_filter`.

See [API.md](API.md) for per-endpoint limits.

---

## Internal Worker Communication

The `/process` worker callback endpoints require the `X-Internal-Worker-Token` header. Tokens are compared with `hmac.compare_digest` to prevent timing attacks. If `WORKER_INTERNAL_TOKEN` is not set, the endpoint returns `500` — not `401` — to signal a configuration error rather than silently degrading security.

---

## GCP Credentials

### Local Development

Application Default Credentials (ADC) are used via `gcloud auth application-default login`. The ADC token is mounted from `${APPDATA}/gcloud` into containers. This credential mode does not provide a service account private key; operations requiring RSA signing (GCS Signed URLs) are unavailable and must use the server-side streaming proxy instead.

### Container / Cloud Run

In production, credentials are provided through the following priority order:

1. **`GCP_CREDENTIALS_B64`** — Base64-encoded service account JSON injected as an environment variable (via Secret Manager). Decoded at startup into a temporary file with `0o600` permissions.
2. **`GCP_CREDENTIALS_JSON`** — Raw JSON string (less preferred).
3. **Workload Identity / ADC** — If neither variable is set, the GCP SDK uses Application Default Credentials (recommended for Cloud Run with an attached service account).

Temporary credential files are created with `tempfile.mkstemp` and restricted to owner read/write only.

---

## Secrets Management

In production, sensitive values (`SECRET_KEY`, `REDIS_URL`, `GEMINI_API_KEY`, `WORKER_INTERNAL_TOKEN`) are stored in **GCP Secret Manager** and injected at runtime. They are never stored in environment variables committed to source control or in container images.

---

## Security Logging

A dedicated `SecurityAnalysisLogger` (singleton) writes to a separate rotating log file (`logs/security/security_analysis.log`) at DEBUG level, capturing every phase of the surveillance video pipeline with video ID and phase context. Errors are duplicated to `logs/security/security_errors.log`.

---

## OWASP Top 10 Mapping

| OWASP Category | Controls Implemented |
|----------------|---------------------|
| A01 Broken Access Control | Ownership validation on every resource access; strict ID format enforcement; session-based auth with SOCIO role; atomic Firestore transactions prevent privilege escalation on workspace creation |
| A02 Cryptographic Failures | bcrypt for passwords; HTTPS enforced at load balancer; credentials in Secret Manager; no private keys in ADC environments |
| A03 Injection | Parameterized Firestore queries via SDK; no raw SQL; regex-validated IDs; `secure_filename` for filenames; `text_sanitizer.py` for all user text fields with injection pattern detection |
| A04 Insecure Design | Clean Architecture separates HTTP from business logic; domain entities enforce invariants; atomic transactions prevent race conditions |
| A05 Security Misconfiguration | `SECRET_KEY` validated as required at startup; WORKER_INTERNAL_TOKEN checked on every internal call; `0o600` on credential files; security headers on every response |
| A06 Vulnerable Components | Automated weekly audits via `pip-audit` (Python) and `npm audit` (Node) in `security-audit.yml`; Trivy image scanning |
| A07 Authentication Failures | Account lockout; bcrypt; no credential logging; rate limiting on login |
| A08 Software Integrity | Multi-stage Dockerfiles; pinned dependency versions with upper bounds; Bandit SAST in CI |
| A09 Logging Failures | Structured logging on all requests; request ID tracing; dedicated security log; workspace audit log; Cloud Logging in production |
| A10 SSRF | No user-controlled URL fetching; GCS streaming proxy validates ownership before accessing blobs; all external calls use hardcoded GCP SDK endpoints |

---

## CI Security Audit

The `security-audit.yml` workflow runs on push to `main`/`develop`, on PRs, and weekly:

- **pip-audit**: Scans `requirements.txt` against the Python Advisory Database.
- **npm audit**: Scans `package.json` dependencies; fails on `critical` severity.
- **Bandit**: Python SAST scan, fails on HIGH severity issues (`-lll` flag).
- **Trivy**: Container image vulnerability scan.

Audit reports are uploaded as GitHub Actions artifacts with a 30-day retention period.

---

**Last Updated**: May 15, 2026  
**Version**: 3.3.0



