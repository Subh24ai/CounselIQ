"""End-to-end tests for the authentication and authorisation system.

All requests go through the ASGI app via ``api_client``, which shares a single
database transaction that is rolled back after each test for isolation.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

API = "/api/v1"


def _register_payload(**overrides: object) -> dict[str, object]:
    """Build a unique registration payload."""
    suffix = uuid.uuid4().hex[:8]
    payload: dict[str, object] = {
        "organisation_name": f"Org {suffix}",
        "domain": f"{suffix}.example",
        "email": f"admin-{suffix}@example.com",
        "password": "supersecret123",
        "full_name": "Admin User",
    }
    payload.update(overrides)
    return payload


async def _register(client: AsyncClient, **overrides: object) -> dict:
    resp = await client.post(f"{API}/auth/register", json=_register_payload(**overrides))
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_register(api_client: AsyncClient) -> None:
    resp = await api_client.post(f"{API}/auth/register", json=_register_payload())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login(api_client: AsyncClient) -> None:
    payload = _register_payload()
    await api_client.post(f"{API}/auth/register", json=payload)

    resp = await api_client.post(
        f"{API}/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_login_wrong_password(api_client: AsyncClient) -> None:
    payload = _register_payload()
    await api_client.post(f"{API}/auth/register", json=payload)

    resp = await api_client.post(
        f"{API}/auth/login",
        json={"email": payload["email"], "password": "wrong-password"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me(api_client: AsyncClient) -> None:
    payload = _register_payload()
    tokens = (
        await api_client.post(f"{API}/auth/register", json=payload)
    ).json()

    resp = await api_client.get(
        f"{API}/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == payload["email"]
    assert body["role"] == "org_admin"
    assert "hashed_password" not in body
    assert "password" not in body


@pytest.mark.asyncio
async def test_refresh(api_client: AsyncClient) -> None:
    tokens = await _register(api_client)

    resp = await api_client.post(
        f"{API}/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    # Refresh token is not rotated.
    assert body["refresh_token"] == tokens["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_rejects_access_token(api_client: AsyncClient) -> None:
    tokens = await _register(api_client)
    # An access token must not be usable as a refresh token.
    resp = await api_client.post(
        f"{API}/auth/refresh",
        json={"refresh_token": tokens["access_token"]},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_role_guard(api_client: AsyncClient) -> None:
    # Register an org (admin), then create a viewer via the admin endpoint.
    admin = await _register(api_client)
    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}

    viewer_email = f"viewer-{uuid.uuid4().hex[:8]}@example.com"
    create_resp = await api_client.post(
        f"{API}/users/",
        headers=admin_headers,
        json={
            "email": viewer_email,
            "full_name": "View Only",
            "role": "viewer",
            "password": "viewerpass123",
        },
    )
    assert create_resp.status_code == 201, create_resp.text

    viewer_tokens = (
        await api_client.post(
            f"{API}/auth/login",
            json={"email": viewer_email, "password": "viewerpass123"},
        )
    ).json()
    viewer_headers = {"Authorization": f"Bearer {viewer_tokens['access_token']}"}

    # Viewer hitting an org_admin-only endpoint must be forbidden.
    resp = await api_client.get(f"{API}/users/", headers=viewer_headers)
    assert resp.status_code == 403
    assert "not permitted" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cross_org_isolation(api_client: AsyncClient) -> None:
    # Org 1 admin.
    org1 = await _register(api_client)
    org1_headers = {"Authorization": f"Bearer {org1['access_token']}"}

    # Org 2 admin.
    org2 = await _register(api_client)
    org2_headers = {"Authorization": f"Bearer {org2['access_token']}"}
    org2_me = (await api_client.get(f"{API}/auth/me", headers=org2_headers)).json()
    org2_user_id = org2_me["id"]

    # Org 1 admin must not be able to read an org 2 user (404, not 200).
    resp = await api_client.get(
        f"{API}/users/{org2_user_id}", headers=org1_headers
    )
    assert resp.status_code == 404

    # Sanity: org 1 can read its own user.
    org1_me = (await api_client.get(f"{API}/auth/me", headers=org1_headers)).json()
    own = await api_client.get(
        f"{API}/users/{org1_me['id']}", headers=org1_headers
    )
    assert own.status_code == 200
