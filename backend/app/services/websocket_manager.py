"""In-process WebSocket connection registry and broadcaster.

Connections are grouped by ``organisation_id`` (the tenant boundary). For each
org with at least one live connection, a single Redis-subscriber asyncio task
forwards cross-process events to that org's sockets; the task is started on the
first connection and cancelled when the last one disconnects.

This module must never be imported by Celery workers — workers publish events
via :mod:`app.services.events` (Redis) instead.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import WebSocket

logger = logging.getLogger("counseliq.ws.manager")


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ConnectionManager:
    """Tracks live WebSocket connections per organisation and broadcasts to them."""

    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}
        self.subscriber_tasks: dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, organisation_id: str) -> None:
        """Accept a socket and ensure the org's Redis subscriber is running."""
        await websocket.accept()
        self.active_connections.setdefault(organisation_id, []).append(websocket)

        if organisation_id not in self.subscriber_tasks:
            # Imported lazily to avoid a circular import: redis_subscriber
            # imports this module's ``ws_manager`` singleton.
            from app.services.redis_subscriber import subscribe_and_forward

            self.subscriber_tasks[organisation_id] = asyncio.create_task(
                subscribe_and_forward(organisation_id)
            )
            logger.info("Started Redis subscriber for org %s", organisation_id)

    def disconnect(self, websocket: WebSocket, organisation_id: str) -> None:
        """Drop a socket; tear down the org's subscriber when none remain."""
        connections = self.active_connections.get(organisation_id)
        if connections and websocket in connections:
            connections.remove(websocket)

        if not self.active_connections.get(organisation_id):
            self.active_connections.pop(organisation_id, None)
            task = self.subscriber_tasks.pop(organisation_id, None)
            if task is not None:
                task.cancel()
                logger.info("Stopped Redis subscriber for org %s", organisation_id)

    async def broadcast_to_org(self, organisation_id: str, message: dict) -> None:
        """Send ``message`` (as JSON) to every live socket for an org.

        Sockets that error on send are treated as dead and disconnected.
        """
        # Iterate over a copy so disconnect() can mutate the live list.
        for websocket in list(self.active_connections.get(organisation_id, [])):
            try:
                await websocket.send_json(message)
            except Exception:  # noqa: BLE001 - a dead socket must not stop the broadcast
                self.disconnect(websocket, organisation_id)

    async def send_job_update(
        self,
        organisation_id: str,
        job_id: str,
        status: str,
        progress: dict | None = None,
    ) -> None:
        await self.broadcast_to_org(
            organisation_id,
            {
                "type": "job_update",
                "job_id": job_id,
                "status": status,
                "progress": progress or {},
                "timestamp": _now(),
            },
        )

    async def send_agent_step(
        self, organisation_id: str, job_id: str, step: dict
    ) -> None:
        await self.broadcast_to_org(
            organisation_id,
            {
                "type": "agent_step",
                "job_id": job_id,
                "step": step,
                "timestamp": _now(),
            },
        )


# Process-wide singleton used by the WebSocket endpoint and the Redis subscriber.
ws_manager = ConnectionManager()
