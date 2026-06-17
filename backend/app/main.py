"""CounselIQ FastAPI application entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Liveness probe used by Docker, ECS, and load balancers."""
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(UTC).isoformat(),
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
