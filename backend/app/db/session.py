"""Async database engine, session factory, and FastAPI dependency."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

logger = logging.getLogger("counseliq.db")

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    pool_pre_ping=True,
    future=True,
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


def _sync_database_url() -> str:
    """Return a synchronous (psycopg2) URL for non-async contexts (Celery)."""
    url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


# Synchronous engine/session for Celery workers, which run sync code.
sync_engine = create_engine(
    _sync_database_url(),
    pool_pre_ping=True,
    future=True,
)

SyncSessionLocal: sessionmaker[Session] = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a request-scoped :class:`AsyncSession`."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Ensure the pgvector extension exists and verify connectivity.

    Called from the FastAPI lifespan on startup. Schema creation itself is
    handled by Alembic migrations, not here. Raises a clear error if the
    database is unreachable so startup fails fast.
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - exercised on infra failure
        logger.error("Database initialisation failed: %s", exc)
        raise RuntimeError(
            "Could not initialise the database. Check DATABASE_URL and that "
            "Postgres (with the pgvector extension available) is reachable."
        ) from exc
    logger.info("Database connection verified and pgvector extension ensured.")
