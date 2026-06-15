"""Organisation request/response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OrganisationCreate(BaseModel):
    """Payload for creating an organisation."""

    name: str = Field(min_length=1, max_length=255)
    domain: str | None = None
    plan: str = "starter"


class OrganisationResponse(BaseModel):
    """Organisation representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    domain: str | None
    plan: str
    is_active: bool
    created_at: datetime
