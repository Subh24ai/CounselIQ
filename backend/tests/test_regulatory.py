"""Tests for the Regulatory Monitor.

The real sentence-transformers model is never loaded here: ``generate_embedding``
is mocked to return a fixed 384-dim vector. Impact matching is exercised by
seeding a clause whose embedding equals that vector (cosine distance ~0).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db.session import get_db
from app.main import app
from app.models import Clause, Document, Organisation, User
from app.services import regulatory as regulatory_service
from app.utils.security import create_access_token, hash_password

API = "/api/v1"

# A deterministic, non-zero 384-dim vector. cosine_distance(v, v) == 0, so a
# clause seeded with this vector matches an update embedded with it.
FIXED_VECTOR = [float((i % 7) + 1) for i in range(384)]


@pytest.fixture(autouse=True)
def mock_embeddings() -> AsyncIterator[AsyncMock]:
    """Patch the embedding service so the real model never loads."""
    mock = AsyncMock(return_value=list(FIXED_VECTOR))
    with patch.object(
        regulatory_service.embedding_service, "generate_embedding", mock
    ):
        yield mock


@pytest_asyncio.fixture
async def reg_env(db_engine: AsyncEngine) -> AsyncIterator[SimpleNamespace]:
    """Seed an org with admin/compliance/viewer + a document; yield a client.

    ``factory`` is exposed so tests can seed clauses on the same connection.
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
        org = Organisation(name=f"Reg Org {suffix}", domain=f"reg-{suffix}.example")
        s.add(org)
        await s.flush()

        admin = User(
            organisation_id=org.id,
            email=f"admin-{suffix}@example.com",
            hashed_password=hash_password("x"),
            role="org_admin",
            is_active=True,
        )
        compliance = User(
            organisation_id=org.id,
            email=f"comp-{suffix}@example.com",
            hashed_password=hash_password("x"),
            role="compliance_officer",
            is_active=True,
        )
        viewer = User(
            organisation_id=org.id,
            email=f"viewer-{suffix}@example.com",
            hashed_password=hash_password("x"),
            role="viewer",
            is_active=True,
        )
        s.add_all([admin, compliance, viewer])
        await s.flush()

        doc = Document(
            organisation_id=org.id,
            uploaded_by=admin.id,
            name="Data Processing Agreement",
            s3_key=f"{org.id}/{suffix}/dpa.pdf",
            status="completed",
            document_type="vendor_contract",
        )
        s.add(doc)
        await s.flush()

        ids = SimpleNamespace(org_id=org.id, doc_id=doc.id)
        await s.commit()

    headers = {
        role: {"Authorization": f"Bearer {create_access_token({'sub': str(uid)})}"}
        for role, uid in (
            ("admin", admin.id),
            ("compliance", compliance.id),
            ("viewer", viewer.id),
        )
    }

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield SimpleNamespace(
                client=ac, ids=ids, headers=headers, factory=factory
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        await transaction.rollback()
        await connection.close()


def _payload(**overrides: object) -> dict:
    body = {
        "source": "other",
        "title": "DPDP Act 2023 — data protection obligations",
        "summary": "Consent, notice, breach notification and security safeguards.",
        "published_date": "2023-08-11",
    }
    body.update(overrides)
    return body


async def _create_update(env: SimpleNamespace, role: str = "compliance") -> dict:
    resp = await env.client.post(
        f"{API}/regulatory/updates", headers=env.headers[role], json=_payload()
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_create_regulatory_update(
    reg_env: SimpleNamespace, mock_embeddings: AsyncMock
) -> None:
    body = await _create_update(reg_env)
    assert body["source"] == "other"
    assert body["is_processed"] is False
    assert body["id"]
    # The title+summary were embedded exactly once.
    mock_embeddings.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_regulatory_updates(reg_env: SimpleNamespace) -> None:
    # Regulatory updates are global (not tenant-scoped), and the dev DB may
    # already hold seeded rows — assert on the delta, not an absolute total.
    baseline = (
        await reg_env.client.get(
            f"{API}/regulatory/updates", headers=reg_env.headers["viewer"]
        )
    ).json()["total"]

    for i in range(3):
        resp = await reg_env.client.post(
            f"{API}/regulatory/updates",
            headers=reg_env.headers["compliance"],
            json=_payload(title=f"Update {i}"),
        )
        assert resp.status_code == 201, resp.text

    resp = await reg_env.client.get(
        f"{API}/regulatory/updates?page=1&page_size=2",
        headers=reg_env.headers["viewer"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == baseline + 3
    assert len(body["items"]) == 2  # page_size honoured
    assert body["page"] == 1


@pytest.mark.asyncio
async def test_get_impact_no_matches(reg_env: SimpleNamespace) -> None:
    update = await _create_update(reg_env)
    resp = await reg_env.client.get(
        f"{API}/regulatory/updates/{update['id']}/impact",
        headers=reg_env.headers["admin"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["regulatory_update"]["id"] == update["id"]
    assert body["affected_documents"] == []


@pytest.mark.asyncio
async def test_get_impact_with_matches(reg_env: SimpleNamespace) -> None:
    update = await _create_update(reg_env)

    # Seed a clause whose embedding equals the update's embedding.
    async with reg_env.factory() as s:
        s.add(
            Clause(
                document_id=reg_env.ids.doc_id,
                clause_type="data_protection",
                content="The processor shall implement appropriate security measures.",
                embedding=list(FIXED_VECTOR),
            )
        )
        await s.commit()

    resp = await reg_env.client.get(
        f"{API}/regulatory/updates/{update['id']}/impact",
        headers=reg_env.headers["admin"],
    )
    assert resp.status_code == 200, resp.text
    affected = resp.json()["affected_documents"]
    assert len(affected) == 1
    match = affected[0]
    assert match["document_id"] == str(reg_env.ids.doc_id)
    assert match["document_name"] == "Data Processing Agreement"
    assert match["similarity_score"] >= 0.99  # identical vectors -> ~1.0
    assert match["matched_clause_excerpt"].startswith("The processor shall")


@pytest.mark.asyncio
async def test_viewer_cannot_create_update(reg_env: SimpleNamespace) -> None:
    resp = await reg_env.client.post(
        f"{API}/regulatory/updates",
        headers=reg_env.headers["viewer"],
        json=_payload(),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_mark_processed(reg_env: SimpleNamespace) -> None:
    update = await _create_update(reg_env)
    assert update["is_processed"] is False

    resp = await reg_env.client.post(
        f"{API}/regulatory/updates/{update['id']}/mark-processed",
        headers=reg_env.headers["compliance"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_processed"] is True
