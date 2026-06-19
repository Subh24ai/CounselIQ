"""Invitations router.

Admin endpoints (create/list/revoke) require ``org_admin`` and are org-scoped.
The accept and validate endpoints are PUBLIC (no auth) so an invited person —
who has no account yet — can open the link, see who invited them, and join.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_db
from app.models import User
from app.schemas.invitation import (
    InvitationAcceptRequest,
    InvitationAcceptResponse,
    InvitationCreate,
    InvitationResponse,
    InvitationValidateResponse,
)
from app.schemas.organisation import OrganisationResponse
from app.schemas.user import UserResponse
from app.services import invitation as invitation_service
from app.utils.security import create_access_token, create_refresh_token

router = APIRouter(prefix="/invitations", tags=["invitations"])

require_org_admin = require_roles("org_admin")


@router.post(
    "/",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invitation(
    body: InvitationCreate,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
) -> InvitationResponse:
    """Invite someone into the caller's organisation (org_admin only).

    No email is sent yet — the response carries the ``invite_link`` for the admin
    to share manually until transactional email is wired up.
    """
    invitation = await invitation_service.create_invitation(
        db,
        organisation_id=current_user.organisation_id,
        invited_by_id=current_user.id,
        email=body.email,
        role=body.role,
    )
    await db.commit()
    await db.refresh(invitation)
    return InvitationResponse.from_invitation(invitation)


@router.get("/", response_model=list[InvitationResponse])
async def list_invitations(
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(default=None),
) -> list[InvitationResponse]:
    """List the organisation's invitations, optionally filtered by status."""
    invitations = await invitation_service.list_invitations(
        db, organisation_id=current_user.organisation_id, status=status
    )
    return [InvitationResponse.from_invitation(inv) for inv in invitations]


@router.delete("/{invitation_id}")
async def revoke_invitation(
    invitation_id: UUID,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Revoke a pending invitation (org_admin only)."""
    await invitation_service.revoke_invitation(
        db,
        invitation_id=invitation_id,
        organisation_id=current_user.organisation_id,
        revoked_by_id=current_user.id,
    )
    await db.commit()
    return {"message": "Invitation revoked"}


@router.post("/accept", response_model=InvitationAcceptResponse)
async def accept_invitation(
    body: InvitationAcceptRequest,
    db: AsyncSession = Depends(get_db),
) -> InvitationAcceptResponse:
    """Accept an invitation (PUBLIC): create the account and issue tokens."""
    user, organisation = await invitation_service.accept_invitation(
        db,
        token=body.token,
        full_name=body.full_name,
        password=body.password,
    )
    await db.commit()
    await db.refresh(user)

    claims = {
        "sub": str(user.id),
        "org": str(user.organisation_id),
        "role": user.role,
    }
    return InvitationAcceptResponse(
        access_token=create_access_token(claims),
        refresh_token=create_refresh_token({"sub": str(user.id)}),
        user=UserResponse.model_validate(user),
        organisation=OrganisationResponse.model_validate(organisation),
    )


@router.get("/validate/{token}", response_model=InvitationValidateResponse)
async def validate_invitation(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Validate an invitation token (PUBLIC) so the accept form can pre-fill.

    404 if unknown, 409 if already used/revoked, 410 (with ``expired_at``) if
    expired.
    """
    invitation = await invitation_service.get_invitation_by_token(db, token)
    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )
    if invitation.status in ("accepted", "revoked"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This invitation has already been used",
        )
    if invitation.status == "expired" or invitation.expires_at <= datetime.now(UTC):
        # Custom body shape so the frontend can surface the exact expiry time.
        return JSONResponse(
            status_code=status.HTTP_410_GONE,
            content={
                "detail": "Invitation has expired",
                "expired_at": invitation.expires_at.isoformat(),
            },
        )

    return InvitationValidateResponse(
        email=invitation.email,
        role=invitation.role,
        organisation_name=invitation.organisation.name,
        expires_at=invitation.expires_at,
    )
