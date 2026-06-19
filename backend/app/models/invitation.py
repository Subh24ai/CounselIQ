"""Invitation model — an org_admin inviting someone into their organisation."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.organisation import Organisation
    from app.models.user import User


class Invitation(UUIDMixin, TimestampMixin, Base):
    """A pending/accepted invitation to join an organisation.

    ``status`` is one of: ``pending``, ``accepted``, ``expired``, ``revoked``.
    The ``token`` is a cryptographically secure random string used in the public
    invite link; the link itself is never stored (it is constructed on read from
    ``FRONTEND_URL`` + token).
    """

    __tablename__ = "invitations"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invited_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Two FKs point at users, so the foreign_keys must be disambiguated. These
    # are one-directional (no back_populates) to keep the User model untouched.
    organisation: Mapped[Organisation] = relationship()
    inviter: Mapped[User] = relationship(foreign_keys=[invited_by])
    accepter: Mapped[User | None] = relationship(foreign_keys=[accepted_by])

    __table_args__ = (
        # Composite index backs the per-org duplicate-pending-invite check.
        Index("ix_invitations_org_email", "organisation_id", "email"),
    )
