"""CounselIQ FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.v1.analysis import router as analysis_router
from app.api.v1.auth import router as auth_router
from app.api.v1.documents import router as documents_router
from app.api.v1.regulatory import router as regulatory_router
from app.api.v1.reviews import router as reviews_router
from app.api.v1.users import router as users_router
from app.api.v1.websocket import router as ws_router
from app.config import settings
from app.db import init_db
from app.db.session import engine
from app.middleware.rate_limit import limiter, rate_limit_exceeded_handler
from app.middleware.request_id import RequestIDMiddleware
from app.utils.logging import configure_logging

configure_logging()
logger = logging.getLogger("counseliq.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup / shutdown lifecycle."""
    logger.info(
        "Starting CounselIQ API",
        extra={"version": __version__, "environment": settings.ENVIRONMENT},
    )
    await init_db()
    logger.info("Database connection established")
    yield
    logger.info("Shutting down CounselIQ API")


app = FastAPI(
    title="CounselIQ API",
    description="Legal compliance multi-agent AI platform for Indian enterprises.",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# --- Rate limiting ----------------------------------------------------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Middleware is applied outermost-last, so order of addition matters:
#   CORS (outermost) -> RequestID -> SlowAPI -> routes
# CORS outermost ensures even 429/500 responses carry CORS headers; RequestID
# wraps the rate limiter so throttled responses still get an X-Request-ID.
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)


# --- Global exception handlers ----------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Consistent ``{"detail": ...}`` shape for all HTTPExceptions.

    Preserves any headers the exception carries (e.g. ``WWW-Authenticate`` on
    401s) so auth semantics are unchanged.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all: log the full traceback, return a safe generic 500.

    Internal error details, stack traces, and DB info are never leaked to the
    client — they go to the logs (correlated by request_id) only.
    """
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
        extra={"request_id": request_id},
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred"},
    )


@app.get("/health", tags=["system"])
@limiter.exempt
async def health(request: Request) -> dict[str, str]:
    """Liveness probe used by Docker, ECS, and load balancers."""
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def _redis_status() -> str:
    """Synchronous Redis ping (run in a thread from the async handler)."""
    try:
        import redis

        client = redis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1
        )
        client.ping()
        return "connected"
    except Exception:  # noqa: BLE001 - health check must never raise
        return "error"


def _celery_worker_count() -> int | str:
    """Count responding Celery workers (run in a thread; broker call blocks)."""
    try:
        from app.tasks.celery_app import celery_app

        replies = celery_app.control.ping(timeout=0.75)
        return len(replies) if replies else 0
    except Exception:  # noqa: BLE001 - health check must never raise
        return "unknown"


@app.get("/health/detailed", tags=["system"])
@limiter.exempt
async def health_detailed(request: Request) -> dict[str, object]:
    """Dependency health for uptime monitoring. No auth, no sensitive info."""
    database = "connected"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - report, don't raise
        database = "error"

    redis_status, celery_workers = await asyncio.gather(
        asyncio.to_thread(_redis_status),
        asyncio.to_thread(_celery_worker_count),
    )

    healthy = database == "connected" and redis_status == "connected"
    return {
        "status": "ok" if healthy else "degraded",
        "environment": settings.ENVIRONMENT,
        "database": database,
        "redis": redis_status,
        "celery_workers": celery_workers,
    }


# Versioned API surface. Feature routers are mounted under /api/v1.
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(reviews_router, prefix="/api/v1")
app.include_router(regulatory_router, prefix="/api/v1")

# WebSocket router is mounted at the root (no /api/v1 prefix):
#   ws://<host>/ws/{organisation_id}?token=<jwt>
app.include_router(ws_router)
