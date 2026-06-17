"""Celery task that runs the LangGraph analysis pipeline over a document.

Runs on the ``analysis`` queue. Celery workers are synchronous, so this uses a
sync SQLAlchemy session and bridges to the async LangGraph ``ainvoke`` via
``asyncio.run``. The full agent trace, summary report, and drafted alternatives
are persisted on ``AnalysisJob.agent_trace`` (a JSONB document); risk flags and
clauses are written to their own tables.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.orchestrator import build_initial_state, counseliq_graph
from app.db.session import SyncSessionLocal
from app.models import AnalysisJob, Clause, Document, RiskFlag
from app.services.audit import write_audit_log_sync
from app.services.events import publish_agent_step, publish_job_update
from app.tasks.celery_app import celery_app

logger = logging.getLogger("counseliq.tasks.analysis")

# A document must have been through extraction (``extracted``) or a prior full
# run (``completed``) before it can be analysed.
ANALYSABLE_DOCUMENT_STATUSES = {"extracted", "completed"}


def _now() -> datetime:
    return datetime.now(UTC)


@celery_app.task(
    name="app.tasks.analysis.run_analysis_task",
    bind=True,
    queue="analysis",
)
def run_analysis_task(self, analysis_job_id: str) -> dict[str, str]:
    """Execute the analysis pipeline for one :class:`AnalysisJob`.

    On success the job moves to ``awaiting_review`` with its risk score, trace,
    clauses, and risk flags persisted, and the document moves to ``completed``.
    On any failure the job moves to ``failed`` with an error message. The
    function always commits and closes its session.
    """
    session = SyncSessionLocal()
    try:
        job = session.execute(
            select(AnalysisJob).where(AnalysisJob.id == analysis_job_id)
        ).scalar_one_or_none()

        if job is None:
            logger.error("AnalysisJob %s not found", analysis_job_id)
            return {"analysis_job_id": analysis_job_id, "status": "not_found"}

        try:
            return _execute(session, job)
        except Exception as exc:  # noqa: BLE001 - persist failure, never lose the job
            logger.exception("Analysis failed for job %s: %s", analysis_job_id, exc)
            session.rollback()
            _mark_failed(session, job, str(exc))
            session.commit()
            publish_job_update(
                str(job.organisation_id),
                str(job.id),
                "failed",
                {"error": str(exc)},
            )
            return {"analysis_job_id": analysis_job_id, "status": "failed"}
    finally:
        session.close()


def _execute(session: Session, job: AnalysisJob) -> dict[str, str]:
    """Run the graph and persist results for a found, fetched job."""
    org_id = str(job.organisation_id)
    job_id = str(job.id)

    job.status = "running"
    job.started_at = _now()
    job.error_message = None
    session.commit()
    publish_job_update(org_id, job_id, "running")

    document = session.execute(
        select(Document).where(Document.id == job.document_id)
    ).scalar_one_or_none()

    if document is None:
        raise RuntimeError(f"Document {job.document_id} not found")
    if document.status not in ANALYSABLE_DOCUMENT_STATUSES:
        raise RuntimeError(
            f"Document {document.id} has status '{document.status}'; "
            f"expected one of {sorted(ANALYSABLE_DOCUMENT_STATUSES)}"
        )

    document.status = "analysing"
    session.commit()

    initial_state = build_initial_state(
        document_id=str(document.id),
        organisation_id=str(job.organisation_id),
        analysis_job_id=str(job.id),
        job_type=job.job_type,
        document_text=document.extracted_text or "",
        document_name=document.name,
    )

    config = {"configurable": {"thread_id": str(job.id)}}
    final_state = asyncio.run(counseliq_graph.ainvoke(initial_state, config=config))

    # Stream each agent's trace step to subscribed WebSocket clients.
    for step in final_state.get("steps", []):
        publish_agent_step(org_id, job_id, step)

    # A hard pipeline error (e.g. no extractable text) is a job failure.
    if final_state.get("error"):
        raise RuntimeError(final_state["error"])

    return _persist_success(session, job, document, final_state)


def _persist_success(
    session: Session,
    job: AnalysisJob,
    document: Document,
    final_state: dict,
) -> dict[str, str]:
    """Write clauses, risk flags, trace, and final job/document state."""
    clauses_data = final_state.get("clauses") or []
    risk_flags_data = final_state.get("risk_flags") or []

    # 1. Persist clauses (in extraction order) so risk flags can reference them.
    created_clauses: list[Clause] = []
    for clause in clauses_data:
        record = Clause(
            document_id=document.id,
            clause_type=clause.get("clause_type"),
            content=clause.get("content") or "",
            page_number=clause.get("page_number"),
            metadata_={
                "key_entities": clause.get("key_entities") or [],
                "risk_indicators": clause.get("risk_indicators") or [],
            },
        )
        session.add(record)
        created_clauses.append(record)
    session.flush()  # assign clause ids for FK linking

    # 2. Persist risk flags, linking each to its clause via clause_index.
    for flag in risk_flags_data:
        clause_index = flag.get("clause_index")
        clause_id = (
            created_clauses[clause_index].id
            if isinstance(clause_index, int) and 0 <= clause_index < len(created_clauses)
            else None
        )
        session.add(
            RiskFlag(
                analysis_job_id=job.id,
                clause_id=clause_id,
                category=flag.get("category"),
                severity=flag.get("severity"),
                title=flag.get("title") or "Untitled risk",
                description=flag.get("description"),
                suggested_action=flag.get("suggested_action"),
                agent_reasoning=flag.get("agent_reasoning"),
                cited_regulation=flag.get("cited_regulation"),
                confidence_score=flag.get("confidence_score"),
                status="open",
            )
        )

    # 3. Update the job. agent_trace is a structured JSONB document holding the
    #    full trace plus outputs the report endpoint surfaces.
    job.agent_trace = {
        "steps": final_state.get("steps") or [],
        "summary_report": final_state.get("summary_report"),
        "drafted_alternatives": final_state.get("drafted_alternatives") or [],
        "research_findings": final_state.get("research_findings") or [],
        "should_escalate": bool(final_state.get("should_escalate")),
    }
    job.overall_risk_score = final_state.get("overall_risk_score")
    job.status = "awaiting_review"
    job.completed_at = _now()

    document.status = "completed"

    write_audit_log_sync(
        session,
        organisation_id=job.organisation_id,
        action="analysis.completed",
        user_id=job.initiated_by,
        resource_type="analysis_job",
        resource_id=job.id,
        payload={
            "overall_risk_score": job.overall_risk_score,
            "clauses": len(created_clauses),
            "risk_flags": len(risk_flags_data),
            "should_escalate": bool(final_state.get("should_escalate")),
        },
    )

    session.commit()
    publish_job_update(
        str(job.organisation_id),
        str(job.id),
        "awaiting_review",
        {
            "overall_risk_score": job.overall_risk_score,
            "flag_count": len(risk_flags_data),
        },
    )
    logger.info(
        "Analysis complete for job %s: score=%s, %d clauses, %d flags",
        job.id,
        job.overall_risk_score,
        len(created_clauses),
        len(risk_flags_data),
    )
    return {"analysis_job_id": str(job.id), "status": "awaiting_review"}


def _mark_failed(session: Session, job: AnalysisJob, message: str) -> None:
    """Flip a job (and its document) to the failed state and audit it."""
    job.status = "failed"
    job.error_message = message[:2000]
    job.completed_at = _now()

    document = session.execute(
        select(Document).where(Document.id == job.document_id)
    ).scalar_one_or_none()
    if document is not None and document.status == "analysing":
        document.status = "failed"

    write_audit_log_sync(
        session,
        organisation_id=job.organisation_id,
        action="analysis.failed",
        user_id=job.initiated_by,
        resource_type="analysis_job",
        resource_id=job.id,
        payload={"error": message[:2000]},
    )
