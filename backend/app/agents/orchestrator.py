"""LangGraph orchestrator — the CounselIQ analysis brain.

Wires the five agents into a directed graph:

    START -> extractor -> risk_scorer -> researcher -> (drafter?) -> synthesiser -> END

A hard failure in the extractor (no clauses / unparseable response) short-circuits
to ``error_handler`` and ends the run; the Celery task then marks the job failed.
Every other agent degrades gracefully (records a ``skipped``/``failed`` step and
emits empty output) so the graph always reaches a terminal state and the trace is
always complete. The drafter is conditionally skipped when nothing is high-risk.

The compiled graph is exported as :data:`counseliq_graph`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.drafter import DrafterAgent
from app.agents.extractor import ExtractorAgent
from app.agents.researcher import ResearcherAgent
from app.agents.risk_scorer import RiskScorerAgent
from app.agents.state import AgentStep, CounselIQState
from app.agents.synthesiser import SynthesiserAgent

logger = logging.getLogger("counseliq.agents.orchestrator")

HIGH_RISK_SEVERITIES = {"critical", "high"}


# --- Node functions ---------------------------------------------------------
# Agents are constructed lazily inside each node so that the LLM client is only
# built when the node actually runs (and so tests can patch ``ChatAnthropic``).


async def _extractor_node(state: CounselIQState) -> dict:
    return await ExtractorAgent().run(state)


async def _risk_scorer_node(state: CounselIQState) -> dict:
    return await RiskScorerAgent().run(state)


async def _researcher_node(state: CounselIQState) -> dict:
    return await ResearcherAgent().run(state)


async def _drafter_node(state: CounselIQState) -> dict:
    return await DrafterAgent().run(state)


async def _synthesiser_node(state: CounselIQState) -> dict:
    return await SynthesiserAgent().run(state)


async def _error_handler_node(state: CounselIQState) -> dict:
    """Terminal node for a hard pipeline failure.

    The error is already set on the state by the failing agent; this records a
    closing trace entry. The Celery task inspects ``state['error']`` and marks
    the :class:`AnalysisJob` failed.
    """
    error = state.get("error") or "Unknown pipeline error"
    logger.error("Analysis pipeline aborted: %s", error)
    step = AgentStep(
        agent="orchestrator",
        status="failed",
        input_summary="hard pipeline error",
        output_summary=error,
        confidence=0.0,
        duration_ms=0,
        timestamp=datetime.now(UTC).isoformat(),
    )
    return {"steps": [step], "current_agent": "error_handler"}


# --- Conditional routing ----------------------------------------------------


def _after_extractor(state: CounselIQState) -> str:
    """Abort to the error handler if extraction hard-failed; else continue."""
    return "error_handler" if state.get("error") else "risk_scorer"


def _should_draft(state: CounselIQState) -> str:
    """Route to the drafter only when there is something high-risk to redraft."""
    has_high_risk = any(
        flag.get("severity") in HIGH_RISK_SEVERITIES for flag in (state.get("risk_flags") or [])
    )
    return "drafter" if has_high_risk else "synthesiser"


# --- Graph construction -----------------------------------------------------


def build_graph() -> StateGraph:
    """Construct (uncompiled) the CounselIQ analysis StateGraph."""
    graph = StateGraph(CounselIQState)

    graph.add_node("extractor", _extractor_node)
    graph.add_node("risk_scorer", _risk_scorer_node)
    graph.add_node("researcher", _researcher_node)
    graph.add_node("drafter", _drafter_node)
    graph.add_node("synthesiser", _synthesiser_node)
    graph.add_node("error_handler", _error_handler_node)

    graph.add_edge(START, "extractor")
    graph.add_conditional_edges(
        "extractor",
        _after_extractor,
        {"risk_scorer": "risk_scorer", "error_handler": "error_handler"},
    )
    graph.add_edge("risk_scorer", "researcher")
    graph.add_conditional_edges(
        "researcher",
        _should_draft,
        {"drafter": "drafter", "synthesiser": "synthesiser"},
    )
    graph.add_edge("drafter", "synthesiser")
    graph.add_edge("synthesiser", END)
    graph.add_edge("error_handler", END)

    return graph


def _compile():
    """Compile the graph with an in-memory checkpointer keyed by thread_id."""
    return build_graph().compile(checkpointer=MemorySaver())


# The single compiled application graph. ``thread_id`` (the analysis job id) is
# supplied per-invocation via ``config={"configurable": {"thread_id": ...}}``.
counseliq_graph = _compile()


def build_initial_state(
    *,
    document_id: str,
    organisation_id: str,
    analysis_job_id: str,
    job_type: str,
    document_text: str,
    document_name: str,
) -> CounselIQState:
    """Build a fully-initialised state for a fresh analysis run."""
    return CounselIQState(
        document_id=document_id,
        organisation_id=organisation_id,
        analysis_job_id=analysis_job_id,
        job_type=job_type,
        document_text=document_text,
        document_name=document_name,
        clauses=[],
        risk_flags=[],
        research_findings=[],
        drafted_alternatives=[],
        steps=[],
        current_agent="orchestrator",
        error=None,
        should_escalate=False,
        overall_risk_score=None,
        summary_report=None,
    )


__all__ = [
    "counseliq_graph",
    "build_graph",
    "build_initial_state",
]
