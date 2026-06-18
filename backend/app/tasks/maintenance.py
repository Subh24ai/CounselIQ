"""Maintenance tasks: recover orphaned analysis jobs and documents.

A worker killed/restarted mid-run dies before any in-process handler can flip
its job to ``failed`` (the SIGKILL'd process never reaches its ``finally``), so
the row is left stuck in ``running`` forever — and its document stuck in
``analysing``. The scheduled task is the safety net: it first fails any job that
has been ``running`` far longer than a real analysis takes, then heals any
document left orphaned in ``analysing`` with no active job.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.session import SyncSessionLocal
from app.models import AnalysisJob, Document
from app.services.audit import write_audit_log_sync
from app.services.events import publish_job_update
from app.tasks.celery_app import celery_app

logger = logging.getLogger("counseliq.tasks.maintenance")

# Job statuses that mean an analysis is genuinely in progress for a document.
IN_PROGRESS_JOB_STATUSES = ("pending", "running")

# A job legitimately running this long is almost certainly orphaned: the longest
# real run observed was ~90s (plus ~25s of Groq rate-limit retries). The task's
# own soft time limit is 300s, so 10 minutes is well clear of any live run.
STALE_RUNNING_AFTER = timedelta(minutes=10)

STALE_ERROR_MESSAGE = (
    "Job exceeded maximum runtime and was marked failed by automated recovery "
    "(likely worker crash or restart)."
)


@celery_app.task(
    name="app.tasks.maintenance.detect_stale_jobs_task",
    queue="default",
)
def detect_stale_jobs_task() -> dict[str, int]:
    """Mark long-orphaned ``running`` jobs as ``failed``. Returns the count.

    For each recovered job: set ``failed`` + a clear ``error_message`` +
    ``completed_at``, un-stick its document so it can be re-analysed, and write
    an audit-log entry. Connected clients are notified best-effort after commit.
    """
    cutoff = datetime.now(UTC) - STALE_RUNNING_AFTER
    session = SyncSessionLocal()
    notifications: list[tuple[str, str]] = []
    try:
        stale_jobs = (
            session.execute(
                select(AnalysisJob).where(
                    AnalysisJob.status == "running",
                    AnalysisJob.started_at < cutoff,
                )
            )
            .scalars()
            .all()
        )

        for job in stale_jobs:
            job.status = "failed"
            job.error_message = STALE_ERROR_MESSAGE
            job.completed_at = datetime.now(UTC)

            # Restore the document to a re-analysable state — a worker crash is
            # not a document problem; the user should be able to retry.
            document = session.execute(
                select(Document).where(Document.id == job.document_id)
            ).scalar_one_or_none()
            if document is not None and document.status == "analysing":
                document.status = "extracted"

            write_audit_log_sync(
                session,
                organisation_id=job.organisation_id,
                action="analysis.stale_recovered",
                user_id=job.initiated_by,
                resource_type="analysis_job",
                resource_id=job.id,
                payload={
                    "reason": STALE_ERROR_MESSAGE,
                    "started_at": (
                        job.started_at.isoformat() if job.started_at else None
                    ),
                },
            )
            notifications.append((str(job.organisation_id), str(job.id)))
            logger.warning(
                "Recovered stale analysis job",
                extra={
                    "organisation_id": str(job.organisation_id),
                    "job_id": str(job.id),
                },
            )

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    # Best-effort real-time notify (after the DB state is durable).
    for organisation_id, job_id in notifications:
        publish_job_update(
            organisation_id, job_id, "failed", {"error": STALE_ERROR_MESSAGE}
        )

    recovered = len(notifications)
    logger.info(
        "Stale job recovery complete: %d recovered",
        recovered,
        extra={"recovered": recovered},
    )

    # Order matters: recover jobs first (which un-sticks their own documents),
    # then heal any documents still orphaned in 'analysing' — e.g. those whose
    # job was failed/recovered without resetting the document.
    healed = detect_orphaned_documents()["healed"]

    return {"recovered": recovered, "documents_healed": healed}


def detect_orphaned_documents() -> dict[str, int]:
    """Heal documents stuck in ``analysing`` with no active job. Returns the count.

    A document is orphaned when its analysis was interrupted (a crashed worker,
    or a job failed/recovered without resetting the document) leaving it
    ``analysing`` while no ``pending``/``running`` job exists for it. Such a
    document still has its extracted text, so it is reset to ``extracted`` so it
    can be re-analysed. Each heal is recorded in the audit log.
    """
    session = SyncSessionLocal()
    healed = 0
    try:
        has_active_job = (
            select(AnalysisJob.id)
            .where(
                AnalysisJob.document_id == Document.id,
                AnalysisJob.status.in_(IN_PROGRESS_JOB_STATUSES),
            )
            .exists()
        )
        orphaned_documents = (
            session.execute(
                select(Document).where(
                    Document.status == "analysing",
                    ~has_active_job,
                )
            )
            .scalars()
            .all()
        )

        for document in orphaned_documents:
            document.status = "extracted"
            write_audit_log_sync(
                session,
                organisation_id=document.organisation_id,
                action="document.status_healed",
                user_id=document.uploaded_by,
                resource_type="document",
                resource_id=document.id,
                payload={
                    "from": "analysing",
                    "to": "extracted",
                    "reason": "no active analysis job (orphaned)",
                },
            )
            healed += 1
            logger.warning(
                "Healed orphaned document",
                extra={
                    "organisation_id": str(document.organisation_id),
                    "document_id": str(document.id),
                },
            )

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    logger.info(
        "Orphaned document recovery complete: %d healed",
        healed,
        extra={"healed": healed},
    )
    return {"healed": healed}
