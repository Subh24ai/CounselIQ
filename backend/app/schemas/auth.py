"""Authentication request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Credentials supplied to ``POST /auth/login``."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Access + refresh token pair returned on auth success."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Body for ``POST /auth/refresh``."""

    refresh_token: str


class RegisterRequest(BaseModel):
    """Combined organisation + first-admin payload for ``POST /auth/register``."""

    # Organisation fields
    organisation_name: str = Field(min_length=1, max_length=255)
    domain: str | None = None
    plan: str = "starter"

    # First user (becomes org_admin)
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)
