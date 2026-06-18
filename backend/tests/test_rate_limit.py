"""Rate limiting tests.

The limiter is disabled suite-wide (see conftest) so other tests aren't
throttled; this test re-enables it locally and restores it afterwards.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.middleware.rate_limit import limiter

API = "/api/v1"


@pytest.mark.asyncio
async def test_rate_limited_success_path_returns_200(
    api_client: AsyncClient,
) -> None:
    """A successful call to a rate-limited endpoint must still succeed.

    Regression guard: with slowapi ``headers_enabled``, a decorated endpoint
    needs a ``response`` parameter or the success path 500s while injecting
    rate-limit headers — which only shows up when the limiter is enabled.
    """
    limiter.reset()
    limiter.enabled = True
    try:
        suffix = uuid.uuid4().hex[:8]
        resp = await api_client.post(
            f"{API}/auth/register",
            json={
                "organisation_name": f"Org {suffix}",
                "domain": f"{suffix}.example",
                "email": f"admin-{suffix}@example.com",
                "password": "supersecret123",
                "full_name": "Admin",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["access_token"]
    finally:
        limiter.enabled = False
        limiter.reset()


@pytest.mark.asyncio
async def test_rate_limit_login_endpoint(api_client: AsyncClient) -> None:
    limiter.reset()
    limiter.enabled = True
    try:
        statuses: list[int] = []
        last = None
        for _ in range(11):
            last = await api_client.post(
                f"{API}/auth/login",
                json={"email": "nobody@example.com", "password": "wrong"},
            )
            statuses.append(last.status_code)

        # The login limit is 10/minute per IP: the first 10 are processed
        # (401 invalid credentials), the 11th is throttled.
        assert statuses[:10] == [401] * 10, statuses
        assert statuses[10] == 429, statuses
        assert last is not None
        assert "retry-after" in {k.lower() for k in last.headers}
    finally:
        limiter.enabled = False
        limiter.reset()
