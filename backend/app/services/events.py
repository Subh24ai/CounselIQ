"""Synchronous event publisher for cross-process notifications.

Celery workers run in separate processes and cannot touch the in-process
WebSocket manager. They publish events to a per-organisation Redis channel here;
the FastAPI process subscribes (see :mod:`app.services.redis_subscriber`) and
forwards them to connected WebSocket clients.

Publishing is best-effort: a Redis failure must never fail the analysis task, so
errors are logged and swallowed.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import redis

from app.config import settings

logger = logging.getLogger("counseliq.events")

# Lazy connection — redis-py connects on first command, so import never blocks.
redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _channel(organisation_id: str) -> str:
    return f"counseliq:org:{organisation_id}:events"


def publish_job_event(organisation_id: str, event: dict) -> None:
    """Publish a single event to an organisation's channel (best-effort)."""
    try:
        redis_client.publish(_channel(organisation_id), json.dumps(event))
    except Exception as exc:  # noqa: BLE001 - notifications are best-effort
        logger.warning(
            "Failed to publish event for org %s: %s", organisation_id, exc
        )


def publish_job_update(
    organisation_id: str,
    job_id: str,
    status: str,
    progress: dict | None = None,
) -> None:
    """Publish an analysis-job status change."""
    publish_job_event(
        organisation_id,
        {
            "type": "job_update",
            "job_id": job_id,
            "status": status,
            "progress": progress or {},
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


def publish_agent_step(organisation_id: str, job_id: str, step: dict) -> None:
    """Publish a single agent trace step as it completes."""
    publish_job_event(
        organisation_id,
        {
            "type": "agent_step",
            "job_id": job_id,
            "step": step,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
