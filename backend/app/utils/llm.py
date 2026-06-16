"""LLM factory — the single place that constructs provider clients.

Primary provider is Anthropic Claude; Groq Llama is the fallback. Selection is
driven by configuration (:attr:`Settings.active_llm_provider`) so callers never
reference a model name or provider directly — they call :func:`get_llm`.
"""

from __future__ import annotations

import logging

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq

from app.config import settings

logger = logging.getLogger("counseliq.llm")

# Model identifiers are defined here and nowhere else.
ANTHROPIC_MODEL = "claude-sonnet-4-6"
GROQ_MODEL = "llama-3.3-70b-versatile"


def get_llm(max_tokens: int = 4096) -> BaseChatModel:
    """Return the configured LangChain chat model.

    Primary: Anthropic Claude. Fallback: Groq Llama. The provider is resolved
    from configuration; an explicit ``LLM_PROVIDER`` whose key is missing is a
    configuration error and raises :class:`RuntimeError`.
    """
    provider = settings.active_llm_provider

    if provider == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not set but LLM_PROVIDER=anthropic")
        logger.info("Using LLM provider: Anthropic (%s)", ANTHROPIC_MODEL)
        return ChatAnthropic(
            model=ANTHROPIC_MODEL,
            anthropic_api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=max_tokens,
        )

    if provider == "groq":
        if not settings.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY not set but LLM_PROVIDER=groq")
        logger.info("Using LLM provider: Groq (%s)", GROQ_MODEL)
        return ChatGroq(
            model=GROQ_MODEL,
            groq_api_key=settings.GROQ_API_KEY,
            max_tokens=max_tokens,
        )

    raise RuntimeError(f"Unknown LLM provider: {provider}")
