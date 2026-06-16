"""Researcher agent — attaches Indian regulatory references to risk flags."""

from __future__ import annotations

import json
import logging
import time

from app.agents.base import BaseAgent
from app.agents.state import CounselIQState

logger = logging.getLogger("counseliq.agents.researcher")

# Only the most material risks are researched, to keep latency and token spend
# bounded.
RESEARCHED_SEVERITIES = {"critical", "high"}

PROMPT_TEMPLATE = """You are a legal research specialist with deep knowledge of Indian law.

For each risk flag below, identify the most relevant Indian legal provisions,
regulations, or case law principles that apply.

For each finding provide:
- risk_flag_index: index in input array
- regulation_name: full name of the regulation/act
- section: specific section or article (if known)
- relevance: how it applies to this specific risk (2-3 sentences)
- implication: what this means for the contracting party (1-2 sentences)
- source_hint: where to verify this (e.g. "MCA website", "SEBI circular database")

Focus on:
- Indian Contract Act 1872
- Information Technology Act 2000 and IT Rules 2011
- Digital Personal Data Protection Act 2023
- Companies Act 2013
- Competition Act 2002
- SEBI regulations (if financial services context)
- IRDAI guidelines (if insurance context)
- RBI Master Directions (if banking context)

Return JSON array only. No preamble. No markdown.

Risk flags to research:
{risk_flags_json}

Contract context (document name): {document_name}
"""


class ResearcherAgent(BaseAgent):
    """Researches regulatory backing for the highest-severity risk flags."""

    name = "researcher"

    async def run(self, state: CounselIQState) -> dict:
        start = time.time()
        risk_flags = state.get("risk_flags") or []

        if not risk_flags:
            step = self._record_step(
                status="skipped",
                input_summary="no risk flags to research",
                output_summary="research skipped",
                confidence=1.0,
                start_time=start,
            )
            return {
                "research_findings": [],
                "steps": [step],
                "current_agent": self.name,
            }

        # Map each researched flag back to its original index in risk_flags so
        # findings can be merged into the correct flag.
        researched = [
            (idx, flag)
            for idx, flag in enumerate(risk_flags)
            if flag.get("severity") in RESEARCHED_SEVERITIES
        ]

        if not researched:
            step = self._record_step(
                status="skipped",
                input_summary=f"{len(risk_flags)} flags, none high/critical",
                output_summary="research skipped",
                confidence=1.0,
                start_time=start,
            )
            return {
                "research_findings": [],
                "steps": [step],
                "current_agent": self.name,
            }

        # The LLM sees a compact, re-indexed list; ``local_index`` maps back to
        # the global position in ``risk_flags``.
        payload = [
            {
                "index": local_index,
                "category": flag.get("category"),
                "severity": flag.get("severity"),
                "title": flag.get("title"),
                "description": flag.get("description"),
            }
            for local_index, (_global_index, flag) in enumerate(researched)
        ]
        prompt = PROMPT_TEMPLATE.format(
            risk_flags_json=json.dumps(payload, ensure_ascii=False),
            document_name=state.get("document_name") or "Unknown document",
        )

        try:
            raw = await self._acall_llm(prompt)
            findings = self.parse_json_array(raw)
            updated_flags = self._merge_findings(risk_flags, researched, findings)

            step = self._record_step(
                status="completed",
                input_summary=f"{len(researched)} high/critical flags",
                output_summary=f"{len(findings)} regulatory findings",
                confidence=0.8 if findings else 0.5,
                start_time=start,
            )
            return {
                "research_findings": findings,
                "risk_flags": updated_flags,
                "steps": [step],
                "current_agent": self.name,
            }

        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            logger.exception("Researcher failed: %s", exc)
            step = self._record_step(
                status="failed",
                input_summary=f"{len(researched)} high/critical flags",
                output_summary=f"research error: {exc}",
                confidence=0.0,
                start_time=start,
            )
            return {
                "research_findings": [],
                "steps": [step],
                "current_agent": self.name,
            }

    @staticmethod
    def _merge_findings(
        risk_flags: list[dict],
        researched: list[tuple[int, dict]],
        findings: list[dict],
    ) -> list[dict]:
        """Copy ``cited_regulation`` from each finding onto its source flag.

        ``risk_flag_index`` in a finding refers to the compact, re-indexed list
        sent to the LLM, which is translated back to the global flag index.
        Existing citations are not overwritten with empty values.
        """
        merged = [dict(flag) for flag in risk_flags]
        for finding in findings:
            local_index = finding.get("risk_flag_index")
            if not isinstance(local_index, int) or not (0 <= local_index < len(researched)):
                continue
            global_index = researched[local_index][0]
            regulation = finding.get("regulation_name")
            section = finding.get("section")
            if regulation:
                citation = f"{regulation} {section}".strip() if section else str(regulation)
                if not merged[global_index].get("cited_regulation"):
                    merged[global_index]["cited_regulation"] = citation[:255]
        return merged
