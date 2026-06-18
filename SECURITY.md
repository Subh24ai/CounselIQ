# Security

This document summarises the security posture of CounselIQ: what is hardened
today, and what must still be addressed before handling real client data in
production. It is a living document — update it as the threat model evolves.

## Reporting a vulnerability

Email the maintainers privately rather than opening a public issue. Please
include reproduction steps and the affected component.

## What is hardened today

**Authentication & authorisation**
- JWT access/refresh tokens; passwords hashed with bcrypt (passlib).
- Role-based access control (`org_admin`, `legal_counsel`, `compliance_officer`,
  `viewer`) enforced in the service layer, not just the router.
- Every data query is scoped to the caller's `organisation_id` — no cross-tenant
  reads, including the pgvector regulatory-impact matching.
- In `ENVIRONMENT=production`, the app refuses to boot unless `JWT_SECRET_KEY`
  is ≥ 32 chars and not a known insecure default (see `app/config.py`).

**Rate limiting** (`app/middleware/rate_limit.py`, slowapi + Redis)
- Default 300/min, keyed per user (authenticated) or per IP (anonymous).
- Stricter limits on expensive/abuse-prone routes: login 10/min·IP,
  register 5/min·IP, document upload 10/min·user, analysis 5/min·user.
- 429 responses carry `Retry-After`. Storage failures degrade gracefully
  (in-memory fallback) rather than taking the API down. WebSockets are exempt.

**Input validation**
- Uploads are validated by magic bytes (PDF `%PDF-`, DOCX/OOXML ZIP signature,
  TXT must decode as UTF-8 and contain no binary signatures) — the spoofable
  `Content-Type` header is not trusted. 50 MB ceiling.
- Request bodies validated by Pydantic schemas.

**Output / XSS**
- React escapes all interpolated strings by default.
- `react-markdown` renders the analysis summary **without** raw HTML
  (`rehype-raw` is intentionally not installed), so injected `<script>` is inert.
- No `dangerouslySetInnerHTML` anywhere in the frontend.

**Error handling & observability**
- Global exception handler returns a generic 500 (`{"detail": "An unexpected
  error occurred"}`) and never leaks stack traces, DB details, or internal
  errors to clients; full tracebacks go to structured logs only.
- Every request carries an `X-Request-ID` (also stamped on each log line) for
  traceability. `GET /health/detailed` reports DB/Redis/Celery status.
- Audit log is append-only and hash-chained.

**Secrets**
- `.env` / `.env.local` are gitignored (only `.env.example` is committed).

## What still needs attention before production

- **AWS / Textract / S3 IAM** — dev uses LocalStack. Production must use a
  dedicated, least-privilege IAM role (scoped to the specific bucket prefix and
  Textract actions) — never root/admin keys. Enable S3 SSE + bucket policies
  blocking public access.
- **Secrets management** — load `JWT_SECRET_KEY`, DB, and provider keys from a
  managed secret store (AWS Secrets Manager / SSM), not a checked-in `.env`.
  Rotate the JWT secret and DB credentials on a schedule.
- **Transport** — terminate TLS at the edge; set HSTS and secure cookie flags;
  restrict `CORS_ORIGINS` to the real frontend origin(s).
- **Token revocation** — logout is currently client-side only. Add a server-side
  denylist (e.g. Redis) or short-lived access tokens with rotating refresh
  tokens for true revocation.
- **Dependency & container scanning** — wire `pip-audit`/`npm audit` and image
  scanning into CI; pin and review the `torch`/`sentence-transformers` chain.
- **DB hardening** — least-privilege Postgres role for the app (no superuser),
  TLS to the database, encrypted backups.
- **PII handling** — extracted contract text and clause embeddings are stored;
  define retention/deletion policies and ensure document delete also purges S3
  objects and embeddings.
- **Monitoring/alerting** — ship logs/metrics to a real backend and alert on
  500 spikes, auth failures, and rate-limit saturation.
