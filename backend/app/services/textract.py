"""AWS Textract service for PDF text extraction, with DOCX/TXT fallbacks.

PDFs are processed with Textract's asynchronous text-detection API (start +
poll). DOCX and TXT files are extracted in-process since Textract does not
accept those formats. As with :mod:`app.services.storage`, blocking boto3 calls
run in worker threads so the async API stays non-blocking.
"""

from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass, field

from botocore.exceptions import ClientError
from docx import Document as DocxDocument

from app.services.storage import _build_client

logger = logging.getLogger("counseliq.textract")


@dataclass
class TextractResult:
    """Outcome of a text-extraction operation."""

    text: str
    page_count: int
    pages: list[str] = field(default_factory=list)


class TextractError(Exception):
    """Raised when a Textract job fails or cannot be processed."""


class TextractService:
    """Async wrapper around Textract plus local DOCX/TXT extractors."""

    def __init__(self) -> None:
        self._client = _build_client("textract")

    async def start_extraction(self, s3_bucket: str, s3_key: str) -> str:
        """Start an async Textract text-detection job for a PDF; return JobId."""
        try:
            response = await asyncio.to_thread(
                self._client.start_document_text_detection,
                DocumentLocation={
                    "S3Object": {"Bucket": s3_bucket, "Name": s3_key}
                },
            )
        except ClientError as exc:
            logger.error("Textract start failed for %s: %s", s3_key, exc)
            raise TextractError(f"Failed to start Textract for {s3_key}") from exc
        return response["JobId"]

    async def get_extraction_result(self, job_id: str) -> TextractResult | None:
        """Poll a Textract job.

        Returns ``None`` while the job is still running (caller retries), a
        :class:`TextractResult` once it has succeeded, and raises
        :class:`TextractError` if it failed.
        """
        try:
            response = await asyncio.to_thread(
                self._client.get_document_text_detection, JobId=job_id
            )
        except ClientError as exc:
            logger.error("Textract poll failed for job %s: %s", job_id, exc)
            raise TextractError(f"Failed to poll Textract job {job_id}") from exc

        job_status = response["JobStatus"]
        if job_status == "IN_PROGRESS":
            return None
        if job_status == "FAILED":
            message = response.get("StatusMessage", "Textract job failed")
            raise TextractError(message)

        # SUCCEEDED — gather every block across all result pages.
        blocks = list(response.get("Blocks", []))
        next_token = response.get("NextToken")
        while next_token:
            page = await asyncio.to_thread(
                self._client.get_document_text_detection,
                JobId=job_id,
                NextToken=next_token,
            )
            blocks.extend(page.get("Blocks", []))
            next_token = page.get("NextToken")

        return self._blocks_to_result(blocks, response)

    @staticmethod
    def _blocks_to_result(blocks: list[dict], response: dict) -> TextractResult:
        """Reconstruct page-aware text from Textract LINE blocks.

        LINE blocks (rather than WORD blocks) are used so that natural line
        breaks are preserved, producing far more readable text for downstream
        clause segmentation.
        """
        pages: dict[int, list[str]] = {}
        for block in blocks:
            if block.get("BlockType") != "LINE":
                continue
            page_number = block.get("Page", 1)
            pages.setdefault(page_number, []).append(block.get("Text", ""))

        ordered_pages = [
            "\n".join(pages[page]) for page in sorted(pages)
        ]
        text = "\n\n".join(ordered_pages)
        page_count = response.get("DocumentMetadata", {}).get("Pages") or len(
            ordered_pages
        )
        return TextractResult(text=text, page_count=page_count, pages=ordered_pages)

    async def extract_docx(self, file_bytes: bytes) -> TextractResult:
        """Extract text from a DOCX file using python-docx."""

        def _extract() -> TextractResult:
            document = DocxDocument(io.BytesIO(file_bytes))
            paragraphs = [p.text for p in document.paragraphs]
            text = "\n".join(paragraphs)
            # Rough page estimate: ~40 paragraphs per page, at least one page.
            page_count = max(1, len(paragraphs) // 40)
            return TextractResult(text=text, page_count=page_count, pages=[])

        return await asyncio.to_thread(_extract)

    async def extract_txt(self, file_bytes: bytes) -> TextractResult:
        """Extract text from a plain-text file."""
        text = file_bytes.decode("utf-8", errors="replace")
        return TextractResult(text=text, page_count=1, pages=[])


textract_service = TextractService()
