"""RegulatoryUpdate model — ingested regulatory bulletins for RAG retrieval."""

from __future__ import annotations

from datetime import date

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class RegulatoryUpdate(UUIDMixin, TimestampMixin, Base):
    """A regulatory update / circular.

    ``source`` is one of: ``SEBI``, ``IRDAI``, ``MCA``, ``RBI``, ``NABH``,
    ``other``.
    """

    __tablename__ = "regulatory_updates"

    source: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    published_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
