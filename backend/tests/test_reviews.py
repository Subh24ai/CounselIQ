"""Tests for the human review gate.

Analysis jobs that are ``awaiting_review`` (with risk flags) cannot be produced
through the API, so the fixture seeds them directly on the *same* DB connection
the API client uses (via savepoint sessions), keeping everything inside one
rolled-back transaction.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db.session import get_db
from app.main import app
from app.models import AnalysisJob, Document, Organisation, RiskFlag, User
from app.utils.security import create_access_token, hash_password

API = "/api/v1"


@pytest_asyncio.fixture
async def review_env(db_engine: AsyncEngine) -> AsyncIterator[SimpleNamespace]:
    """Seed an org with reviewers + an awaiting_review job and yield a client.

    Provides:
      - ``client``: AsyncClient sharing the seeded connection
      - ``ids``: seeded primary keys
      - ``headers`` for admin / counsel / viewer
    """
    connection = await db_engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    async def _override_get_db() -> AsyncIterator:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    suffix = uuid.uuid4().hex[:8]
    async with factory() as s:
        org = Organisation(name=f"Rev Org {suffix}", domain=f"rev-{suffix}.example")
        s.add(org)
        await s.flush()

        admin = User(
            organisation_id=org.id,
            email=f"admin-{suffix}@example.com",
            hashed_password=hash_password("x"),
            role="org_admin",
            is_active=True,
        )
        counsel = User(
            organisation_id=org.id,
            email=f"counsel-{suffix}@example.com",
            hashed_password=hash_password("x"),
            role="legal_counsel",
            is_active=True,
        )
        viewer = User(
            organisation_id=org.id,
            email=f"viewer-{suffix}@example.com",
            hashed_password=hash_password("x"),
            role="viewer",
            is_active=True,
        )
        s.add_all([admin, counsel, viewer])
        await s.flush()

        doc = Document(
            organisation_id=org.id,
            uploaded_by=admin.id,
            name="Reviewed Contract",
            s3_key=f"{org.id}/{suffix}/contract.pdf",
            status="completed",
            document_type="vendor_contract",
        )
        s.add(doc)
        await s.flush()

        job = AnalysisJob(
            document_id=doc.id,
            organisation_id=org.id,
            initiated_by=admin.id,
            status="awaiting_review",
            job_type="contract_review",
            agent_trace=[],
        )
        pending_job = AnalysisJob(
            document_id=doc.id,
            organisation_id=org.id,
            initiated_by=admin.id,
            status="pending",
            job_type="contract_review",
            agent_trace=[],
        )
        s.add_all([job, pending_job])
        await s.flush()

        critical_flag = RiskFlag(
            analysis_job_id=job.id,
            category="indemnity",
            severity="critical",
            title="Unlimited indemnity exposure",
            status="open",
            confidence_score=0.9,
        )
        high_flag = RiskFlag(
            analysis_job_id=job.id,
            category="liability_cap",
            severity="high",
            title="No liability cap",
            status="open",
            confidence_score=0.8,
        )
        s.add_all([critical_flag, high_flag])
        await s.flush()

        ids = SimpleNamespace(
            org_id=org.id,
            job_id=job.id,
            pending_job_id=pending_job.id,
            critical_flag_id=critical_flag.id,
            high_flag_id=high_flag.id,
            admin_id=admin.id,
            counsel_id=counsel.id,
            viewer_id=viewer.id,
        )
        await s.commit()

    headers = {
        "admin": {"Authorization": f"Bearer {create_access_token({'sub': str(ids.admin_id)})}"},
        "counsel": {"Authorization": f"Bearer {create_access_token({'sub': str(ids.counsel_id)})}"},
        "viewer": {"Authorization": f"Bearer {create_access_token({'sub': str(ids.viewer_id)})}"},
    }

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield SimpleNamespace(client=ac, ids=ids, headers=headers)
    finally:
        app.dependency_overrides.pop(get_db, None)
        await transaction.rollback()
        await connection.close()


async def _start(env: SimpleNamespace, role: str = "counsel"):
    return await env.client.post(
        f"{API}/reviews/jobs/{env.ids.job_id}/start", headers=env.headers[role]
    )


@pytest.mark.asyncio
async def test_start_review(review_env: SimpleNamespace) -> None:
    resp = await _start(review_env)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["review_id"]
    assert body["status"] == "in_progress"
    assert body["analysis_job_id"] == str(review_env.ids.job_id)


@pytest.mark.asyncio
async def test_start_review_wrong_status(review_env: SimpleNamespace) -> None:
    resp = await review_env.client.post(
        f"{API}/reviews/jobs/{review_env.ids.pending_job_id}/start",
        headers=review_env.headers["counsel"],
    )
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_start_review_duplicate(review_env: SimpleNamespace) -> None:
    first = await _start(review_env)
    assert first.status_code == 201, first.text
    second = await _start(review_env)
    assert second.status_code == 409, second.text
    assert "already" in second.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_flag_status(review_env: SimpleNamespace) -> None:
    await _start(review_env)
    resp = await review_env.client.patch(
        f"{API}/reviews/flags/{review_env.ids.high_flag_id}",
        headers=review_env.headers["counsel"],
        json={"status": "accepted", "notes": "Acceptable with the agreed cap."},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_submit_review_blocked_by_critical(review_env: SimpleNamespace) -> None:
    await _start(review_env)
    resp = await review_env.client.post(
        f"{API}/reviews/jobs/{review_env.ids.job_id}/submit",
        headers=review_env.headers["counsel"],
        json={"status": "approved", "notes": "LGTM"},
    )
    assert resp.status_code == 422, resp.text
    assert "critical" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_submit_review_approved(review_env: SimpleNamespace) -> None:
    await _start(review_env)
    # Resolve both flags so no critical flag remains open.
    for flag_id in (review_env.ids.critical_flag_id, review_env.ids.high_flag_id):
        patch = await review_env.client.patch(
            f"{API}/reviews/flags/{flag_id}",
            headers=review_env.headers["counsel"],
            json={"status": "accepted"},
        )
        assert patch.status_code == 200, patch.text

    resp = await review_env.client.post(
        f"{API}/reviews/jobs/{review_env.ids.job_id}/submit",
        headers=review_env.headers["counsel"],
        json={"status": "approved", "notes": "Approved after review."},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"

    # The analysis job must now be completed.
    job_resp = await review_env.client.get(
        f"{API}/analysis/jobs/{review_env.ids.job_id}",
        headers=review_env.headers["counsel"],
    )
    assert job_resp.status_code == 200, job_resp.text
    assert job_resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_viewer_cannot_start_review(review_env: SimpleNamespace) -> None:
    resp = await _start(review_env, role="viewer")
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_review_summary(review_env: SimpleNamespace) -> None:
    resp = await review_env.client.get(
        f"{API}/reviews/jobs/{review_env.ids.job_id}/summary",
        headers=review_env.headers["counsel"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_flags"] == 2
    assert body["critical_open"] == 1
    assert body["open"] == 2
