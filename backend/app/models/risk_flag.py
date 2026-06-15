"""RiskFlag model — an individual risk identified during analysis."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.analysis_job import AnalysisJob
    from app.models.clause import Clause


class RiskFlag(UUIDMixin, TimestampMixin, Base):
    """A flagged risk.

    ``category`` is one of: ``indemnity``, ``liability_cap``, ``ip_assignment``,
    ``auto_renewal``, ``jurisdiction``, ``termination``, ``payment_terms``,
    ``confidentiality``, ``data_protection``, ``regulatory``.

    ``severity`` is one of: ``critical``, ``high``, ``medium``, ``low``.

    ``status`` is one of: ``open``, ``accepted``, ``rejected``, ``resolved``.
    """

    __tablename__ = "risk_flags"

    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    clause_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clauses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    cited_regulation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)

    analysis_job: Mapped[AnalysisJob] = relationship(back_populates="risk_flags")
    clause: Mapped[Clause | None] = relationship(back_populates="risk_flags")
