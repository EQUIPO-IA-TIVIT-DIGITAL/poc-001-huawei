# Security and Compliance

## Authentication and Authorization

- Flask signed-cookie sessions use a CSPRNG-generated `SECRET_KEY` of at least 64 characters.
- Passwords use bcrypt; plaintext passwords are never persisted or logged.
- Redis-backed lockout limits failed login attempts to five per five minutes and locks accounts for 15 minutes.
- Resource ownership is validated on reads and writes for authenticated users.

## Transport and Headers

- Terminate TLS at the deployment reverse proxy and configure `CORS_ORIGIN` to the approved frontend origin.
- Responses use `nosniff`, `DENY` framing, HSTS in production, and a self-hosted content security policy.
- Media is served from application or configured MinIO endpoints; restrict the CSP to those local origins.

## Data and Secrets

- PostgreSQL credentials, MinIO access keys, Redis passwords, and worker tokens are supplied at runtime through the deployment secret mechanism.
- Do not bake `.env`, private keys, credential files, or database backups into images.
- PostgreSQL access is parameterized through SQLAlchemy. MinIO object keys and filesystem paths are validated before access.
- Object storage uses `s3://` URIs and filesystem storage uses `file://` URIs.

## Worker Security

- Internal callbacks require `X-Internal-Worker-Token` and compare it with `hmac.compare_digest`.
- RQ workers receive jobs through authenticated Redis and run media processing outside request handlers.
- Temporary media files are removed after processing and object lifecycle rules should expire transient prefixes.

## Logging Hygiene

- Connection URLs (Redis, database) are masked before logging; credentials never appear in plaintext in logs (`_mask_redis_url` in `job_queue.py`).
- Error responses sanitize stack traces and debug fields before returning 5xx payloads.
- Request correlation uses `X-Request-ID`; identifiers like usernames are masked (`u***e`) in auth logs.

## Push / Git Hygiene

- `.env` is gitignored and must never be committed; secrets are generated locally with a CSPRNG and rotated if exposed in logs or shared sessions.
- Commits must pass the local CI replica before pushing: `pytest`, `flake8`, `npm test` (tsc + vitest), and Docker image builds.
- Secret scanning (`gitleaks`) runs in CI; if a secret reaches history, rotate it immediately and force-remove it from the branch.

## Assurance

CI runs dependency audits, Bandit, Trivy, and frontend checks. Review audit findings, rotate runtime secrets, patch base images, and back up PostgreSQL to MinIO on an operational schedule.
