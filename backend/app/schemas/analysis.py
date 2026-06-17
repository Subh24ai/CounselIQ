"""Analysis-job request/response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Allowed analysis job types (mirrors AnalysisJob.job_type documentation).
JOB_TYPES = {"contract_review", "due_diligence", "reg_compliance", "risk_assessment"}


class AnalysisJobCreate(BaseModel):
    """Request body to start an analysis job."""

    document_id: UUID
    job_type: str = Field(min_length=1, max_length=50)


class AnalysisJobResponse(BaseModel):
    """An analysis job as returned by the API.

    ``agent_trace`` is the append-only step log of the pipeline run (empty until
    the job has executed).
    """

    id: UUID
    document_id: UUID
    status: str
    job_type: str
    overall_risk_score: float | None
    agent_trace: list[dict]
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class AnalysisJobListResponse(BaseModel):
    """Paginated list of analysis jobs."""

    items: list[AnalysisJobResponse]
    total: int
    page: int
    page_size: int


class RiskFlagResponse(BaseModel):
    """A single persisted risk flag."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category: str | None
    severity: str | None
    title: str
    description: str | None
    suggested_action: str | None
    agent_reasoning: str | None
    cited_regulation: str | None
    confidence_score: float | None
    status: str
    notes: str | None


class AnalysisReportResponse(BaseModel):
    """The full review report for a completed/awaiting-review job."""

    job: AnalysisJobResponse
    risk_flags: list[RiskFlagResponse]
    drafted_alternatives: list[dict]
    research_findings: list[dict]
    summary_report: str | None
    clauses_count: int
