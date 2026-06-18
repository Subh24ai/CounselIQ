"""Tests for stale-job recovery (worker-crash safety net).

The task opens its own ``SyncSessionLocal``; we monkeypatch that to a
savepoint-bound session on a single rolled-back connection, so seeding, the
task, and assertions all share one transaction and nothing touches the real DB.
Assertions target the specific seeded job (not global counts), since the shared
dev DB may hold unrelated rows.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.session import sync_engine
from app.models import AnalysisJob, Document, Organisation, User
from app.tasks.maintenance import (
    STALE_ERROR_MESSAGE,
    detect_orphaned_documents,
    detect_stale_jobs_task,
)
from app.utils.security import hash_password


@pytest.fixture
def sync_factory(monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker]:
    """A sync session factory on one rolled-back connection, patched into the task."""
    connection = sync_engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
        autoflush=False,
    )
    # The task imports SyncSessionLocal into its own module namespace.
    monkeypatch.setattr("app.tasks.maintenance.SyncSessionLocal", factory)
    try:
        yield factory
    finally:
        transaction.rollback()
        connection.close()


def _seed_job(
    factory: sessionmaker,
    *,
    status: str,
    started_minutes_ago: int | None,
    doc_status: str = "analysing",
) -> uuid.UUID:
    """Seed an org/user/document and one analysis job; return the job id."""
    suffix = uuid.uuid4().hex[:8]
    started_at = (
        datetime.now(UTC) - timedelta(minutes=started_minutes_ago)
        if started_minutes_ago is not None
        else None
    )
    with factory() as session:
        org = Organisation(name=f"Maint {suffix}", domain=f"m-{suffix}.example")
        session.add(org)
        session.flush()
        user = User(
            organisation_id=org.id,
            email=f"u-{suffix}@example.com",
            hashed_password=hash_password("x"),
            role="org_admin",
            is_active=True,
        )
        session.add(user)
        session.flush()
        doc = Document(
            organisation_id=org.id,
            uploaded_by=user.id,
            name="Doc",
            s3_key=f"{org.id}/{suffix}/d.pdf",
            status=doc_status,
            document_type="nda",
        )
        session.add(doc)
        session.flush()
        job = AnalysisJob(
            document_id=doc.id,
            organisation_id=org.id,
            initiated_by=user.id,
            status=status,
            job_type="contract_review",
            agent_trace=[],
            started_at=started_at,
        )
        session.add(job)
        session.flush()
        job_id = job.id
        session.commit()
    return job_id


def test_detect_stale_jobs_marks_old_running_jobs_failed(
    sync_factory: sessionmaker,
) -> None:
    job_id = _seed_job(sync_factory, status="running", started_minutes_ago=15)

    result = detect_stale_jobs_task()
    assert result["recovered"] >= 1  # at least our seeded job

    with sync_factory() as session:
        job = session.get(AnalysisJob, job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.error_message == STALE_ERROR_MESSAGE
        assert job.completed_at is not None
        # The document is restored to a re-analysable state.
        document = session.get(Document, job.document_id)
        assert document is not None
        assert document.status == "extracted"


def test_detect_stale_jobs_ignores_recent_running_jobs(
    sync_factory: sessionmaker,
) -> None:
    job_id = _seed_job(sync_factory, status="running", started_minutes_ago=2)

    detect_stale_jobs_task()

    with sync_factory() as session:
        job = session.get(AnalysisJob, job_id)
        assert job is not None
        assert job.status == "running"  # still in flight, untouched
        assert job.completed_at is None
        assert job.error_message is None


def test_detect_stale_jobs_ignores_completed_jobs(
    sync_factory: sessionmaker,
) -> None:
    # An old, non-running job must never be touched.
    job_id = _seed_job(
        sync_factory,
        status="completed",
        started_minutes_ago=30,
        doc_status="completed",
    )

    detect_stale_jobs_task()

    with sync_factory() as session:
        job = session.get(AnalysisJob, job_id)
        assert job is not None
        assert job.status == "completed"
        assert job.error_message is None


def test_detect_orphaned_documents_resets_status(
    sync_factory: sessionmaker,
) -> None:
    # A document stuck 'analysing' whose only job is 'failed' (no active job) is
    # orphaned and must be healed back to 'extracted'.
    job_id = _seed_job(
        sync_factory,
        status="failed",
        started_minutes_ago=20,
        doc_status="analysing",
    )
    with sync_factory() as session:
        document_id = session.get(AnalysisJob, job_id).document_id
        assert session.get(Document, document_id).status == "analysing"

    result = detect_orphaned_documents()
    assert result["healed"] >= 1  # at least our seeded document

    with sync_factory() as session:
        assert session.get(Document, document_id).status == "extracted"


def test_detect_orphaned_documents_ignores_documents_with_active_job(
    sync_factory: sessionmaker,
) -> None:
    # A document 'analysing' WITH a running job is genuinely in progress —
    # it must not be healed.
    job_id = _seed_job(
        sync_factory,
        status="running",
        started_minutes_ago=1,
        doc_status="analysing",
    )
    with sync_factory() as session:
        document_id = session.get(AnalysisJob, job_id).document_id

    detect_orphaned_documents()

    with sync_factory() as session:
        assert session.get(Document, document_id).status == "analysing"
