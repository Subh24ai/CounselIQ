"""Document request/response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentUploadRequest(BaseModel):
    """Metadata accompanying a document upload (sent as form fields)."""

    name: str = Field(min_length=1, max_length=512)
    document_type: str = Field(min_length=1, max_length=50)
    description: str | None = None


class DocumentResponse(BaseModel):
    """A document as returned by the API.

    ``presigned_url`` is populated only on single-document GET (never on list,
    and never persisted) and is generated fresh on each request.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    original_filename: str | None
    document_type: str
    status: str
    file_size_bytes: int | None
    page_count: int | None
    mime_type: str | None
    uploaded_by: UUID | None
    created_at: datetime
    presigned_url: str | None = None


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""

    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int


class DocumentStatusResponse(BaseModel):
    """Lightweight document-status payload for polling."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    textract_job_id: str | None
    page_count: int | None
    updated_at: datetime
