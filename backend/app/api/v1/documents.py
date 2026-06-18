"""Documents router: upload, list, retrieve, status polling, and delete.

Every endpoint requires authentication and is scoped to the caller's
organisation. Uploaded files are stored in S3 under an org-prefixed key and an
extraction task is enqueued asynchronously.
"""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.middleware.rate_limit import limiter
from app.models import Document, User
from app.schemas.document import (
    DocumentListResponse,
    DocumentResponse,
    DocumentStatusResponse,
)
from app.services.audit import write_audit_log
from app.services.storage import s3_service
from app.tasks.extraction import extract_document_task

logger = logging.getLogger("counseliq.api.documents")

router = APIRouter(prefix="/documents", tags=["documents"])

# Deletion is limited to admins and legal counsel.
require_document_deleter = require_roles("org_admin", "legal_counsel")

# Allowed upload types and the 50 MB size ceiling.
MIME_PDF = "application/pdf"
MIME_DOCX = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
MIME_TXT = "text/plain"
ALLOWED_MIME_TYPES = {MIME_PDF, MIME_DOCX, MIME_TXT}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

# Known binary signatures that must never pass as plain text.
_BINARY_SIGNATURES = (
    b"%PDF-",  # PDF
    b"PK\x03\x04",  # ZIP / OOXML (docx, xlsx, …)
    b"MZ",  # Windows PE executable
    b"\x7fELF",  # ELF executable
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG",  # PNG
)


def _content_matches_declared(content_type: str, data: bytes) -> bool:
    """Validate the file's real content against its declared MIME type.

    The client-supplied ``Content-Type`` is trivially spoofable, so we inspect
    the leading magic bytes. DOCX (and other OOXML) files are ZIP archives, so a
    ZIP signature is the strongest cheap signal available without unzipping.
    """
    if content_type == MIME_PDF:
        return data[:5] == b"%PDF-"
    if content_type == MIME_DOCX:
        return data[:4] == b"PK\x03\x04"
    if content_type == MIME_TXT:
        # Plain text has no signature: reject anything that looks binary and
        # require the content to decode as UTF-8.
        if data.startswith(_BINARY_SIGNATURES) or b"\x00" in data[:8192]:
            return False
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True
    return False


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _get_org_document(
    db: AsyncSession, document_id: UUID, organisation_id: UUID
) -> Document:
    """Fetch a document within an organisation or raise 404."""
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.organisation_id == organisation_id,
        )
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return document


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    response: Response,  # required so slowapi can attach rate-limit headers
    file: UploadFile = File(...),
    name: str = Form(...),
    document_type: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Upload a document, store it in S3, and enqueue text extraction."""
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Unsupported file type. Allowed types: PDF, DOCX, TXT."
            ),
        )

    # Read once and validate size *before* uploading anything to S3.
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="File exceeds the 50MB maximum size.",
        )
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Uploaded file is empty.",
        )

    # Verify the actual file content matches its declared type — the
    # Content-Type header alone is spoofable (e.g. a .exe renamed to .pdf).
    if not _content_matches_declared(content_type, file_bytes):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "File content does not match its declared type. "
                "Upload a genuine PDF, DOCX, or TXT file."
            ),
        )

    document_id = uuid4()
    original_filename = file.filename or "document"
    # org_id prefix enforces per-tenant storage isolation in the bucket.
    s3_key = f"{current_user.organisation_id}/{document_id}/{original_filename}"

    await s3_service.upload_file(file_bytes, s3_key, content_type)

    document = Document(
        id=document_id,
        organisation_id=current_user.organisation_id,
        uploaded_by=current_user.id,
        name=name,
        original_filename=original_filename,
        s3_key=s3_key,
        s3_bucket=s3_service._bucket,
        file_size_bytes=len(file_bytes),
        mime_type=content_type,
        status="uploaded",
        document_type=document_type,
    )
    db.add(document)
    await db.flush()

    await write_audit_log(
        db,
        organisation_id=current_user.organisation_id,
        action="document.upload",
        user_id=current_user.id,
        resource_type="document",
        resource_id=document.id,
        payload={"name": name, "mime_type": content_type},
        ip_address=_client_ip(request),
    )

    # Hand off extraction to the worker and mark the document queued.
    document.status = "queued"

    await db.commit()
    await db.refresh(document)

    extract_document_task.delay(str(document.id))
    return document


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_deleted: bool = Query(False),
) -> DocumentListResponse:
    """List the organisation's documents, newest first (paginated).

    Soft-deleted documents (``status == "deleted"``) are excluded by default;
    pass ``include_deleted=true`` to include them.
    """
    base = select(Document).where(
        Document.organisation_id == current_user.organisation_id
    )
    if not include_deleted:
        base = base.where(Document.status != "deleted")

    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    )

    result = await db.execute(
        base.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    documents = result.scalars().all()

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(doc) for doc in documents],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Retrieve a single document with a freshly generated presigned URL."""
    document = await _get_org_document(
        db, document_id, current_user.organisation_id
    )
    response = DocumentResponse.model_validate(document)
    response.presigned_url = await s3_service.generate_presigned_url(
        document.s3_key
    )
    return response


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Lightweight status endpoint for the frontend to poll."""
    return await _get_org_document(
        db, document_id, current_user.organisation_id
    )


@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,
    request: Request,
    current_user: User = Depends(require_document_deleter),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete a document's S3 object and mark the record deleted (soft delete).

    ``status`` is set to the dedicated ``"deleted"`` sentinel rather than
    ``"failed"`` so soft-deleted rows stay distinguishable from genuine
    extraction/processing failures in the DB, UI, and audit/analytics queries.
    """
    document = await _get_org_document(
        db, document_id, current_user.organisation_id
    )

    await s3_service.delete_file(document.s3_key)
    document.status = "deleted"

    await write_audit_log(
        db,
        organisation_id=current_user.organisation_id,
        action="document.delete",
        user_id=current_user.id,
        resource_type="document",
        resource_id=document.id,
        ip_address=_client_ip(request),
    )

    await db.commit()
    return {"message": "Document deleted"}
