"""SQLAlchemy ORM models for CounselIQ.

Importing every model here ensures they are all registered on
``Base.metadata`` so Alembic autogeneration sees the full schema.
"""

from __future__ import annotations

from app.models.analysis_job import AnalysisJob
from app.models.audit_log import AuditLog
from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.clause import Clause
from app.models.document import Document
from app.models.organisation import Organisation
from app.models.regulatory_update import RegulatoryUpdate
from app.models.review import Review
from app.models.risk_flag import RiskFlag
from app.models.user import User

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    "Organisation",
    "User",
    "Document",
    "Clause",
    "AnalysisJob",
    "RiskFlag",
    "Review",
    "AuditLog",
    "RegulatoryUpdate",
]
