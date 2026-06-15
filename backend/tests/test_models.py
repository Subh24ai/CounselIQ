"""Tests for the SQLAlchemy ORM models against the real Postgres database.

Each test runs inside a transaction that is rolled back on teardown (via the
``db_session`` fixture), so the database is never mutated and tests stay
isolated from one another.
"""

from __future__ import annotations

import uuid

import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Clause, Document, Organisation, User


@pytest.mark.asyncio
async def test_create_organisation(db_session: AsyncSession) -> None:
    org = Organisation(name="Acme Legal", domain="acme.example")
    db_session.add(org)
    await db_session.flush()

    fetched = await db_session.get(Organisation, org.id)
    assert fetched is not None
    assert fetched.name == "Acme Legal"
    assert fetched.plan == "starter"  # default
    assert fetched.is_active is True
    assert fetched.settings == {}


@pytest.mark.asyncio
async def test_create_user(db_session: AsyncSession) -> None:
    org = Organisation(name="Beta Corp")
    db_session.add(org)
    await db_session.flush()

    user = User(
        organisation_id=org.id,
        email="counsel@beta.example",
        hashed_password="$2b$12$hashedpasswordvalue",
        full_name="Jane Counsel",
        role="legal_counsel",
    )
    db_session.add(user)
    await db_session.flush()

    result = await db_session.execute(
        select(User).where(User.email == "counsel@beta.example")
    )
    fetched = result.scalar_one()
    assert fetched.organisation_id == org.id  # FK wired correctly
    assert fetched.role == "legal_counsel"
    assert fetched.hashed_password == "$2b$12$hashedpasswordvalue"
    assert fetched.is_active is True


@pytest.mark.asyncio
async def test_create_document(db_session: AsyncSession) -> None:
    org = Organisation(name="Gamma Ltd")
    db_session.add(org)
    await db_session.flush()

    user = User(
        organisation_id=org.id,
        email="uploader@gamma.example",
        hashed_password="hashed",
        role="org_admin",
    )
    db_session.add(user)
    await db_session.flush()

    s3_key = f"docs/{uuid.uuid4()}.pdf"
    document = Document(
        organisation_id=org.id,
        uploaded_by=user.id,
        name="Vendor MSA 2026",
        original_filename="msa.pdf",
        s3_key=s3_key,
        s3_bucket="counseliq-documents",
        file_size_bytes=204800,
        mime_type="application/pdf",
        document_type="msa",
    )
    db_session.add(document)
    await db_session.flush()

    fetched = await db_session.get(Document, document.id)
    assert fetched is not None
    assert fetched.s3_key == s3_key
    assert fetched.status == "uploaded"  # default
    assert fetched.document_type == "msa"
    assert fetched.organisation_id == org.id
    assert fetched.uploaded_by == user.id


@pytest.mark.asyncio
async def test_audit_log_no_updated_at(db_session: AsyncSession) -> None:
    org = Organisation(name="Delta Inc")
    db_session.add(org)
    await db_session.flush()

    entry = AuditLog(
        organisation_id=org.id,
        action="document.upload",
        resource_type="document",
        resource_id=uuid.uuid4(),
        payload={"filename": "msa.pdf"},
        ip_address="203.0.113.7",
        chained_hash="a" * 64,
    )
    db_session.add(entry)
    await db_session.flush()

    fetched = await db_session.get(AuditLog, entry.id)
    assert fetched is not None
    # Audit log is append-only: created_at present, updated_at intentionally absent.
    assert hasattr(fetched, "created_at")
    assert fetched.created_at is not None
    assert not hasattr(fetched, "updated_at")
    assert "updated_at" not in AuditLog.__table__.columns
    assert fetched.chained_hash == "a" * 64


def test_clause_embedding_column() -> None:
    """The clause embedding column must be a pgvector Vector(1536) type."""
    embedding_type = Clause.__table__.c.embedding.type
    assert isinstance(embedding_type, Vector)
    assert embedding_type.dim == 1536
