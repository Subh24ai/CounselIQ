"""AnalysisJob model — a single agentic analysis run over a document."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.organisation import Organisation
    from app.models.review import Review
    from app.models.risk_flag import RiskFlag
    from app.models.user import User


class AnalysisJob(UUIDMixin, TimestampMixin, Base):
    """An analysis pipeline execution.

    ``status`` is one of: ``pending``, ``running``, ``awaiting_review``,
    ``completed``, ``failed``.

    ``job_type`` is one of: ``contract_review``, ``due_diligence``,
    ``reg_compliance``, ``risk_assessment``.
    """

    __tablename__ = "analysis_jobs"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    overall_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    agent_trace: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    document: Mapped[Document] = relationship(back_populates="analysis_jobs")
    organisation: Mapped[Organisation] = relationship(back_populates="analysis_jobs")
    initiator: Mapped[User | None] = relationship(back_populates="initiated_jobs")
    risk_flags: Mapped[list[RiskFlag]] = relationship(
        back_populates="analysis_job",
        cascade="all, delete-orphan",
    )
    review: Mapped[Review | None] = relationship(
        back_populates="analysis_job",
        uselist=False,
        cascade="all, delete-orphan",
    )
