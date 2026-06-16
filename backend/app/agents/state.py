"""Shared LangGraph state for the CounselIQ analysis pipeline.

Every agent reads from and writes to a single :class:`CounselIQState`. The
``steps`` channel uses an append-only reducer so each agent can record its own
trace entry without clobbering earlier ones; all other channels are
last-writer-wins (a node returning a key overwrites the previous value).
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class AgentStep(TypedDict):
    """A single entry in the agent execution trace.

    Persisted (as part of ``AnalysisJob.agent_trace``) so the full reasoning
    chain of a review is auditable after the fact.
    """

    agent: str  # 'orchestrator','extractor','risk_scorer','researcher','drafter','synthesiser'
    status: str  # 'started','completed','failed','skipped'
    input_summary: str  # brief description of what was passed in
    output_summary: str  # brief description of what was produced
    confidence: float  # 0.0-1.0
    duration_ms: int
    timestamp: str  # ISO8601


class CounselIQState(TypedDict, total=False):
    """The graph state threaded through every agent.

    ``total=False`` so callers may construct an initial state without having to
    pre-populate every intermediate channel; nodes fill them in as they run and
    agents read defensively via ``.get``.
    """

    # --- Inputs -------------------------------------------------------------
    document_id: str
    organisation_id: str
    analysis_job_id: str
    job_type: str  # 'contract_review','due_diligence','reg_compliance','risk_assessment'
    document_text: str
    document_name: str

    # --- Intermediate outputs (each agent writes here) ----------------------
    clauses: list[dict]  # extracted clauses with metadata
    risk_flags: list[dict]  # raw risk flags before DB write
    research_findings: list[dict]  # regulatory references found
    drafted_alternatives: list[dict]  # redlined clause alternatives

    # --- Orchestration ------------------------------------------------------
    steps: Annotated[list[AgentStep], operator.add]  # append-only trace log
    current_agent: str
    error: str | None
    should_escalate: bool  # true if any critical risk found

    # --- Final output -------------------------------------------------------
    overall_risk_score: float | None
    summary_report: str | None
