"""Human-review request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.analysis import RiskFlagResponse


class RiskFlagUpdateRequest(BaseModel):
    """Reviewer decision on a single risk flag.

    ``notes`` are recorded in the audit trail (the RiskFlag row carries only its
    status).
    """

    status: Literal["accepted", "rejected", "resolved"]
    notes: str | None = None


class ReviewStartResponse(BaseModel):
    """Returned when a review is opened on an analysis job."""

    review_id: UUID
    analysis_job_id: UUID
    status: str
    created_at: datetime


class ReviewSubmitRequest(BaseModel):
    """Final reviewer sign-off on a job."""

    status: Literal["approved", "rejected"]
    notes: str | None = None


class ReviewResponse(BaseModel):
    """A review with the analysis job's risk flags attached."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_job_id: UUID
    reviewed_by: UUID | None
    status: str
    notes: str | None
    approved_at: datetime | None
    created_at: datetime
    risk_flags: list[RiskFlagResponse]


class ReviewSummaryResponse(BaseModel):
    """Aggregate counts of a job's risk flags by review status."""

    total_flags: int
    accepted: int
    rejected: int
    resolved: int
    open: int
    critical_open: int
