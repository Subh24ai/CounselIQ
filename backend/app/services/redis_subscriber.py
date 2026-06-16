"""Async Redis subscriber that bridges published events to WebSocket clients.

One :func:`subscribe_and_forward` task runs per organisation that has live
WebSocket connections. It is started by the connection manager on the first
connection and cancelled when the last connection for the org disconnects.

Uses ``redis.asyncio`` (built into redis-py >= 4.2) — no separate aioredis
package is required.
"""

from __future__ import annotations

import asyncio
import json
import logging

import redis.asyncio as aioredis

from app.config import settings
from app.services.websocket_manager import ws_manager

logger = logging.getLogger("counseliq.ws.subscriber")


def _channel(organisation_id: str) -> str:
    return f"counseliq:org:{organisation_id}:events"


async def subscribe_and_forward(organisation_id: str) -> None:
    """Forward this org's Redis channel messages to its WebSocket connections.

    Runs as an asyncio task inside the FastAPI process. Cleans up its Redis
    connection on cancellation (last socket gone) or on error.
    """
    channel = _channel(organisation_id)
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    try:
        await pubsub.subscribe(channel)
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                event = json.loads(message["data"])
            except (ValueError, TypeError):
                logger.warning("Discarding malformed event on %s", channel)
                continue
            await ws_manager.broadcast_to_org(organisation_id, event)
    except asyncio.CancelledError:
        # Normal teardown when the last WebSocket for this org disconnects.
        raise
    except Exception as exc:  # noqa: BLE001 - keep failures isolated to this org
        logger.error("Redis subscriber error org=%s: %s", organisation_id, exc)
    finally:
        try:
            await pubsub.aclose()
            await r.aclose()
        except Exception:  # noqa: BLE001 - best-effort cleanup
            pass
