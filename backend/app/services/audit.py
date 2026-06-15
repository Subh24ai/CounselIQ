"""Audit-log service with tamper-evident hash chaining.

Each audit entry stores ``chained_hash = SHA256(previous_hash + content)`` where
``previous_hash`` is the most recent entry's hash for the same organisation (or
the literal ``GENESIS`` for the first entry). Any retroactive edit to an entry
breaks every subsequent hash, making tampering detectable.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog

GENESIS_HASH = "GENESIS"


async def _latest_hash(db: AsyncSession, organisation_id: UUID) -> str:
    """Return the most recent chained_hash for an org, or GENESIS if none."""
    result = await db.execute(
        select(AuditLog.chained_hash)
        .where(AuditLog.organisation_id == organisation_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(1)
    )
    previous = result.scalar_one_or_none()
    return previous or GENESIS_HASH


async def write_audit_log(
    db: AsyncSession,
    organisation_id: UUID,
    action: str,
    *,
    user_id: UUID | None = None,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Create and persist a hash-chained audit-log entry.

    The new entry is added and flushed (so it is queryable within the current
    transaction); committing is the caller's responsibility.
    """
    payload = payload or {}
    previous_hash = await _latest_hash(db, organisation_id)

    timestamp = datetime.now(UTC).isoformat()
    content_str = f"{organisation_id}{user_id}{action}{resource_id}{timestamp}"
    chained_hash = hashlib.sha256(
        (previous_hash + content_str).encode("utf-8")
    ).hexdigest()

    entry = AuditLog(
        organisation_id=organisation_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=payload,
        ip_address=ip_address,
        chained_hash=chained_hash,
    )
    db.add(entry)
    await db.flush()
    return entry
