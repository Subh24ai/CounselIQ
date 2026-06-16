"""LangGraph multi-agent definitions for CounselIQ.

The analysis pipeline is a five-agent LangGraph: extractor -> risk_scorer ->
researcher -> (drafter) -> synthesiser. The compiled graph is exported as
:data:`counseliq_graph`.
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.drafter import DrafterAgent
from app.agents.extractor import ExtractorAgent
from app.agents.orchestrator import build_initial_state, counseliq_graph
from app.agents.researcher import ResearcherAgent
from app.agents.risk_scorer import RISK_TAXONOMY, RiskScorerAgent
from app.agents.state import AgentStep, CounselIQState
from app.agents.synthesiser import SynthesiserAgent

__all__ = [
    "BaseAgent",
    "ExtractorAgent",
    "RiskScorerAgent",
    "ResearcherAgent",
    "DrafterAgent",
    "SynthesiserAgent",
    "RISK_TAXONOMY",
    "AgentStep",
    "CounselIQState",
    "counseliq_graph",
    "build_initial_state",
]
