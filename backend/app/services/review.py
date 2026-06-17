"""Human-review service: the sign-off gate over an analysis job.

The critical business rule — a job cannot be approved while any *critical* risk
flag is still ``open`` — is enforced here in the service layer, not the router,
so it holds regardless of which entry point calls ``submit_review``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisJob, Review, RiskFlag
from app.schemas.review import ReviewSubmitRequest, ReviewSummaryResponse
from app.services.audit import write_audit_log
from app.services.events import publish_job_event


async def _get_org_job(
    db: AsyncSession, analysis_job_id: UUID, organisation_id: UUID
) -> AnalysisJob:
    """Fetch an analysis job scoped to an organisation or raise 404."""
    job = (
        await db.execute(
            select(AnalysisJob).where(
                AnalysisJob.id == analysis_job_id,
                AnalysisJob.organisation_id == organisation_id,
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Analysis job not found"
        )
    return job


async def start_review(
    db: AsyncSession,
    analysis_job_id: UUID,
    reviewer_id: UUID,
    organisation_id: UUID,
) -> Review:
    """Open a review on a job that is awaiting human review."""
    job = await _get_org_job(db, analysis_job_id, organisation_id)
    if job.status != "awaiting_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Job is not awaiting review (status '{job.status}'); "
                "a review can only be started once analysis is complete."
            ),
        )

    existing = (
        await db.execute(select(Review).where(Review.analysis_job_id == analysis_job_id))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Review already started"
        )

    review = Review(
        analysis_job_id=analysis_job_id,
        reviewed_by=reviewer_id,
        status="in_progress",
    )
    db.add(review)
    await db.flush()

    await write_audit_log(
        db,
        organisation_id=organisation_id,
        action="review.started",
        user_id=reviewer_id,
        resource_type="analysis_job",
        resource_id=analysis_job_id,
        payload={"review_id": str(review.id)},
    )
    await db.commit()
    await db.refresh(review)
    return review


async def update_risk_flag(
    db: AsyncSession,
    flag_id: UUID,
    new_status: str,
    notes: str | None,
    reviewer_id: UUID,
    organisation_id: UUID,
) -> RiskFlag:
    """Record a reviewer's decision on a single risk flag.

    The flag row stores only the new status; ``notes`` are preserved in the
    tamper-evident audit trail.
    """
    flag = (
        await db.execute(
            select(RiskFlag)
            .join(AnalysisJob, RiskFlag.analysis_job_id == AnalysisJob.id)
            .where(
                RiskFlag.id == flag_id,
                AnalysisJob.organisation_id == organisation_id,
            )
        )
    ).scalar_one_or_none()
    if flag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Risk flag not found"
        )

    flag.status = new_status
    # Persist the note on the row for display; the audit log below remains the
    # tamper-evident trail of the change.
    flag.notes = notes

    await write_audit_log(
        db,
        organisation_id=organisation_id,
        action="review.flag_updated",
        user_id=reviewer_id,
        resource_type="risk_flag",
        resource_id=flag_id,
        payload={"status": new_status, "notes": notes},
    )
    await db.commit()
    await db.refresh(flag)

    # Notify other reviewers viewing this job in real time (best-effort).
    publish_job_event(
        str(organisation_id),
        {
            "type": "review_flag_updated",
            "job_id": str(flag.analysis_job_id),
            "flag_id": str(flag_id),
            "status": new_status,
        },
    )
    return flag


async def submit_review(
    db: AsyncSession,
    review_id: UUID,
    submit: ReviewSubmitRequest,
    reviewer_id: UUID,
    organisation_id: UUID,
) -> Review:
    """Finalise a review, gating approval on all critical flags being resolved."""
    review = (
        await db.execute(
            select(Review)
            .join(AnalysisJob, Review.analysis_job_id == AnalysisJob.id)
            .where(
                Review.id == review_id,
                AnalysisJob.organisation_id == organisation_id,
            )
        )
    ).scalar_one_or_none()
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Review not found"
        )

    job = await _get_org_job(db, review.analysis_job_id, organisation_id)

    if submit.status == "approved":
        critical_open = (
            await db.scalar(
                select(func.count())
                .select_from(RiskFlag)
                .where(
                    RiskFlag.analysis_job_id == review.analysis_job_id,
                    RiskFlag.severity == "critical",
                    RiskFlag.status == "open",
                )
            )
            or 0
        )
        if critical_open:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Cannot approve: {critical_open} critical flags still open. "
                    "Review all critical issues first."
                ),
            )

    review.status = submit.status
    review.notes = submit.notes
    review.reviewed_by = reviewer_id
    review.approved_at = datetime.now(UTC) if submit.status == "approved" else None

    # Approval completes the job; rejection sends it back for further review.
    job.status = "completed" if submit.status == "approved" else "awaiting_review"

    await write_audit_log(
        db,
        organisation_id=organisation_id,
        action=f"review.{submit.status}",
        user_id=reviewer_id,
        resource_type="analysis_job",
        resource_id=review.analysis_job_id,
        payload={"review_id": str(review.id), "notes": submit.notes},
    )
    await db.commit()
    await db.refresh(review)

    # Notify other reviewers viewing this job in real time (best-effort).
    publish_job_event(
        str(organisation_id),
        {
            "type": "review_submitted",
            "job_id": str(review.analysis_job_id),
            "status": submit.status,
        },
    )
    return review


async def get_review_summary(
    db: AsyncSession, analysis_job_id: UUID, organisation_id: UUID
) -> ReviewSummaryResponse:
    """Aggregate a job's risk flags by status for the review dashboard."""
    await _get_org_job(db, analysis_job_id, organisation_id)

    rows = (
        await db.execute(
            select(RiskFlag.status, func.count())
            .where(RiskFlag.analysis_job_id == analysis_job_id)
            .group_by(RiskFlag.status)
        )
    ).all()
    by_status = {row[0]: row[1] for row in rows}

    critical_open = (
        await db.scalar(
            select(func.count())
            .select_from(RiskFlag)
            .where(
                RiskFlag.analysis_job_id == analysis_job_id,
                RiskFlag.severity == "critical",
                RiskFlag.status == "open",
            )
        )
        or 0
    )

    return ReviewSummaryResponse(
        total_flags=sum(by_status.values()),
        accepted=by_status.get("accepted", 0),
        rejected=by_status.get("rejected", 0),
        resolved=by_status.get("resolved", 0),
        open=by_status.get("open", 0),
        critical_open=critical_open,
    )
