"""Reviews router: the human sign-off gate over analysis jobs.

All endpoints require authentication and are scoped to the caller's
organisation. Mutating endpoints (start, flag update, submit) are restricted to
``legal_counsel`` and ``org_admin`` roles.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import AnalysisJob, Review, RiskFlag, User
from app.schemas.analysis import RiskFlagResponse
from app.schemas.review import (
    ReviewResponse,
    ReviewStartResponse,
    ReviewSubmitRequest,
    ReviewSummaryResponse,
    RiskFlagUpdateRequest,
)
from app.services import review as review_service

logger = logging.getLogger("counseliq.api.reviews")

router = APIRouter(prefix="/reviews", tags=["reviews"])

# Reviewing is limited to legal counsel and organisation admins.
require_reviewer = require_roles("legal_counsel", "org_admin")


async def _flags_for_job(db: AsyncSession, analysis_job_id: UUID) -> list[RiskFlag]:
    result = await db.execute(
        select(RiskFlag)
        .where(RiskFlag.analysis_job_id == analysis_job_id)
        .order_by(RiskFlag.created_at.asc())
    )
    return list(result.scalars().all())


async def _build_review_response(db: AsyncSession, review: Review) -> ReviewResponse:
    flags = await _flags_for_job(db, review.analysis_job_id)
    return ReviewResponse(
        id=review.id,
        analysis_job_id=review.analysis_job_id,
        reviewed_by=review.reviewed_by,
        status=review.status,
        notes=review.notes,
        approved_at=review.approved_at,
        created_at=review.created_at,
        risk_flags=[RiskFlagResponse.model_validate(flag) for flag in flags],
    )


@router.post(
    "/jobs/{job_id}/start",
    response_model=ReviewStartResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_review(
    job_id: UUID,
    current_user: User = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
) -> ReviewStartResponse:
    """Open a review on a job that is awaiting human review."""
    review = await review_service.start_review(
        db,
        analysis_job_id=job_id,
        reviewer_id=current_user.id,
        organisation_id=current_user.organisation_id,
    )
    return ReviewStartResponse(
        review_id=review.id,
        analysis_job_id=review.analysis_job_id,
        status=review.status,
        created_at=review.created_at,
    )


@router.get("/", response_model=list[ReviewResponse])
async def list_reviews(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> list[ReviewResponse]:
    """List the organisation's reviews, newest first (paginated)."""
    result = await db.execute(
        select(Review)
        .join(AnalysisJob, Review.analysis_job_id == AnalysisJob.id)
        .where(AnalysisJob.organisation_id == current_user.organisation_id)
        .order_by(Review.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    reviews = list(result.scalars().all())
    return [await _build_review_response(db, review) for review in reviews]


@router.get("/jobs/{job_id}", response_model=ReviewResponse)
async def get_review(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewResponse:
    """Retrieve the review for a job, with its risk flags."""
    review = (
        await db.execute(
            select(Review)
            .join(AnalysisJob, Review.analysis_job_id == AnalysisJob.id)
            .where(
                Review.analysis_job_id == job_id,
                AnalysisJob.organisation_id == current_user.organisation_id,
            )
        )
    ).scalar_one_or_none()
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Review not found"
        )
    return await _build_review_response(db, review)


@router.get("/jobs/{job_id}/summary", response_model=ReviewSummaryResponse)
async def get_review_summary(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewSummaryResponse:
    """Aggregate counts of a job's risk flags by review status."""
    return await review_service.get_review_summary(
        db, analysis_job_id=job_id, organisation_id=current_user.organisation_id
    )


@router.patch("/flags/{flag_id}", response_model=RiskFlagResponse)
async def update_flag(
    flag_id: UUID,
    body: RiskFlagUpdateRequest,
    current_user: User = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
) -> RiskFlag:
    """Record a reviewer's decision on a single risk flag."""
    return await review_service.update_risk_flag(
        db,
        flag_id=flag_id,
        new_status=body.status,
        notes=body.notes,
        reviewer_id=current_user.id,
        organisation_id=current_user.organisation_id,
    )


@router.post("/jobs/{job_id}/submit", response_model=ReviewResponse)
async def submit_review(
    job_id: UUID,
    body: ReviewSubmitRequest,
    current_user: User = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
) -> ReviewResponse:
    """Finalise the review for a job (approve or reject)."""
    review = (
        await db.execute(
            select(Review)
            .join(AnalysisJob, Review.analysis_job_id == AnalysisJob.id)
            .where(
                Review.analysis_job_id == job_id,
                AnalysisJob.organisation_id == current_user.organisation_id,
            )
        )
    ).scalar_one_or_none()
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Review not found"
        )

    updated = await review_service.submit_review(
        db,
        review_id=review.id,
        submit=body,
        reviewer_id=current_user.id,
        organisation_id=current_user.organisation_id,
    )
    return await _build_review_response(db, updated)