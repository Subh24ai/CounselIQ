"""Regulatory monitor router.

Anyone in the org can browse regulatory updates and check their impact on the
org's own documents. Logging a new update and marking one reviewed are limited
to ``org_admin`` and ``compliance_officer``.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import RegulatoryUpdate, User
from app.schemas.regulatory import (
    RegulatoryImpactResponse,
    RegulatoryUpdateCreate,
    RegulatoryUpdateListResponse,
    RegulatoryUpdateResponse,
)
from app.services import regulatory as regulatory_service

logger = logging.getLogger("counseliq.api.regulatory")

router = APIRouter(prefix="/regulatory", tags=["regulatory"])

# Logging and triaging updates is limited to admins and compliance officers.
require_compliance_manager = require_roles("org_admin", "compliance_officer")


async def _get_update_or_404(
    db: AsyncSession, update_id: UUID
) -> RegulatoryUpdate:
    update = await db.get(RegulatoryUpdate, update_id)
    if update is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regulatory update not found",
        )
    return update


@router.post(
    "/updates",
    response_model=RegulatoryUpdateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_update(
    body: RegulatoryUpdateCreate,
    current_user: User = Depends(require_compliance_manager),
    db: AsyncSession = Depends(get_db),
) -> RegulatoryUpdate:
    """Manually log a regulatory update (and embed it for impact matching)."""
    return await regulatory_service.create_regulatory_update(db, body)


@router.get("/updates", response_model=RegulatoryUpdateListResponse)
async def list_updates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    source: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> RegulatoryUpdateListResponse:
    """List regulatory updates, newest first, optionally filtered by source."""
    base = select(RegulatoryUpdate)
    if source:
        base = base.where(RegulatoryUpdate.source == source)

    total = await db.scalar(select(func.count()).select_from(base.subquery()))

    result = await db.execute(
        base.order_by(
            RegulatoryUpdate.published_date.desc().nullslast(),
            RegulatoryUpdate.created_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = result.scalars().all()

    return RegulatoryUpdateListResponse(
        items=[RegulatoryUpdateResponse.model_validate(item) for item in items],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/updates/{update_id}", response_model=RegulatoryUpdateResponse)
async def get_update(
    update_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RegulatoryUpdate:
    """Retrieve a single regulatory update."""
    return await _get_update_or_404(db, update_id)


@router.get(
    "/updates/{update_id}/impact", response_model=RegulatoryImpactResponse
)
async def get_impact(
    update_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RegulatoryImpactResponse:
    """Find which of the caller-org's documents this update likely affects."""
    update = await _get_update_or_404(db, update_id)
    affected = await regulatory_service.find_affected_documents(
        db,
        regulatory_update_id=update.id,
        organisation_id=current_user.organisation_id,
    )
    return RegulatoryImpactResponse(
        regulatory_update=RegulatoryUpdateResponse.model_validate(update),
        affected_documents=affected,
    )


@router.post(
    "/updates/{update_id}/mark-processed",
    response_model=RegulatoryUpdateResponse,
)
async def mark_processed(
    update_id: UUID,
    current_user: User = Depends(require_compliance_manager),
    db: AsyncSession = Depends(get_db),
) -> RegulatoryUpdate:
    """Mark a regulatory update as reviewed/handled."""
    return await regulatory_service.mark_processed(db, update_id)
