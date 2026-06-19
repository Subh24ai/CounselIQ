"""Celery task: expire stale invitations on a schedule.

Pending invitations past their 48-hour TTL are flipped to ``expired`` so the
public validate/accept endpoints reject them with a clean status even before a
user tries the link. Scheduled via ``celery beat`` (see celery_app.py).
"""

from __future__ import annotations

import asyncio
import logging

from app.db.session import async_session_factory
from app.services.invitation import expire_stale_invitations
from app.tasks.celery_app import celery_app

logger = logging.getLogger("counseliq.tasks.invitations")


async def _run_expire() -> int:
    async with async_session_factory() as session:
        count = await expire_stale_invitations(session)
        await session.commit()
        return count


@celery_app.task(
    name="app.tasks.invitations.expire_invitations_task",
    queue="default",
)
def expire_invitations_task() -> dict[str, int]:
    """Mark all pending-but-expired invitations as ``expired``."""
    expired = asyncio.run(_run_expire())
    logger.info("Expired %d stale invitation(s)", expired)
    return {"expired": expired}
