"""Rate limiting via slowapi (Redis-backed).

Keying strategy:
- Authenticated requests are keyed by the JWT subject (user id) so users behind
  a shared office IP / NAT are not throttled as one.
- Unauthenticated requests fall back to the client IP.

Defaults are generous (300/min); the genuinely expensive or abuse-prone
endpoints carry much stricter explicit limits (see the decorators in the auth,
documents, and analysis routers).

Resilience: storage errors are swallowed and an in-memory fallback is used, so a
Redis outage degrades rate limiting rather than taking the API down. WebSocket
connections bypass ``SlowAPIMiddleware`` entirely (it is HTTP-only), so live
updates are never throttled.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.utils.security import decode_access_token


def _bearer_subject(request: Request) -> str | None:
    """Cheaply extract the JWT subject from the Authorization header, if valid."""
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    payload = decode_access_token(auth[7:].strip())
    if not payload:
        return None
    subject = payload.get("sub")
    return str(subject) if subject else None


def user_or_ip_key(request: Request) -> str:
    """Per-user key when authenticated, else per-IP."""
    subject = _bearer_subject(request)
    if subject:
        return f"user:{subject}"
    return f"ip:{get_remote_address(request)}"


# 300/min default ceiling, keyed per user (or per IP when unauthenticated).
# Sensitive endpoints override this with stricter explicit limits.
limiter = Limiter(
    key_func=user_or_ip_key,
    default_limits=["300/minute"],
    storage_uri=settings.REDIS_URL,
    headers_enabled=True,
    retry_after="delta-seconds",
    swallow_errors=True,
    in_memory_fallback_enabled=True,
    enabled=settings.RATE_LIMIT_ENABLED,
)


def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """Return a clean 429 with a ``detail`` body and a ``Retry-After`` header."""
    response = JSONResponse(
        status_code=429,
        content={
            "detail": (
                "Rate limit exceeded. Please slow down and try again shortly."
            )
        },
    )
    # Adds Retry-After (delta-seconds) and X-RateLimit-* headers.
    return request.app.state.limiter._inject_headers(
        response, request.state.view_rate_limit
    )
