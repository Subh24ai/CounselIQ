"""User request/response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# Allowed user roles across the platform.
ALLOWED_ROLES: frozenset[str] = frozenset(
    {"org_admin", "legal_counsel", "compliance_officer", "viewer"}
)


def _validate_role(value: str) -> str:
    if value not in ALLOWED_ROLES:
        allowed = ", ".join(sorted(ALLOWED_ROLES))
        raise ValueError(f"role must be one of: {allowed}")
    return value


class UserBase(BaseModel):
    """Shared user fields."""

    email: EmailStr
    full_name: str
    role: str

    @field_validator("role")
    @classmethod
    def check_role(cls, value: str) -> str:
        return _validate_role(value)


class UserCreate(UserBase):
    """Payload for creating a user."""

    password: str = Field(min_length=8)
    organisation_id: UUID


class UserCreateInOrg(UserBase):
    """Payload for an admin creating a user; org is taken from the token."""

    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    """Partial update payload for a user."""

    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def check_role(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_role(value)


class UserResponse(UserBase):
    """User representation returned by the API (never includes the password)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organisation_id: UUID
    is_active: bool
    last_login: datetime | None
    created_at: datetime
