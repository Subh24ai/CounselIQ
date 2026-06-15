"""User model — an authenticated member of an organisation."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.analysis_job import AnalysisJob
    from app.models.document import Document
    from app.models.organisation import Organisation


class User(UUIDMixin, TimestampMixin, Base):
    """A platform user. Roles are one of:

    ``org_admin``, ``legal_counsel``, ``compliance_officer``, ``viewer``.
    """

    __tablename__ = "users"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    organisation: Mapped[Organisation] = relationship(back_populates="users")
    documents: Mapped[list[Document]] = relationship(back_populates="uploader")
    initiated_jobs: Mapped[list[AnalysisJob]] = relationship(
        back_populates="initiator"
    )
