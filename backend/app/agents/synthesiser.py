"""Synthesiser agent — writes the executive review summary."""

from __future__ import annotations

import logging
import time

from app.agents.base import BaseAgent
from app.agents.state import CounselIQState

logger = logging.getLogger("counseliq.agents.synthesiser")

PROMPT_TEMPLATE = """You are a legal review report writer for Indian enterprises.

Produce a concise executive summary of this contract review for a senior lawyer.

The summary must include:
1. CONTRACT OVERVIEW (2-3 sentences: what is this contract, parties, key terms)
2. OVERALL RISK ASSESSMENT (1 sentence with the numeric score and what it means)
3. CRITICAL ISSUES (bullet list of critical/high risks - title + one sentence each)
4. KEY RECOMMENDATIONS (top 3-5 actions the lawyer should take, numbered)
5. NEXT STEPS (what requires human judgment vs what is routine)

Write for a senior lawyer who will use this to decide where to focus their time.
Be precise, not verbose. No generic statements.

Risk score: {overall_risk_score}/100
Total clauses analysed: {clause_count}
Total risk flags: {flag_count}
Critical flags: {critical_count}

Risk flags summary:
{flags_summary}

Research findings:
{research_summary}
"""


class SynthesiserAgent(BaseAgent):
    """Distils the full analysis into a senior-lawyer-facing summary report."""

    name = "synthesiser"

    async def run(self, state: CounselIQState) -> dict:
        start = time.time()

        clauses = state.get("clauses") or []
        risk_flags = state.get("risk_flags") or []
        research_findings = state.get("research_findings") or []
        overall_risk_score = state.get("overall_risk_score") or 0.0
        critical_count = sum(1 for flag in risk_flags if flag.get("severity") == "critical")

        flags_summary = self._build_flags_summary(risk_flags)
        research_summary = self._build_research_summary(research_findings)

        prompt = PROMPT_TEMPLATE.format(
            overall_risk_score=round(float(overall_risk_score), 1),
            clause_count=len(clauses),
            flag_count=len(risk_flags),
            critical_count=critical_count,
            flags_summary=flags_summary,
            research_summary=research_summary,
        )

        try:
            report = (await self._acall_llm(prompt)).strip()
            step = self._record_step(
                status="completed",
                input_summary=(
                    f"{len(clauses)} clauses, {len(risk_flags)} flags, "
                    f"score={float(overall_risk_score):.1f}"
                ),
                output_summary=f"summary report ({len(report)} chars)",
                confidence=0.85,
                start_time=start,
            )
            return {
                "summary_report": report,
                "steps": [step],
                "current_agent": self.name,
            }

        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            logger.exception("Synthesiser failed: %s", exc)
            # Even on failure, emit a deterministic fallback summary so the
            # review always carries a human-readable headline.
            fallback = self._fallback_summary(
                overall_risk_score, len(clauses), len(risk_flags), critical_count
            )
            step = self._record_step(
                status="failed",
                input_summary=f"{len(clauses)} clauses, {len(risk_flags)} flags",
                output_summary=f"synthesis error, used fallback: {exc}",
                confidence=0.2,
                start_time=start,
            )
            return {
                "summary_report": fallback,
                "steps": [step],
                "current_agent": self.name,
            }

    @staticmethod
    def _build_flags_summary(risk_flags: list[dict]) -> str:
        if not risk_flags:
            return "No risk flags were raised."
        lines = []
        for flag in risk_flags:
            lines.append(
                f"- [{flag.get('severity', 'unknown')}] {flag.get('title', 'Untitled')}: "
                f"{flag.get('description') or 'No description.'}"
            )
        return "\n".join(lines)

    @staticmethod
    def _build_research_summary(research_findings: list[dict]) -> str:
        if not research_findings:
            return "No regulatory research findings."
        lines = []
        for finding in research_findings:
            name = finding.get("regulation_name") or "Unknown regulation"
            section = finding.get("section")
            ref = f"{name} {section}".strip() if section else name
            lines.append(f"- {ref}: {finding.get('relevance') or 'See source.'}")
        return "\n".join(lines)

    @staticmethod
    def _fallback_summary(
        score: float, clause_count: int, flag_count: int, critical_count: int
    ) -> str:
        return (
            "CONTRACT REVIEW SUMMARY (auto-generated fallback)\n\n"
            f"OVERALL RISK ASSESSMENT: {float(score):.1f}/100.\n"
            f"Analysed {clause_count} clauses and raised {flag_count} risk flags "
            f"({critical_count} critical).\n\n"
            "The narrative summary could not be generated automatically; please "
            "review the individual risk flags below."
        )
