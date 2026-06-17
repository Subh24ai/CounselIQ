"""Document model — an uploaded legal document and its processing state."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.analysis_job import AnalysisJob
    from app.models.clause import Clause
    from app.models.organisation import Organisation
    from app.models.user import User


class Document(UUIDMixin, TimestampMixin, Base):
    """A document uploaded for analysis.

    ``status`` is one of: ``uploaded``, ``queued``, ``extracting``,
    ``analysing``, ``completed``, ``failed``, ``deleted``. ``deleted`` is a
    soft-delete sentinel and must never be treated as a failure state.

    ``document_type`` is one of: ``vendor_contract``, ``employment``, ``nda``,
    ``msa``, ``policy``, ``regulatory``, ``other``.
    """

    __tablename__ = "documents"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    s3_key: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    s3_bucket: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="uploaded", nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), default="other", nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    textract_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    organisation: Mapped[Organisation] = relationship(back_populates="documents")
    uploader: Mapped[User] = relationship(back_populates="documents")
    analysis_jobs: Mapped[list[AnalysisJob]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    clauses: Mapped[list[Clause]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
