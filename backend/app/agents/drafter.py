"""Drafter agent — proposes safer alternatives for high-risk clauses."""

from __future__ import annotations

import json
import logging
import time

from app.agents.base import BaseAgent
from app.agents.state import CounselIQState

logger = logging.getLogger("counseliq.agents.drafter")

REDRAFTED_SEVERITIES = {"critical", "high"}

PROMPT_TEMPLATE = """You are a senior Indian corporate lawyer specialising in contract drafting.

For each high-risk clause below, provide a safer alternative clause that:
- Protects the interests of the reviewing party
- Complies with Indian law
- Is commercially reasonable
- Clearly marks what changed and why

For each alternative provide:
- clause_index: index in input
- original_clause_type: the clause type
- alternative_text: the full rewritten clause (ready to use)
- changes_summary: bullet points of what was changed
- negotiation_note: how to present this to the other party (1-2 sentences)
- fallback_position: minimum acceptable version if other party pushes back

Return JSON array only. No preamble. No markdown.

High-risk clauses requiring redrafting:
{high_risk_clauses_json}
"""


class DrafterAgent(BaseAgent):
    """Rewrites the riskiest clauses into safer, India-compliant alternatives."""

    name = "drafter"

    async def run(self, state: CounselIQState) -> dict:
        start = time.time()
        risk_flags = state.get("risk_flags") or []
        clauses = state.get("clauses") or []

        high_risk_flags = [
            flag for flag in risk_flags if flag.get("severity") in REDRAFTED_SEVERITIES
        ]

        if not high_risk_flags:
            step = self._record_step(
                status="skipped",
                input_summary=f"{len(risk_flags)} flags, none high/critical",
                output_summary="drafting skipped",
                confidence=1.0,
                start_time=start,
            )
            return {
                "drafted_alternatives": [],
                "steps": [step],
                "current_agent": self.name,
            }

        # Resolve each high-risk flag to its original clause text via clause_index.
        # ``index`` re-indexes the compact payload sent to the LLM so the returned
        # ``clause_index`` is unambiguous.
        high_risk_clauses = []
        for index, flag in enumerate(high_risk_flags):
            clause_index = flag.get("clause_index")
            clause = (
                clauses[clause_index]
                if isinstance(clause_index, int) and 0 <= clause_index < len(clauses)
                else {}
            )
            high_risk_clauses.append(
                {
                    "index": index,
                    "clause_type": clause.get("clause_type") or flag.get("category") or "other",
                    "content": clause.get("content") or "",
                    "risk_title": flag.get("title"),
                    "severity": flag.get("severity"),
                }
            )

        prompt = PROMPT_TEMPLATE.format(
            high_risk_clauses_json=json.dumps(high_risk_clauses, ensure_ascii=False)
        )

        try:
            raw = await self._acall_llm(prompt)
            alternatives = self.parse_json_array(raw)

            step = self._record_step(
                status="completed",
                input_summary=f"{len(high_risk_clauses)} high-risk clauses",
                output_summary=f"{len(alternatives)} redrafted alternatives",
                confidence=0.8 if alternatives else 0.5,
                start_time=start,
            )
            return {
                "drafted_alternatives": alternatives,
                "steps": [step],
                "current_agent": self.name,
            }

        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            logger.exception("Drafter failed: %s", exc)
            step = self._record_step(
                status="failed",
                input_summary=f"{len(high_risk_clauses)} high-risk clauses",
                output_summary=f"drafting error: {exc}",
                confidence=0.0,
                start_time=start,
            )
            return {
                "drafted_alternatives": [],
                "steps": [step],
                "current_agent": self.name,
            }
