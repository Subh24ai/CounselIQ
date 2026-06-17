"""Celery task to backfill clause embeddings.

Clauses created before embedding-on-analysis existed have ``embedding IS NULL``
and would silently never match a regulatory update. Run this once after
deploying the regulatory monitor to embed them::

    celery -A app.tasks.celery_app:celery_app call \\
        app.tasks.embeddings.backfill_embeddings_task
"""

from __future__ import annotations

import asyncio
import logging

from app.db.session import async_session_factory
from app.services.regulatory import backfill_clause_embeddings
from app.tasks.celery_app import celery_app

logger = logging.getLogger("counseliq.tasks.embeddings")


async def _run_backfill() -> int:
    async with async_session_factory() as session:
        return await backfill_clause_embeddings(session, organisation_id=None)


@celery_app.task(
    name="app.tasks.embeddings.backfill_embeddings_task",
    bind=True,
    queue="default",
)
def backfill_embeddings_task(self) -> dict[str, int]:
    """Embed every clause across all organisations that lacks an embedding."""
    embedded = asyncio.run(_run_backfill())
    logger.info("Backfilled embeddings for %d clauses", embedded)
    return {"embedded": embedded}
