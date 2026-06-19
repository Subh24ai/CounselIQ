"""Tests for the organisation invitation system.

A single DB connection is shared between the API client (via a get_db override)
and the test-side session using savepoint sessions, so writes made by request
handlers and by the test setup are mutually visible while the outer transaction
is rolled back on teardown.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db.session import get_db
from app.main import app
from app.models import Invitation, User
from app.services.invitation import expire_stale_invitations
from app.utils.security import create_access_token, hash_password

API = "/api/v1"


def _auth_header(user: User) -> dict[str, str]:
    token = create_access_token(
        {"sub": str(user.id), "org": str(user.organisation_id), "role": user.role}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def env(db_engine: AsyncEngine) -> AsyncIterator[SimpleNamespace]:
    """Seed an org with admin/counsel/viewer users and yield a shared client."""
    connection = await db_engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    async def _override_get_db() -> AsyncIterator:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    suffix = uuid.uuid4().hex[:8]
    from app.models import Organisation

    async with factory() as s:
        org = Organisation(name=f"Inv Org {suffix}", domain=f"inv-{suffix}.example")
        s.add(org)
        await s.flush()

        admin = User(
            organisation_id=org.id,
            email=f"admin-{suffix}@example.com",
            hashed_password=hash_password("x"),
            role="org_admin",
            is_active=True,
        )
        counsel = User(
            organisation_id=org.id,
            email=f"counsel-{suffix}@example.com",
            hashed_password=hash_password("x"),
            role="legal_counsel",
            is_active=True,
        )
        viewer = User(
            organisation_id=org.id,
            email=f"viewer-{suffix}@example.com",
            hashed_password=hash_password("x"),
            role="viewer",
            is_active=True,
        )
        s.add_all([admin, counsel, viewer])
        await s.commit()

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield SimpleNamespace(
                client=client,
                factory=factory,
                suffix=suffix,
                org_id=org.id,
                admin=admin,
                counsel=counsel,
                viewer=viewer,
                admin_headers=_auth_header(admin),
                viewer_headers=_auth_header(viewer),
                invitee_email=f"invitee-{suffix}@example.com",
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        await transaction.rollback()
        await connection.close()


def _token_from_link(invite_link: str) -> str:
    return invite_link.rsplit("/invite/", 1)[1]


async def _create(env: SimpleNamespace, email: str, role: str = "legal_counsel"):
    return await env.client.post(
        f"{API}/invitations/",
        json={"email": email, "role": role},
        headers=env.admin_headers,
    )


@pytest.mark.asyncio
async def test_create_invitation(env: SimpleNamespace) -> None:
    resp = await _create(env, env.invitee_email)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == env.invitee_email
    assert body["role"] == "legal_counsel"
    assert body["status"] == "pending"
    # invite_link is computed and carries the (stored) token.
    token = _token_from_link(body["invite_link"])
    assert token and "/invite/" in body["invite_link"]

    # The token in the link matches the persisted row.
    async with env.factory() as s:
        inv = (
            await s.execute(select(Invitation).where(Invitation.email == env.invitee_email))
        ).scalar_one()
        assert inv.token == token


@pytest.mark.asyncio
async def test_create_invitation_duplicate_email(env: SimpleNamespace) -> None:
    assert (await _create(env, env.invitee_email)).status_code == 201
    dup = await _create(env, env.invitee_email)
    assert dup.status_code == 409
    assert "pending" in dup.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_invitation_existing_user(env: SimpleNamespace) -> None:
    # The counsel user already belongs to the org.
    resp = await _create(env, env.counsel.email)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_invitation_org_admin_role_blocked(env: SimpleNamespace) -> None:
    resp = await _create(env, env.invitee_email, role="org_admin")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_validate_token_valid(env: SimpleNamespace) -> None:
    token = _token_from_link((await _create(env, env.invitee_email)).json()["invite_link"])
    resp = await env.client.get(f"{API}/invitations/validate/{token}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == env.invitee_email
    assert body["role"] == "legal_counsel"
    assert body["organisation_name"].startswith("Inv Org")


@pytest.mark.asyncio
async def test_validate_token_expired(env: SimpleNamespace) -> None:
    token = _token_from_link((await _create(env, env.invitee_email)).json()["invite_link"])
    async with env.factory() as s:
        inv = (
            await s.execute(select(Invitation).where(Invitation.token == token))
        ).scalar_one()
        inv.expires_at = datetime.now(UTC) - timedelta(hours=1)
        await s.commit()

    resp = await env.client.get(f"{API}/invitations/validate/{token}")
    assert resp.status_code == 410
    assert "expired_at" in resp.json()


@pytest.mark.asyncio
async def test_accept_invitation(env: SimpleNamespace) -> None:
    token = _token_from_link((await _create(env, env.invitee_email)).json()["invite_link"])
    resp = await env.client.post(
        f"{API}/invitations/accept",
        json={
            "token": token,
            "full_name": "New Member",
            "password": "supersecret1",
            "confirm_password": "supersecret1",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["email"] == env.invitee_email
    assert body["user"]["role"] == "legal_counsel"

    async with env.factory() as s:
        user = (
            await s.execute(select(User).where(User.email == env.invitee_email))
        ).scalar_one()
        assert user.organisation_id == env.org_id
        assert user.role == "legal_counsel"


@pytest.mark.asyncio
async def test_accept_invitation_password_mismatch(env: SimpleNamespace) -> None:
    token = _token_from_link((await _create(env, env.invitee_email)).json()["invite_link"])
    resp = await env.client.post(
        f"{API}/invitations/accept",
        json={
            "token": token,
            "full_name": "New Member",
            "password": "supersecret1",
            "confirm_password": "different99",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_accept_invitation_twice(env: SimpleNamespace) -> None:
    token = _token_from_link((await _create(env, env.invitee_email)).json()["invite_link"])
    payload = {
        "token": token,
        "full_name": "New Member",
        "password": "supersecret1",
        "confirm_password": "supersecret1",
    }
    assert (await env.client.post(f"{API}/invitations/accept", json=payload)).status_code == 200
    second = await env.client.post(f"{API}/invitations/accept", json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_revoke_invitation(env: SimpleNamespace) -> None:
    created = (await _create(env, env.invitee_email)).json()
    invitation_id = created["id"]
    token = _token_from_link(created["invite_link"])

    revoke = await env.client.delete(
        f"{API}/invitations/{invitation_id}", headers=env.admin_headers
    )
    assert revoke.status_code == 200

    async with env.factory() as s:
        inv = (
            await s.execute(select(Invitation).where(Invitation.token == token))
        ).scalar_one()
        assert inv.status == "revoked"

    # A revoked invitation cannot be accepted.
    accept = await env.client.post(
        f"{API}/invitations/accept",
        json={
            "token": token,
            "full_name": "New Member",
            "password": "supersecret1",
            "confirm_password": "supersecret1",
        },
    )
    assert accept.status_code == 409


@pytest.mark.asyncio
async def test_viewer_cannot_invite(env: SimpleNamespace) -> None:
    resp = await env.client.post(
        f"{API}/invitations/",
        json={"email": env.invitee_email, "role": "viewer"},
        headers=env.viewer_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_invitation_expiry_task(env: SimpleNamespace) -> None:
    token = _token_from_link((await _create(env, env.invitee_email)).json()["invite_link"])
    async with env.factory() as s:
        inv = (
            await s.execute(select(Invitation).where(Invitation.token == token))
        ).scalar_one()
        inv.expires_at = datetime.now(UTC) - timedelta(hours=1)
        await s.commit()

    async with env.factory() as s:
        count = await expire_stale_invitations(s)
        await s.commit()
        assert count == 1

    async with env.factory() as s:
        inv = (
            await s.execute(select(Invitation).where(Invitation.token == token))
        ).scalar_one()
        assert inv.status == "expired"
