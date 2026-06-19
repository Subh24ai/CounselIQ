"""Invitation request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    model_validator,
)

from app.config import settings
from app.schemas.organisation import OrganisationResponse
from app.schemas.user import UserResponse

# Roles an org_admin may assign via an invitation. org_admin is intentionally
# excluded — an admin cannot mint another admin through an invite.
INVITABLE_ROLES = ("legal_counsel", "compliance_officer", "viewer")
InvitableRole = Literal["legal_counsel", "compliance_officer", "viewer"]


class InvitationCreate(BaseModel):
    """Payload for ``POST /invitations/``."""

    email: EmailStr
    role: InvitableRole


class InvitationResponse(BaseModel):
    """An invitation as returned by the API.

    ``invite_link`` is computed from ``FRONTEND_URL`` + the stored token at
    response time; the link itself is never persisted.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organisation_id: UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime
    invite_link: str

    @classmethod
    def from_invitation(cls, invitation: object) -> InvitationResponse:
        """Build a response, constructing the invite link from the stored token."""
        link = f"{settings.FRONTEND_URL}/invite/{invitation.token}"
        return cls(
            id=invitation.id,
            organisation_id=invitation.organisation_id,
            email=invitation.email,
            role=invitation.role,
            status=invitation.status,
            expires_at=invitation.expires_at,
            accepted_at=invitation.accepted_at,
            created_at=invitation.created_at,
            invite_link=link,
        )


class InvitationAcceptRequest(BaseModel):
    """Payload for ``POST /invitations/accept`` (public)."""

    token: str
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8)
    confirm_password: str

    @model_validator(mode="after")
    def _passwords_match(self) -> InvitationAcceptRequest:
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class InvitationAcceptResponse(BaseModel):
    """Auth + identity returned after a successful invitation acceptance."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
    organisation: OrganisationResponse


class InvitationValidateResponse(BaseModel):
    """Public token-validation response used to pre-fill the accept form."""

    email: str
    role: str
    organisation_name: str
    expires_at: datetime
