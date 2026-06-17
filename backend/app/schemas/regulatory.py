"""Regulatory monitor request/response schemas."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Recognised regulator sources (free-text ``other`` permitted for anything else).
REGULATORY_SOURCES = {"SEBI", "IRDAI", "MCA", "RBI", "NABH", "other"}


class RegulatoryUpdateCreate(BaseModel):
    """Body to manually log a regulatory update / circular."""

    source: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=512)
    summary: str = Field(min_length=1)
    full_text: str | None = None
    url: str | None = Field(default=None, max_length=1024)
    published_date: date


class RegulatoryUpdateResponse(BaseModel):
    """A regulatory update as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: str | None
    title: str
    summary: str | None
    full_text: str | None = None
    url: str | None
    published_date: date | None
    is_processed: bool
    created_at: datetime


class RegulatoryUpdateListResponse(BaseModel):
    """Paginated list of regulatory updates."""

    items: list[RegulatoryUpdateResponse]
    total: int
    page: int
    page_size: int


class AffectedDocumentMatch(BaseModel):
    """A document whose clauses semantically match a regulatory update."""

    document_id: UUID
    document_name: str
    similarity_score: float  # 0.0-1.0 cosine similarity (best matching clause)
    matched_clause_id: UUID | None
    matched_clause_excerpt: str | None  # first 200 chars of the clause


class RegulatoryImpactResponse(BaseModel):
    """A regulatory update plus the caller-org documents it likely affects."""

    regulatory_update: RegulatoryUpdateResponse
    affected_documents: list[AffectedDocumentMatch]
