"""Analysis router: start jobs, list/inspect jobs, and fetch the full report.

Every endpoint requires authentication and is scoped to the caller's
organisation. Starting a job enqueues the LangGraph pipeline on the ``analysis``
Celery queue.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import AnalysisJob, Clause, Document, RiskFlag, User
from app.schemas.analysis import (
    JOB_TYPES,
    AnalysisJobCreate,
    AnalysisJobListResponse,
    AnalysisJobResponse,
    AnalysisReportResponse,
    RiskFlagResponse,
)
from app.services.audit import write_audit_log
from app.tasks.analysis import run_analysis_task

logger = logging.getLogger("counseliq.api.analysis")

router = APIRouter(prefix="/analysis", tags=["analysis"])

# A document must be extracted (queued) or previously completed to be analysed.
ANALYSABLE_DOCUMENT_STATUSES = {"queued", "completed"}

# Statuses for which a full report is meaningful.
REPORTABLE_JOB_STATUSES = {"awaiting_review", "completed"}


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _trace_dict(job: AnalysisJob) -> dict[str, Any]:
    """Return ``agent_trace`` as a dict regardless of how it was stored.

    Completed jobs store a structured dict; freshly created jobs default to an
    empty list. This normalises both to a dict for safe key access.
    """
    trace = job.agent_trace
    if isinstance(trace, dict):
        return trace
    return {}


def _trace_steps(job: AnalysisJob) -> list[dict]:
    """Return the step log from a job's trace (handles list or dict storage)."""
    trace = job.agent_trace
    if isinstance(trace, dict):
        steps = trace.get("steps")
        return steps if isinstance(steps, list) else []
    if isinstance(trace, list):
        return trace
    return []


def _job_to_response(job: AnalysisJob) -> AnalysisJobResponse:
    """Build the API response for a job, exposing only the step log as the trace."""
    return AnalysisJobResponse(
        id=job.id,
        document_id=job.document_id,
        status=job.status,
        job_type=job.job_type,
        overall_risk_score=job.overall_risk_score,
        agent_trace=_trace_steps(job),
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
    )


async def _get_org_job(
    db: AsyncSession, job_id: UUID, organisation_id: UUID
) -> AnalysisJob:
    """Fetch an analysis job within an organisation or raise 404."""
    result = await db.execute(
        select(AnalysisJob).where(
            AnalysisJob.id == job_id,
            AnalysisJob.organisation_id == organisation_id,
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Analysis job not found"
        )
    return job


@router.post("/jobs", response_model=AnalysisJobResponse, status_code=status.HTTP_201_CREATED)
async def create_analysis_job(
    payload: AnalysisJobCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalysisJobResponse:
    """Create an analysis job for a document and enqueue the pipeline."""
    if payload.job_type not in JOB_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported job_type. Allowed: {sorted(JOB_TYPES)}",
        )

    document = (
        await db.execute(
            select(Document).where(
                Document.id == payload.document_id,
                Document.organisation_id == current_user.organisation_id,
            )
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    if document.status not in ANALYSABLE_DOCUMENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Document is not ready for analysis (status '{document.status}'). "
                "It must be extracted before analysis can run."
            ),
        )

    job = AnalysisJob(
        document_id=document.id,
        organisation_id=current_user.organisation_id,
        initiated_by=current_user.id,
        status="pending",
        job_type=payload.job_type,
        agent_trace=[],
    )
    db.add(job)
    await db.flush()

    await write_audit_log(
        db,
        organisation_id=current_user.organisation_id,
        action="analysis.created",
        user_id=current_user.id,
        resource_type="analysis_job",
        resource_id=job.id,
        payload={"document_id": str(document.id), "job_type": payload.job_type},
        ip_address=_client_ip(request),
    )

    await db.commit()
    await db.refresh(job)

    # Enqueue only after the job is durably committed so the worker can find it.
    run_analysis_task.delay(str(job.id))

    return _job_to_response(job)


@router.get("/jobs", response_model=AnalysisJobListResponse)
async def list_analysis_jobs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> AnalysisJobListResponse:
    """List the organisation's analysis jobs, newest first (paginated)."""
    base = select(AnalysisJob).where(
        AnalysisJob.organisation_id == current_user.organisation_id
    )

    total = await db.scalar(select(func.count()).select_from(base.subquery()))

    result = await db.execute(
        base.order_by(AnalysisJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    jobs = result.scalars().all()

    return AnalysisJobListResponse(
        items=[_job_to_response(job) for job in jobs],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/jobs/{job_id}", response_model=AnalysisJobResponse)
async def get_analysis_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalysisJobResponse:
    """Retrieve a single analysis job with its agent trace."""
    job = await _get_org_job(db, job_id, current_user.organisation_id)
    return _job_to_response(job)


@router.get("/jobs/{job_id}/report", response_model=AnalysisReportResponse)
async def get_analysis_report(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalysisReportResponse:
    """Return the full review report: job, risk flags, alternatives, summary."""
    job = await _get_org_job(db, job_id, current_user.organisation_id)
    if job.status not in REPORTABLE_JOB_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Report not available while job status is '{job.status}'. "
                f"Available once status is one of {sorted(REPORTABLE_JOB_STATUSES)}."
            ),
        )

    flags_result = await db.execute(
        select(RiskFlag)
        .where(RiskFlag.analysis_job_id == job.id)
        .order_by(RiskFlag.created_at.asc())
    )
    risk_flags = flags_result.scalars().all()

    clauses_count = await db.scalar(
        select(func.count())
        .select_from(Clause)
        .where(Clause.document_id == job.document_id)
    )

    trace = _trace_dict(job)
    drafted = trace.get("drafted_alternatives")
    summary = trace.get("summary_report")

    return AnalysisReportResponse(
        job=_job_to_response(job),
        risk_flags=[RiskFlagResponse.model_validate(flag) for flag in risk_flags],
        drafted_alternatives=drafted if isinstance(drafted, list) else [],
        summary_report=summary if isinstance(summary, str) else None,
        clauses_count=clauses_count or 0,
    )
