"""Shared pytest fixtures for the CounselIQ backend."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.db.session import get_db
from app.main import app

# Database used by the model tests. Defaults to the local Docker Postgres
# exposed on 5433; overridable via DATABASE_URL for CI.
TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://counseliq:counseliq@localhost:5433/counseliq",
)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An httpx AsyncClient wired directly to the ASGI app (no network)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """Session-scoped async engine against the migrated test database.

    Uses :class:`NullPool` so connections are not held open across the suite.
    The session-wide event loop (configured in pyproject) lets this single
    engine be reused safely by every test.
    """
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, future=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A transaction-scoped session that is rolled back after each test.

    Each test runs inside an outer transaction that is rolled back on teardown,
    so tests never persist data and remain isolated from one another.
    """
    connection = await db_engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def api_connection(db_engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """A single test connection wrapped in an outer transaction.

    Shared by :func:`api_client` and :func:`api_session` so request handlers and
    test-side data setup observe each other's commits (savepoint releases) while
    the outer transaction is rolled back on teardown, keeping the DB pristine.
    """
    connection = await db_engine.connect()
    transaction = await connection.begin()
    try:
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def api_client(
    api_connection: AsyncConnection,
) -> AsyncIterator[AsyncClient]:
    """An AsyncClient whose requests share one rolled-back DB transaction.

    The app's ``get_db`` dependency is overridden to yield sessions bound to a
    single test connection using ``join_transaction_mode='create_savepoint'``,
    so endpoint ``commit()`` calls only release savepoints. The outer
    transaction is rolled back on teardown, keeping the database pristine while
    still letting request handlers commit as they do in production.
    """
    test_session_factory = async_sessionmaker(
        bind=api_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def api_session(
    api_connection: AsyncConnection,
) -> AsyncIterator[AsyncSession]:
    """A session on the same connection as :func:`api_client`.

    Lets a test set up or inspect rows that request handlers can see (and vice
    versa) — e.g. marking a document ``extracted`` to simulate the extraction
    task completing without running the real Celery pipeline.
    """
    factory = async_sessionmaker(
        bind=api_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    async with factory() as session:
        yield session
