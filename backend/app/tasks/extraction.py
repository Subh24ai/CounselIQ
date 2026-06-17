"""Celery task that extracts text from an uploaded document.

Runs on the ``extraction`` queue. Celery workers are synchronous, so this uses
a sync SQLAlchemy session and bridges to the async AWS service methods via
``asyncio.run``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Coroutine
from typing import Any

from sqlalchemy import select

from app.db.session import SyncSessionLocal
from app.models import Document
from app.services.storage import s3_service
from app.services.textract import TextractResult, textract_service
from app.tasks.celery_app import celery_app

logger = logging.getLogger("counseliq.tasks.extraction")

# Textract polling configuration.
_POLL_INTERVAL_SECONDS = 5
_POLL_TIMEOUT_SECONDS = 600  # 10 minutes

# Supported MIME types.
MIME_PDF = "application/pdf"
MIME_DOCX = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
MIME_TXT = "text/plain"


class UnsupportedFileType(Exception):
    """Raised when a document's MIME type cannot be extracted."""


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Execute an async coroutine to completion from sync Celery code."""
    return asyncio.run(coro)


def _extract_pdf(document: Document, session: Any) -> TextractResult:
    """Run an async Textract job for a PDF and poll until done or timeout."""
    bucket = document.s3_bucket or ""
    job_id = _run(textract_service.start_extraction(bucket, document.s3_key))
    document.textract_job_id = job_id
    session.commit()

    deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        result = _run(textract_service.get_extraction_result(job_id))
        if result is not None:
            return result
        time.sleep(_POLL_INTERVAL_SECONDS)

    raise TimeoutError(
        f"Textract job {job_id} did not finish within "
        f"{_POLL_TIMEOUT_SECONDS} seconds"
    )


def _extract_non_pdf(document: Document) -> TextractResult:
    """Download a DOCX/TXT file from S3 and extract it in-process."""
    file_bytes = _run(s3_service.get_file_bytes(document.s3_key))
    if document.mime_type == MIME_DOCX:
        return _run(textract_service.extract_docx(file_bytes))
    if document.mime_type == MIME_TXT:
        return _run(textract_service.extract_txt(file_bytes))
    raise UnsupportedFileType(f"Unsupported MIME type: {document.mime_type}")


@celery_app.task(
    name="app.tasks.extraction.extract_document_task",
    bind=True,
    queue="extraction",
)
def extract_document_task(self, document_id: str) -> dict[str, str]:
    """Extract text from a document and mark it ready for analysis.

    On success the document moves to ``extracted``; on any failure it moves to
    ``failed``. The function always commits and closes its session.
    """
    session = SyncSessionLocal()
    try:
        document = session.execute(
            select(Document).where(Document.id == document_id)
        ).scalar_one_or_none()

        if document is None:
            logger.error("Document %s not found for extraction", document_id)
            return {"document_id": document_id, "status": "not_found"}

        document.status = "extracting"
        session.commit()

        try:
            if document.mime_type == MIME_PDF:
                result = _extract_pdf(document, session)
            elif document.mime_type in (MIME_DOCX, MIME_TXT):
                result = _extract_non_pdf(document)
            else:
                raise UnsupportedFileType(
                    f"Unsupported MIME type: {document.mime_type}"
                )

            document.extracted_text = result.text
            document.page_count = result.page_count
            document.status = "extracted"
            session.commit()
            logger.info("Extraction complete for document %s", document_id)
            return {"document_id": document_id, "status": "extracted"}

        except Exception as exc:
            logger.exception(
                "Extraction failed for document %s: %s", document_id, exc
            )
            document.status = "failed"
            session.commit()
            return {"document_id": document_id, "status": "failed"}

    finally:
        session.close()
