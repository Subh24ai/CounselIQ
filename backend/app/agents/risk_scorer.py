"""Risk Scorer agent — grades clauses against a weighted risk taxonomy."""

from __future__ import annotations

import json
import logging
import time

from app.agents.base import BaseAgent
from app.agents.state import CounselIQState

logger = logging.getLogger("counseliq.agents.risk_scorer")

RISK_TAXONOMY: dict[str, dict] = {
    "indemnity": {
        "description": "Clauses requiring one party to compensate the other for losses",
        "red_flags": [
            "unlimited indemnity",
            "consequential damages",
            "third party claims",
            "without limitation",
        ],
        "weight": 0.20,
    },
    "liability_cap": {
        "description": "Limitations on financial liability",
        "red_flags": ["no liability cap", "uncapped", "unlimited liability", "full damages"],
        "weight": 0.18,
    },
    "ip_assignment": {
        "description": "Transfer of intellectual property rights",
        "red_flags": [
            "assigns all rights",
            "work for hire",
            "perpetual irrevocable",
            "without compensation",
        ],
        "weight": 0.15,
    },
    "auto_renewal": {
        "description": "Automatic contract renewal terms",
        "red_flags": ["automatically renews", "unless notice given", "evergreen", "tacit renewal"],
        "weight": 0.10,
    },
    "jurisdiction": {
        "description": "Choice of law and dispute forum",
        "red_flags": [
            "foreign jurisdiction",
            "arbitration only",
            "no Indian courts",
            "exclusive jurisdiction abroad",
        ],
        "weight": 0.12,
    },
    "termination": {
        "description": "Conditions and rights for ending the contract",
        "red_flags": [
            "no termination right",
            "lock-in period",
            "penalty on exit",
            "unilateral termination",
        ],
        "weight": 0.10,
    },
    "payment_terms": {
        "description": "Payment obligations and penalties",
        "red_flags": [
            "interest on late payment",
            "penalty clause",
            "unilateral price change",
            "automatic escalation",
        ],
        "weight": 0.08,
    },
    "data_protection": {
        "description": "Data handling, privacy, and security obligations",
        "red_flags": [
            "no data protection",
            "transfers abroad",
            "no breach notification",
            "unlimited retention",
        ],
        "weight": 0.07,
    },
}

# Default taxonomy weight for any category the LLM returns that is not in the
# taxonomy above (e.g. 'regulatory').
DEFAULT_WEIGHT = 0.05

SEVERITY_MULTIPLIER = {"critical": 1.0, "high": 0.7, "medium": 0.4, "low": 0.2}

PROMPT_TEMPLATE = """You are a legal risk assessment specialist for Indian corporate contracts.

Analyse each clause below against the risk taxonomy and Indian legal standards
(Indian Contract Act 1872, IT Act 2000, upcoming DPDP Act, Companies Act 2013).

For each HIGH or CRITICAL risk found, output:
- clause_index: index in the input array
- category: from taxonomy keys
- severity: 'critical' | 'high' | 'medium' | 'low'
- title: short risk title (max 10 words)
- description: what the risk is (2-3 sentences)
- suggested_action: what the lawyer should do (1-2 sentences)
- agent_reasoning: your reasoning chain (3-5 sentences)
- cited_regulation: specific Indian law or regulation if applicable (or null)
- confidence_score: 0.0-1.0

Return JSON array only. No preamble. No markdown.

Risk taxonomy:
{taxonomy}

Clauses to analyse:
{clauses_json}
"""


class RiskScorerAgent(BaseAgent):
    """Scores extracted clauses and computes an overall document risk score."""

    name = "risk_scorer"

    async def run(self, state: CounselIQState) -> dict:
        start = time.time()
        clauses = state.get("clauses") or []

        if not clauses:
            step = self._record_step(
                status="skipped",
                input_summary="no clauses to score",
                output_summary="risk scoring skipped",
                confidence=1.0,
                start_time=start,
            )
            return {
                "risk_flags": [],
                "overall_risk_score": 0.0,
                "should_escalate": False,
                "steps": [step],
                "current_agent": self.name,
            }

        clauses_json = json.dumps(
            [
                {
                    "index": idx,
                    "clause_type": clause.get("clause_type"),
                    "content": clause.get("content"),
                }
                for idx, clause in enumerate(clauses)
            ],
            ensure_ascii=False,
        )
        taxonomy_json = json.dumps(RISK_TAXONOMY, ensure_ascii=False)
        prompt = PROMPT_TEMPLATE.format(taxonomy=taxonomy_json, clauses_json=clauses_json)

        try:
            raw = await self._acall_llm(prompt)
            flags = [
                self._normalise_flag(item, len(clauses))
                for item in self.parse_json_array(raw)
            ]

            overall = self._compute_score(flags)
            should_escalate = any(flag["severity"] == "critical" for flag in flags)

            step = self._record_step(
                status="completed",
                input_summary=f"{len(clauses)} clauses",
                output_summary=(
                    f"{len(flags)} risk flags, score={overall:.1f}, "
                    f"escalate={should_escalate}"
                ),
                confidence=0.85 if flags else 0.6,
                start_time=start,
            )
            return {
                "risk_flags": flags,
                "overall_risk_score": overall,
                "should_escalate": should_escalate,
                "steps": [step],
                "current_agent": self.name,
            }

        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            logger.exception("Risk scorer failed: %s", exc)
            step = self._record_step(
                status="failed",
                input_summary=f"{len(clauses)} clauses",
                output_summary=f"risk scoring error: {exc}",
                confidence=0.0,
                start_time=start,
            )
            return {
                "risk_flags": [],
                "overall_risk_score": 0.0,
                "should_escalate": False,
                "steps": [step],
                "current_agent": self.name,
            }

    @staticmethod
    def _compute_score(flags: list[dict]) -> float:
        """Weighted risk score in [0, 100] per the product specification."""
        score = 0.0
        for flag in flags:
            weight = RISK_TAXONOMY.get(flag["category"], {}).get("weight", DEFAULT_WEIGHT)
            severity_multiplier = SEVERITY_MULTIPLIER.get(flag["severity"], 0.2)
            score += weight * severity_multiplier * flag["confidence_score"] * 100
        return min(100.0, score)

    @staticmethod
    def _normalise_flag(item: dict, clause_count: int) -> dict:
        """Coerce a raw risk flag into a complete, valid flag dict."""
        severity = str(item.get("severity") or "medium").strip().lower()
        if severity not in SEVERITY_MULTIPLIER:
            severity = "medium"

        category = item.get("category")
        category = str(category).strip().lower() if category else None

        clause_index = item.get("clause_index")
        if not isinstance(clause_index, int) or not (0 <= clause_index < clause_count):
            clause_index = None

        try:
            confidence = float(item.get("confidence_score", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        cited = item.get("cited_regulation")
        cited = str(cited) if cited else None

        return {
            "clause_index": clause_index,
            "category": category,
            "severity": severity,
            "title": str(item.get("title") or "Untitled risk").strip()[:512],
            "description": str(item.get("description") or "").strip() or None,
            "suggested_action": str(item.get("suggested_action") or "").strip() or None,
            "agent_reasoning": str(item.get("agent_reasoning") or "").strip() or None,
            "cited_regulation": cited,
            "confidence_score": confidence,
        }
