"""Tests for the document upload pipeline.

S3, Textract, and the Celery enqueue are mocked — no real AWS or broker is
contacted. Requests share one rolled-back DB transaction via ``api_client``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.api.v1 import documents as documents_module

API = "/api/v1"

PDF_CONTENT_TYPE = "application/pdf"
SMALL_PDF = b"%PDF-1.4 fake pdf body for testing\n%%EOF"


@dataclass
class AwsMocks:
    """Handles to the patched AWS/Celery callables for assertions."""

    upload_file: AsyncMock
    generate_presigned_url: AsyncMock
    delete_file: AsyncMock
    enqueue: MagicMock


@pytest_asyncio.fixture
async def aws_mocks() -> AsyncIterator[AwsMocks]:
    """Patch S3 service methods and the extraction task's ``delay``."""
    upload = AsyncMock(side_effect=lambda b, key, ct: key)
    presign = AsyncMock(return_value="https://s3.local/presigned-url")
    delete = AsyncMock(return_value=True)
    enqueue = MagicMock()

    with (
        patch.object(documents_module.s3_service, "upload_file", upload),
        patch.object(
            documents_module.s3_service, "generate_presigned_url", presign
        ),
        patch.object(documents_module.s3_service, "delete_file", delete),
        patch.object(documents_module.extract_document_task, "delay", enqueue),
    ):
        yield AwsMocks(upload, presign, delete, enqueue)


async def _register(client: AsyncClient) -> dict[str, str]:
    """Register an org + admin and return Authorization headers."""
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
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _upload(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    filename: str = "contract.pdf",
    content: bytes = SMALL_PDF,
    content_type: str = PDF_CONTENT_TYPE,
    name: str = "Test Contract",
    document_type: str = "vendor_contract",
):
    return await client.post(
        f"{API}/documents/upload",
        headers=headers,
        files={"file": (filename, content, content_type)},
        data={"name": name, "document_type": document_type},
    )


@pytest.mark.asyncio
async def test_upload_document(
    api_client: AsyncClient, aws_mocks: AwsMocks
) -> None:
    headers = await _register(api_client)
    resp = await _upload(api_client, headers)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["document_type"] == "vendor_contract"
    assert body["mime_type"] == PDF_CONTENT_TYPE

    # The s3_key must be generated and org-prefixed (storage isolation).
    aws_mocks.upload_file.assert_awaited_once()
    _, s3_key, _ = aws_mocks.upload_file.await_args.args
    assert s3_key.endswith("contract.pdf")
    assert s3_key.split("/")[0]  # leading organisation_id segment present

    # Extraction must be enqueued exactly once with the new document id.
    aws_mocks.enqueue.assert_called_once_with(body["id"])

    # extracted_text must never appear in API responses.
    assert "extracted_text" not in body


@pytest.mark.asyncio
async def test_upload_invalid_type(
    api_client: AsyncClient, aws_mocks: AwsMocks
) -> None:
    headers = await _register(api_client)
    resp = await _upload(
        api_client,
        headers,
        filename="malware.exe",
        content=b"MZ\x90\x00",
        content_type="application/x-msdownload",
    )
    assert resp.status_code == 422
    aws_mocks.upload_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_too_large(
    api_client: AsyncClient, aws_mocks: AwsMocks
) -> None:
    headers = await _register(api_client)
    # Patch the ceiling small so we exercise the size guard without allocating
    # 50MB in the test process.
    with patch.object(documents_module, "MAX_FILE_SIZE_BYTES", 16):
        resp = await _upload(
            api_client, headers, content=b"x" * 64, content_type=PDF_CONTENT_TYPE
        )
    assert resp.status_code == 422
    aws_mocks.upload_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_documents(
    api_client: AsyncClient, aws_mocks: AwsMocks
) -> None:
    headers = await _register(api_client)
    await _upload(api_client, headers, filename="a.pdf", name="Doc A")
    await _upload(api_client, headers, filename="b.pdf", name="Doc B")

    resp = await api_client.get(f"{API}/documents/", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert body["page"] == 1
    # List responses must not carry presigned URLs.
    assert all(item["presigned_url"] is None for item in body["items"])


@pytest.mark.asyncio
async def test_get_document_presigned_url(
    api_client: AsyncClient, aws_mocks: AwsMocks
) -> None:
    headers = await _register(api_client)
    doc_id = (await _upload(api_client, headers)).json()["id"]

    resp = await api_client.get(f"{API}/documents/{doc_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["presigned_url"] == "https://s3.local/presigned-url"
    aws_mocks.generate_presigned_url.assert_awaited_once()


@pytest.mark.asyncio
async def test_document_status_endpoint(
    api_client: AsyncClient, aws_mocks: AwsMocks
) -> None:
    headers = await _register(api_client)
    doc_id = (await _upload(api_client, headers)).json()["id"]

    resp = await api_client.get(
        f"{API}/documents/{doc_id}/status", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == doc_id
    assert body["status"] == "queued"


@pytest.mark.asyncio
async def test_cross_org_document_isolation(
    api_client: AsyncClient, aws_mocks: AwsMocks
) -> None:
    org1_headers = await _register(api_client)
    doc_id = (await _upload(api_client, org1_headers)).json()["id"]

    org2_headers = await _register(api_client)
    resp = await api_client.get(
        f"{API}/documents/{doc_id}", headers=org2_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_document(
    api_client: AsyncClient, aws_mocks: AwsMocks
) -> None:
    headers = await _register(api_client)
    doc_id = (await _upload(api_client, headers)).json()["id"]

    resp = await api_client.delete(f"{API}/documents/{doc_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["message"] == "Document deleted"
    aws_mocks.delete_file.assert_awaited_once()

    # Record is kept (soft delete) and status flips to the dedicated
    # "deleted" sentinel — never "failed", which is reserved for real failures.
    after = await api_client.get(f"{API}/documents/{doc_id}", headers=headers)
    assert after.status_code == 200
    assert after.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_list_documents_excludes_deleted(
    api_client: AsyncClient, aws_mocks: AwsMocks
) -> None:
    headers = await _register(api_client)
    await _upload(api_client, headers, filename="keep.pdf", name="Keep Me")
    doc_id = (
        await _upload(api_client, headers, filename="gone.pdf", name="Delete Me")
    ).json()["id"]

    resp = await api_client.delete(f"{API}/documents/{doc_id}", headers=headers)
    assert resp.status_code == 200, resp.text

    # Default list omits the soft-deleted document.
    listing = await api_client.get(f"{API}/documents/", headers=headers)
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] != doc_id

    # include_deleted=true brings it back.
    with_deleted = await api_client.get(
        f"{API}/documents/?include_deleted=true", headers=headers
    )
    assert with_deleted.status_code == 200, with_deleted.text
    body = with_deleted.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert any(item["id"] == doc_id for item in body["items"])
