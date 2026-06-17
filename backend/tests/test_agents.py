"""Tests for the LangGraph analysis agents, orchestrator, and API.

Every LLM call is mocked — no real Anthropic API is contacted. Agent unit tests
(1-7) run without a database; the API test (8) uses the rolled-back
``api_client`` transaction and mocks S3 and the Celery enqueue.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import base as base_module
from app.agents.drafter import DrafterAgent
from app.agents.extractor import ExtractorAgent
from app.agents.orchestrator import build_initial_state, counseliq_graph
from app.agents.researcher import ResearcherAgent
from app.agents.risk_scorer import RiskScorerAgent
from app.agents.state import CounselIQState
from app.agents.synthesiser import SynthesiserAgent
from app.models import Document

API = "/api/v1"


@contextmanager
def mock_llm(content: str) -> Iterator[MagicMock]:
    """Patch the ``get_llm`` factory so any agent constructed returns ``content``.

    The factory yields a client whose ``ainvoke`` is an AsyncMock returning an
    object with a ``.content`` attribute, mirroring a LangChain ``AIMessage``.
    This is provider-agnostic — it does not matter whether Anthropic or Groq is
    configured.
    """
    instance = MagicMock()
    instance.ainvoke = AsyncMock(return_value=SimpleNamespace(content=content))
    with patch.object(base_module, "get_llm", MagicMock(return_value=instance)):
        yield instance


def _base_state(**overrides) -> CounselIQState:
    state = build_initial_state(
        document_id=str(uuid.uuid4()),
        organisation_id=str(uuid.uuid4()),
        analysis_job_id=str(uuid.uuid4()),
        job_type="contract_review",
        document_text="This Agreement is made between ACME and BETA.",
        document_name="Test MSA",
    )
    state.update(overrides)
    return state


# --- LLM provider factory ---------------------------------------------------
def test_llm_factory_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    """auto mode with only a Groq key selects ChatGroq."""
    from langchain_groq import ChatGroq

    from app.utils import llm as llm_module

    monkeypatch.setattr(llm_module.settings, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(llm_module.settings, "GROQ_API_KEY", "test")
    monkeypatch.setattr(llm_module.settings, "LLM_PROVIDER", "auto")

    assert isinstance(llm_module.get_llm(), ChatGroq)


def test_llm_factory_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    """auto mode prefers Anthropic when its key is present (even if Groq is too)."""
    from langchain_anthropic import ChatAnthropic

    from app.utils import llm as llm_module

    monkeypatch.setattr(llm_module.settings, "ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(llm_module.settings, "GROQ_API_KEY", "test")
    monkeypatch.setattr(llm_module.settings, "LLM_PROVIDER", "auto")

    assert isinstance(llm_module.get_llm(), ChatAnthropic)


def test_llm_factory_no_keys() -> None:
    """The config validator fails fast at startup when no LLM key is set."""
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError, match="At least one LLM key required"):
        Settings(_env_file=None, ANTHROPIC_API_KEY=None, GROQ_API_KEY=None)


# --- 1. Extractor: valid JSON ------------------------------------------------
async def test_extractor_parses_clauses() -> None:
    payload = (
        '[{"clause_type": "indemnity", "content": "Party A shall indemnify Party B.",'
        ' "page_number": 2, "key_entities": ["Party A", "Party B"],'
        ' "risk_indicators": ["unlimited"]},'
        '{"clause_type": "termination", "content": "Either party may terminate.",'
        ' "page_number": null, "key_entities": [], "risk_indicators": []}]'
    )
    with mock_llm(payload):
        result = await ExtractorAgent().run(_base_state())

    assert result.get("error") is None
    assert len(result["clauses"]) == 2
    assert result["clauses"][0]["clause_type"] == "indemnity"
    assert result["clauses"][0]["key_entities"] == ["Party A", "Party B"]
    assert result["steps"][0]["status"] == "completed"
    assert result["current_agent"] == "extractor"


# --- 2. Extractor: malformed JSON -------------------------------------------
async def test_extractor_handles_bad_json() -> None:
    with mock_llm("Sorry, I cannot produce JSON here. <<< broken"):
        result = await ExtractorAgent().run(_base_state())

    assert result["clauses"] == []
    assert result["error"] is not None
    assert result["steps"][0]["status"] == "failed"


# --- 3. Risk scorer: score computation --------------------------------------
async def test_risk_scorer_computes_score() -> None:
    clauses = [{"clause_type": "indemnity", "content": "Unlimited indemnity clause."}]
    # indemnity weight=0.20, high severity multiplier=0.7, confidence=1.0
    # => 0.20 * 0.7 * 1.0 * 100 = 14.0
    flags_json = (
        '[{"clause_index": 0, "category": "indemnity", "severity": "high",'
        ' "title": "Unlimited indemnity", "description": "Risky.",'
        ' "suggested_action": "Cap it.", "agent_reasoning": "Because.",'
        ' "cited_regulation": null, "confidence_score": 1.0}]'
    )
    with mock_llm(flags_json):
        result = await RiskScorerAgent().run(_base_state(clauses=clauses))

    assert 0.0 <= result["overall_risk_score"] <= 100.0
    assert result["overall_risk_score"] == pytest.approx(14.0)
    assert len(result["risk_flags"]) == 1
    assert result["steps"][0]["status"] == "completed"


# --- 4. Risk scorer: escalation on critical ---------------------------------
async def test_risk_scorer_sets_escalate() -> None:
    clauses = [{"clause_type": "liability", "content": "No liability cap whatsoever."}]
    flags_json = (
        '[{"clause_index": 0, "category": "liability_cap", "severity": "critical",'
        ' "title": "Uncapped liability", "description": "Critical.",'
        ' "suggested_action": "Add a cap.", "agent_reasoning": "Unbounded exposure.",'
        ' "cited_regulation": null, "confidence_score": 0.9}]'
    )
    with mock_llm(flags_json):
        result = await RiskScorerAgent().run(_base_state(clauses=clauses))

    assert result["should_escalate"] is True
    assert any(flag["severity"] == "critical" for flag in result["risk_flags"])


# --- 5. Researcher: skips when no flags -------------------------------------
async def test_researcher_skips_if_no_flags() -> None:
    # No LLM should be called; patch it to blow up if it is.
    with mock_llm("SHOULD NOT BE CALLED") as llm:
        result = await ResearcherAgent().run(_base_state(risk_flags=[]))

    assert result["research_findings"] == []
    assert result["steps"][0]["status"] == "skipped"
    llm.ainvoke.assert_not_called()


# --- 6. Drafter: skips when nothing high-risk -------------------------------
async def test_drafter_skips_if_no_high_risk() -> None:
    flags = [
        {"clause_index": 0, "severity": "low", "title": "Minor"},
        {"clause_index": 1, "severity": "medium", "title": "Moderate"},
    ]
    with mock_llm("SHOULD NOT BE CALLED") as llm:
        result = await DrafterAgent().run(_base_state(risk_flags=flags))

    assert result["drafted_alternatives"] == []
    assert result["steps"][0]["status"] == "skipped"
    llm.ainvoke.assert_not_called()


# --- 7. Full graph: end-to-end with all agents mocked -----------------------
async def test_full_graph_runs() -> None:
    extractor_update = {
        "clauses": [{"clause_type": "indemnity", "content": "Indemnity clause."}],
        "steps": [_step("extractor", "completed")],
        "current_agent": "extractor",
    }
    risk_update = {
        "risk_flags": [
            {
                "clause_index": 0,
                "category": "indemnity",
                "severity": "high",
                "title": "Unlimited indemnity",
                "confidence_score": 0.8,
            }
        ],
        "overall_risk_score": 42.0,
        "should_escalate": False,
        "steps": [_step("risk_scorer", "completed")],
        "current_agent": "risk_scorer",
    }
    research_update = {
        "research_findings": [{"regulation_name": "Indian Contract Act 1872"}],
        "steps": [_step("researcher", "completed")],
        "current_agent": "researcher",
    }
    drafter_update = {
        "drafted_alternatives": [{"clause_index": 0, "alternative_text": "Capped indemnity."}],
        "steps": [_step("drafter", "completed")],
        "current_agent": "drafter",
    }
    synth_update = {
        "summary_report": "EXECUTIVE SUMMARY: one high risk identified.",
        "steps": [_step("synthesiser", "completed")],
        "current_agent": "synthesiser",
    }

    with (
        patch.object(base_module, "get_llm", MagicMock(return_value=MagicMock())),
        patch.object(ExtractorAgent, "run", AsyncMock(return_value=extractor_update)),
        patch.object(RiskScorerAgent, "run", AsyncMock(return_value=risk_update)),
        patch.object(ResearcherAgent, "run", AsyncMock(return_value=research_update)),
        patch.object(DrafterAgent, "run", AsyncMock(return_value=drafter_update)) as drafter_run,
        patch.object(SynthesiserAgent, "run", AsyncMock(return_value=synth_update)),
    ):
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        final_state = await counseliq_graph.ainvoke(_base_state(), config=config)

    assert final_state["summary_report"] == "EXECUTIVE SUMMARY: one high risk identified."
    assert final_state["overall_risk_score"] == 42.0
    # The high-risk flag must have routed through the drafter.
    drafter_run.assert_awaited_once()
    assert final_state["drafted_alternatives"]
    # Every agent contributed a step (append-only reducer).
    agents_seen = {step["agent"] for step in final_state["steps"]}
    assert {"extractor", "risk_scorer", "researcher", "drafter", "synthesiser"} <= agents_seen


def _step(agent: str, status: str) -> dict:
    return {
        "agent": agent,
        "status": status,
        "input_summary": "",
        "output_summary": "",
        "confidence": 1.0,
        "duration_ms": 1,
        "timestamp": "2026-06-16T00:00:00+00:00",
    }


# --- 8. API: create analysis job --------------------------------------------
@dataclass
class _ApiMocks:
    upload_file: AsyncMock
    extract_enqueue: MagicMock
    analysis_enqueue: MagicMock


@pytest_asyncio.fixture
async def api_mocks() -> AsyncIterator[_ApiMocks]:
    """Mock S3 upload and both Celery enqueues used by the upload+analysis flow."""
    from app.api.v1 import analysis as analysis_module
    from app.api.v1 import documents as documents_module

    upload = AsyncMock(side_effect=lambda b, key, ct: key)
    extract_enqueue = MagicMock()
    analysis_enqueue = MagicMock()

    with (
        patch.object(documents_module.s3_service, "upload_file", upload),
        patch.object(documents_module.extract_document_task, "delay", extract_enqueue),
        patch.object(analysis_module.run_analysis_task, "delay", analysis_enqueue),
    ):
        yield _ApiMocks(upload, extract_enqueue, analysis_enqueue)


async def _register(client: AsyncClient) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    resp = await client.post(
        f"{API}/auth/register",
        json={
            "organisation_name": f"Org {suffix}",
            "domain": f"{suffix}.example",
            "email": f"admin-{suffix}@example.com",
            "password": "supersecret123",
            "full_name": "Admin User",
        },
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _upload_document(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        f"{API}/documents/upload",
        headers=headers,
        files={"file": ("contract.pdf", b"%PDF-1.4 fake\n%%EOF", "application/pdf")},
        data={"name": "Test Contract", "document_type": "vendor_contract"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "queued"  # freshly uploaded, pending extraction
    return body["id"]


async def _mark_extracted(session: AsyncSession, document_id: str) -> None:
    """Simulate the extraction task completing: flip the document to ``extracted``.

    The real Celery task is mocked in these tests, so a document never leaves
    ``queued`` on its own; analysis requires the post-extraction ``extracted``
    state.
    """
    document = await session.get(Document, uuid.UUID(document_id))
    assert document is not None
    document.status = "extracted"
    await session.commit()


@pytest.mark.asyncio
async def test_analysis_job_created(
    api_client: AsyncClient, api_session: AsyncSession, api_mocks: _ApiMocks
) -> None:
    headers = await _register(api_client)
    document_id = await _upload_document(api_client, headers)
    # Analysis is only permitted once extraction has completed.
    await _mark_extracted(api_session, document_id)

    resp = await api_client.post(
        f"{API}/analysis/jobs",
        headers=headers,
        json={"document_id": document_id, "job_type": "contract_review"},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["job_type"] == "contract_review"
    assert body["document_id"] == document_id
    assert body["agent_trace"] == []

    # The analysis task must be enqueued exactly once with the new job id.
    api_mocks.analysis_enqueue.assert_called_once_with(body["id"])


@pytest.mark.asyncio
async def test_analysis_job_rejects_unready_document(
    api_client: AsyncClient, api_mocks: _ApiMocks
) -> None:
    """A job cannot be created for a document that has not been extracted."""
    headers = await _register(api_client)
    resp = await api_client.post(
        f"{API}/analysis/jobs",
        headers=headers,
        json={"document_id": str(uuid.uuid4()), "job_type": "contract_review"},
    )
    assert resp.status_code == 404
    api_mocks.analysis_enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_analysis_job_rejects_queued_document(
    api_client: AsyncClient, api_mocks: _ApiMocks
) -> None:
    """A freshly uploaded (``queued``) document cannot be analysed yet.

    Regression guard for the lifecycle bug: ``queued`` is the pre-extraction
    state, so analysis must wait for extraction to finish (``extracted``).
    """
    headers = await _register(api_client)
    document_id = await _upload_document(api_client, headers)

    resp = await api_client.post(
        f"{API}/analysis/jobs",
        headers=headers,
        json={"document_id": document_id, "job_type": "contract_review"},
    )
    assert resp.status_code == 409, resp.text
    api_mocks.analysis_enqueue.assert_not_called()
