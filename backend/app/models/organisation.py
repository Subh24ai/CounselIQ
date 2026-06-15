"""Organisation model — the top-level tenant in CounselIQ."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.analysis_job import AnalysisJob
    from app.models.document import Document
    from app.models.user import User


class Organisation(UUIDMixin, TimestampMixin, Base):
    """A customer organisation (tenant)."""

    __tablename__ = "organisations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    plan: Mapped[str] = mapped_column(String(50), default="starter", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    users: Mapped[list[User]] = relationship(
        back_populates="organisation",
        cascade="all, delete-orphan",
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="organisation",
        cascade="all, delete-orphan",
    )
    analysis_jobs: Mapped[list[AnalysisJob]] = relationship(
        back_populates="organisation",
        cascade="all, delete-orphan",
    )
