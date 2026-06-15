"""Tests for the /health endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert "environment" in body
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_health_timestamp_is_iso8601(client: AsyncClient) -> None:
    from datetime import datetime

    response = await client.get("/health")
    body = response.json()

    # Should parse cleanly as an ISO-8601 timestamp.
    parsed = datetime.fromisoformat(body["timestamp"])
    assert parsed.tzinfo is not None
