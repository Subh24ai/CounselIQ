"""Extractor agent — segments raw contract text into typed clauses."""

from __future__ import annotations

import difflib
import logging
import time

from app.agents.base import BaseAgent
from app.agents.state import CounselIQState

logger = logging.getLogger("counseliq.agents.extractor")

# A clause whose normalised content is this similar to an earlier clause is
# treated as a duplicate extraction (e.g. the same term quoted in a recital and
# the operative section) and dropped, keeping the first occurrence.
NEAR_DUPLICATE_RATIO = 0.92

# Safety margin below the model context window; very long contracts are
# truncated rather than rejected so analysis can still proceed on the bulk of
# the document.
MAX_DOCUMENT_CHARS = 180_000

VALID_CLAUSE_TYPES = {
    "indemnity",
    "liability",
    "ip_assignment",
    "auto_renewal",
    "jurisdiction",
    "termination",
    "payment_terms",
    "confidentiality",
    "data_protection",
    "governing_law",
    "dispute_resolution",
    "force_majeure",
    "warranty",
    "other",
}

PROMPT_TEMPLATE = """You are a legal clause extraction specialist for Indian contracts.

Extract ALL distinct clauses from this contract text. For each clause identify:
- clause_type: one of [indemnity, liability, ip_assignment, auto_renewal, jurisdiction,
  termination, payment_terms, confidentiality, data_protection, governing_law,
  dispute_resolution, force_majeure, warranty, other]
- content: the exact clause text
- page_number: estimated page (null if unknown)
- key_entities: list of parties, amounts, dates mentioned
- risk_indicators: any words/phrases that suggest legal risk

Return JSON array only. No preamble. No markdown.
Format: [{{"clause_type": "...", "content": "...", "page_number": null,
           "key_entities": [], "risk_indicators": []}}]

Contract text:
{document_text}
"""


class ExtractorAgent(BaseAgent):
    """Extracts and normalises the clauses present in a contract."""

    name = "extractor"

    async def run(self, state: CounselIQState) -> dict:
        start = time.time()
        document_text = (state.get("document_text") or "").strip()

        if not document_text:
            step = self._record_step(
                status="failed",
                input_summary="empty document text",
                output_summary="no text to extract",
                confidence=0.0,
                start_time=start,
            )
            return {
                "error": "Document has no extractable text",
                "clauses": [],
                "steps": [step],
                "current_agent": self.name,
            }

        truncated = document_text[:MAX_DOCUMENT_CHARS]
        prompt = PROMPT_TEMPLATE.format(document_text=truncated)

        try:
            raw = await self._acall_llm(prompt)
            parsed = self.parse_json_array(raw)
            clauses = [self._normalise_clause(item) for item in parsed]
            deduped = self._deduplicate_clauses(clauses)
            dropped = len(clauses) - len(deduped)
            if dropped:
                logger.info("Extractor dropped %d duplicate clause(s)", dropped)
            clauses = deduped

            step = self._record_step(
                status="completed",
                input_summary=f"{len(truncated)} chars of contract text",
                output_summary=f"extracted {len(clauses)} clauses",
                confidence=0.9 if clauses else 0.3,
                start_time=start,
            )
            return {
                "clauses": clauses,
                "steps": [step],
                "current_agent": self.name,
            }

        except Exception as exc:  # noqa: BLE001 - degrade gracefully, never crash the graph
            logger.exception("Extractor failed: %s", exc)
            step = self._record_step(
                status="failed",
                input_summary=f"{len(truncated)} chars of contract text",
                output_summary=f"extraction error: {exc}",
                confidence=0.0,
                start_time=start,
            )
            return {
                "error": f"Clause extraction failed: {exc}",
                "clauses": [],
                "steps": [step],
                "current_agent": self.name,
            }

    @staticmethod
    def _deduplicate_clauses(clauses: list[dict]) -> list[dict]:
        """Drop exact/near-duplicate clauses, keeping the first occurrence.

        Content is normalised (lowercased, whitespace-collapsed) and compared
        with :class:`difflib.SequenceMatcher`; a ratio above
        :data:`NEAR_DUPLICATE_RATIO` is treated as a duplicate. The same term
        often appears in both a recital and the operative section, which the LLM
        legitimately returns twice — we keep only one.
        """
        unique: list[dict] = []
        seen_norms: list[str] = []
        for clause in clauses:
            norm = " ".join((clause.get("content") or "").lower().split())
            is_duplicate = any(
                difflib.SequenceMatcher(None, norm, prev).ratio()
                > NEAR_DUPLICATE_RATIO
                for prev in seen_norms
            )
            if not is_duplicate:
                unique.append(clause)
                seen_norms.append(norm)
        return unique

    @staticmethod
    def _normalise_clause(item: dict) -> dict:
        """Coerce one raw clause object into a complete, valid clause dict."""
        clause_type = str(item.get("clause_type") or "other").strip().lower()
        if clause_type not in VALID_CLAUSE_TYPES:
            clause_type = "other"

        page_number = item.get("page_number")
        if isinstance(page_number, str) and page_number.isdigit():
            page_number = int(page_number)
        elif not isinstance(page_number, int):
            page_number = None

        key_entities = item.get("key_entities")
        if not isinstance(key_entities, list):
            key_entities = []

        risk_indicators = item.get("risk_indicators")
        if not isinstance(risk_indicators, list):
            risk_indicators = []

        return {
            "clause_type": clause_type,
            "content": str(item.get("content") or "").strip(),
            "page_number": page_number,
            "key_entities": [str(e) for e in key_entities],
            "risk_indicators": [str(r) for r in risk_indicators],
        }
