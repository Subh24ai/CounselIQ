"""Invitation service — create, accept, revoke, list, and expiry sweep.

All invariants live here in the service layer (never the router) so they hold
regardless of the entry point: an org_admin cannot invite another org_admin, an
email already in the org cannot be re-invited, an expired invite cannot be
accepted, and so on. Token generation is cryptographically secure
(:func:`secrets.token_urlsafe`).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Invitation, Organisation, User
from app.schemas.invitation import INVITABLE_ROLES
from app.services.audit import write_audit_log
from app.utils.security import hash_password

# Invitations live for 48 hours from creation.
INVITATION_TTL = timedelta(hours=48)


def _now() -> datetime:
    return datetime.now(UTC)


async def create_invitation(
    db: AsyncSession,
    organisation_id: UUID,
    invited_by_id: UUID,
    email: str,
    role: str,
) -> Invitation:
    """Create a pending invitation for ``email`` to join the organisation.

    Raises 422 if the role is not invitable (an org_admin can never be invited),
    and 409 if the email already belongs to a member or already has a pending
    invite in this organisation.
    """
    if role == "org_admin":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot invite org_admin role",
        )
    if role not in INVITABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid role. Allowed: {', '.join(INVITABLE_ROLES)}",
        )

    existing_user = (
        await db.execute(
            select(User.id).where(
                User.email == email,
                User.organisation_id == organisation_id,
            )
        )
    ).first()
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email is already a member of this organisation",
        )

    pending = (
        await db.execute(
            select(Invitation.id).where(
                Invitation.organisation_id == organisation_id,
                Invitation.email == email,
                Invitation.status == "pending",
            )
        )
    ).first()
    if pending is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An invitation is already pending for {email}",
        )

    invitation = Invitation(
        organisation_id=organisation_id,
        invited_by=invited_by_id,
        email=email,
        role=role,
        token=secrets.token_urlsafe(32),
        status="pending",
        expires_at=_now() + INVITATION_TTL,
    )
    db.add(invitation)
    await db.flush()

    await write_audit_log(
        db,
        organisation_id=organisation_id,
        action="invitation.created",
        user_id=invited_by_id,
        resource_type="invitation",
        resource_id=invitation.id,
        payload={"email": email, "role": role},
    )
    return invitation


async def get_invitation_by_token(
    db: AsyncSession, token: str
) -> Invitation | None:
    """Fetch an invitation by token with its organisation eagerly loaded."""
    result = await db.execute(
        select(Invitation)
        .options(selectinload(Invitation.organisation))
        .where(Invitation.token == token)
    )
    return result.scalar_one_or_none()


async def accept_invitation(
    db: AsyncSession,
    token: str,
    full_name: str,
    password: str,
) -> tuple[User, Organisation]:
    """Accept a pending invitation, creating the member's user account.

    Raises 404 (unknown token), 409 (already used/revoked, or the email now has
    an account), or 410 (expired). On success the invitation is marked accepted
    and the new ``(user, organisation)`` is returned.
    """
    invitation = await get_invitation_by_token(db, token)
    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )
    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invitation already used or revoked",
        )
    if invitation.expires_at <= _now():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Invitation has expired",
        )

    # Email is globally unique on users — a pre-existing account blocks accept.
    existing = (
        await db.execute(select(User.id).where(User.email == invitation.email))
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user = User(
        organisation_id=invitation.organisation_id,
        email=invitation.email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=invitation.role,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    invitation.status = "accepted"
    invitation.accepted_at = _now()
    invitation.accepted_by = user.id

    await write_audit_log(
        db,
        organisation_id=invitation.organisation_id,
        action="invitation.accepted",
        user_id=user.id,
        resource_type="invitation",
        resource_id=invitation.id,
        payload={"email": invitation.email, "role": invitation.role},
    )

    organisation = invitation.organisation
    if organisation is None:  # pragma: no cover - FK guarantees this is loaded
        organisation = (
            await db.execute(
                select(Organisation).where(
                    Organisation.id == invitation.organisation_id
                )
            )
        ).scalar_one()
    return user, organisation


async def revoke_invitation(
    db: AsyncSession,
    invitation_id: UUID,
    organisation_id: UUID,
    revoked_by_id: UUID,
) -> Invitation:
    """Revoke a pending invitation owned by the organisation.

    Raises 404 if it doesn't exist in this org, 409 if it is no longer pending.
    """
    invitation = (
        await db.execute(
            select(Invitation).where(
                Invitation.id == invitation_id,
                Invitation.organisation_id == organisation_id,
            )
        )
    ).scalar_one_or_none()
    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )
    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending invitations can be revoked",
        )

    invitation.status = "revoked"

    await write_audit_log(
        db,
        organisation_id=organisation_id,
        action="invitation.revoked",
        user_id=revoked_by_id,
        resource_type="invitation",
        resource_id=invitation.id,
        payload={"email": invitation.email},
    )
    return invitation


async def list_invitations(
    db: AsyncSession,
    organisation_id: UUID,
    status: str | None = None,
) -> list[Invitation]:
    """List an organisation's invitations (newest first), optionally filtered."""
    query = select(Invitation).where(
        Invitation.organisation_id == organisation_id
    )
    if status is not None:
        query = query.where(Invitation.status == status)
    query = query.order_by(Invitation.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def expire_stale_invitations(db: AsyncSession) -> int:
    """Flip every pending-but-past-expiry invitation to ``expired``.

    Returns the number of invitations expired. Called by the Celery beat task;
    committing is the caller's responsibility.
    """
    result = await db.execute(
        update(Invitation)
        .where(
            Invitation.status == "pending",
            Invitation.expires_at < _now(),
        )
        .values(status="expired")
    )
    return result.rowcount or 0
