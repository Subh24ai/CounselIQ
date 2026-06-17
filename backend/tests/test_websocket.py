"""Tests for the real-time WebSocket status endpoint.

WebSocket auth uses a JWT ``token`` query parameter (the handshake cannot carry
an Authorization header).

The synchronous TestClient runs the app in its own event loop per instance. To
avoid the production async engine pooling connections across loops, ``get_db``
is overridden with a NullPool engine and the app lifespan is not started (the DB
is already migrated; no startup work is needed for these tests). The seeded
org+user are committed via a synchronous session and removed on teardown.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.db.session import SyncSessionLocal, get_db
from app.main import app
from app.models import Organisation, User
from app.utils.security import create_access_token, hash_password


@pytest.fixture
def ws_env() -> Iterator[SimpleNamespace]:
    """Seed a committed org+user, wire a NullPool-backed TestClient, clean up."""
    suffix = uuid.uuid4().hex[:8]
    session = SyncSessionLocal()
    org = Organisation(name=f"WS Org {suffix}", domain=f"ws-{suffix}.example")
    session.add(org)
    session.flush()
    user = User(
        organisation_id=org.id,
        email=f"ws-{suffix}@example.com",
        hashed_password=hash_password("x"),
        role="legal_counsel",
        is_active=True,
    )
    session.add(user)
    session.flush()
    session.commit()
    org_id, user_id = str(org.id), str(user.id)
    session.close()

    token = create_access_token({"sub": user_id})

    # Fresh NullPool engine so connections are never reused across the
    # TestClient's event loop boundaries.
    test_engine = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, future=True
    )

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(test_engine, expire_on_commit=False) as s:
            yield s

    app.dependency_overrides[get_db] = _override_get_db

    try:
        # No `with` block: the app lifespan (init_db) is intentionally skipped.
        client = TestClient(app)
        yield SimpleNamespace(
            client=client, org_id=org_id, user_id=user_id, token=token
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(test_engine.dispose())
        cleanup = SyncSessionLocal()
        obj = cleanup.get(Organisation, uuid.UUID(org_id))
        if obj is not None:
            cleanup.delete(obj)  # cascade removes the user
            cleanup.commit()
        cleanup.close()


def test_ws_connect_valid_token(ws_env: SimpleNamespace) -> None:
    url = f"/ws/{ws_env.org_id}?token={ws_env.token}"
    with ws_env.client.websocket_connect(url) as ws:
        msg = ws.receive_json()
        assert msg["type"] == "connected"
        assert msg["organisation_id"] == ws_env.org_id
        assert msg["user_id"] == ws_env.user_id


def test_ws_connect_real_token_claims(ws_env: SimpleNamespace) -> None:
    """Connect with a token shaped exactly like production's ``_issue_tokens``.

    Production tokens carry ``sub`` + ``org`` + ``role`` claims (see
    ``app/api/v1/auth.py``), not the bare ``sub`` the other tests use. This
    exercises the real claim shape the handshake receives in the browser and
    would have caught a claim-key/comparison mismatch in the endpoint.
    """
    # Mirror auth._issue_tokens() precisely.
    token = create_access_token(
        {"sub": ws_env.user_id, "org": ws_env.org_id, "role": "legal_counsel"}
    )
    url = f"/ws/{ws_env.org_id}?token={token}"
    with ws_env.client.websocket_connect(url) as ws:
        msg = ws.receive_json()
        assert msg["type"] == "connected"
        assert msg["organisation_id"] == ws_env.org_id
        assert msg["user_id"] == ws_env.user_id


def test_ws_connect_invalid_token(ws_env: SimpleNamespace) -> None:
    url = f"/ws/{ws_env.org_id}?token=not-a-real-token"
    with pytest.raises(WebSocketDisconnect) as exc, ws_env.client.websocket_connect(url) as ws:
        ws.receive_json()
    assert exc.value.code == 4001


def test_ws_connect_org_case_insensitive(ws_env: SimpleNamespace) -> None:
    """An uppercased org UUID in the URL must still authenticate.

    UUIDs are case-insensitive by value; the endpoint compares ``UUID`` objects
    rather than string forms, so formatting differences between the URL and the
    canonical DB value must not produce a spurious 4003.
    """
    url = f"/ws/{ws_env.org_id.upper()}?token={ws_env.token}"
    with ws_env.client.websocket_connect(url) as ws:
        msg = ws.receive_json()
        assert msg["type"] == "connected"
        # Reported back in canonical (lowercase) form.
        assert msg["organisation_id"] == ws_env.org_id


def test_ws_ping_pong(ws_env: SimpleNamespace) -> None:
    url = f"/ws/{ws_env.org_id}?token={ws_env.token}"
    with ws_env.client.websocket_connect(url) as ws:
        ws.receive_json()  # consume the initial "connected" frame
        ws.send_text("ping")
        assert ws.receive_text() == '{"type":"pong"}'


def test_ws_wrong_org(ws_env: SimpleNamespace) -> None:
    other_org = str(uuid.uuid4())
    url = f"/ws/{other_org}?token={ws_env.token}"
    with pytest.raises(WebSocketDisconnect) as exc, ws_env.client.websocket_connect(url) as ws:
        ws.receive_json()
    assert exc.value.code == 4003
