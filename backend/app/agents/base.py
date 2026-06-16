"""Base agent class shared by every node in the CounselIQ graph.

Each concrete agent subclasses :class:`BaseAgent`, sets a class-level ``name``,
and implements :meth:`run`. The base class owns the LLM client, a helper to
invoke it, a tolerant JSON parser (LLMs frequently wrap JSON in prose or
markdown fences), and trace-step construction.
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from app.agents.state import AgentStep, CounselIQState
from app.config import settings

# Single model used across every agent (per product spec).
LLM_MODEL = "claude-sonnet-4-6"
LLM_MAX_TOKENS = 4096


class BaseAgent:
    """Common behaviour for all pipeline agents.

    Subclasses set ``name`` and implement :meth:`run`. The LLM client is built
    lazily per instance so that, in tests, patching ``ChatAnthropic`` before the
    agent is constructed yields a mock client.
    """

    name: str = "base"

    def __init__(self) -> None:
        self.llm = ChatAnthropic(
            model=LLM_MODEL,
            anthropic_api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=LLM_MAX_TOKENS,
        )

    # --- LLM ----------------------------------------------------------------
    async def _acall_llm(self, prompt: str) -> str:
        """Invoke the LLM with a single user message and return text content.

        Anthropic responses may arrive as a plain string or as a list of
        content blocks; both are normalised to a single string here.
        """
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        content = response.content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    parts.append(str(block.get("text", "")))
                else:
                    parts.append(str(block))
            return "".join(parts)
        return str(content)

    # --- JSON parsing -------------------------------------------------------
    @staticmethod
    def parse_json(text: str) -> Any:
        """Parse JSON from a raw LLM response, tolerating common wrappers.

        Strategy, in order: strip markdown code fences and parse; parse the raw
        text; extract the outermost ``[...]`` array; extract the outermost
        ``{...}`` object. Raises :class:`ValueError` if none succeed so callers
        can record a failed step rather than crash the graph.
        """
        cleaned = text.strip()

        # Strip a leading/trailing markdown code fence (```json ... ```).
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z0-9]*\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned).strip()

        for candidate in (cleaned, _slice(cleaned, "[", "]"), _slice(cleaned, "{", "}")):
            if candidate is None:
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

        raise ValueError("Could not parse JSON from LLM response")

    @classmethod
    def parse_json_array(cls, text: str) -> list[dict]:
        """Parse and coerce an LLM response into a list of dicts.

        A bare object is wrapped into a single-element list; anything that is
        not a list of objects yields an empty list.
        """
        parsed = cls.parse_json(text)
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, dict)]

    # --- Trace --------------------------------------------------------------
    def _record_step(
        self,
        status: str,
        input_summary: str,
        output_summary: str,
        confidence: float,
        start_time: float,
    ) -> AgentStep:
        """Build a trace step for this agent, timing from ``start_time``."""
        return AgentStep(
            agent=self.name,
            status=status,
            input_summary=input_summary,
            output_summary=output_summary,
            confidence=confidence,
            duration_ms=int((time.time() - start_time) * 1000),
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def run(self, state: CounselIQState) -> dict:
        """Execute the agent and return a partial state update."""
        raise NotImplementedError


def _slice(text: str, open_ch: str, close_ch: str) -> str | None:
    """Return the substring from the first ``open_ch`` to the last ``close_ch``."""
    start = text.find(open_ch)
    end = text.rfind(close_ch)
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return None
