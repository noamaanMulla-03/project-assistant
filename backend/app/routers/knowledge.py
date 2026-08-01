# ── Knowledge Router ──────────────────────────────────────────────────────────
# Endpoints for uploading, listing, downloading, and deleting knowledge-base
# documents.  All endpoints require authentication — the knowledge base is
# universal (shared across all user accounts).

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models.knowledge import KnowledgeDocument
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.knowledge import (
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# ── Helpers ───────────────────────────────────────────────────────────────────


def _validate_extension(filename: str) -> str:
    """Return the lowercase extension if allowed, otherwise raise 400."""
    ext = Path(filename).suffix.lower()
    if ext not in settings.allowed_upload_extensions_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"File type '{ext}' is not allowed. "
                f"Accepted: {', '.join(sorted(settings.allowed_upload_extensions_set))}"
            ),
        )
    return ext


def _resolve_upload_path() -> Path:
    """Return the absolute upload directory, creating it if needed."""
    path = Path(settings.UPLOAD_DIR).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


async def _count_documents(db: AsyncSession) -> int:
    """Return total number of documents in the knowledge base."""
    result = await db.execute(select(func.count(KnowledgeDocument.id)))
    return result.scalar_one()


# ═══════════════════════════════════════════════════════════════════════════════
#  POST /knowledge/upload
# ═══════════════════════════════════════════════════════════════════════════════


@router.post(
    "/upload",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document to the knowledge base",
)
async def upload_document(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept a multipart file upload and store it on disk.

    Only ``.pdf``, ``.docx``, and ``.txt`` extensions are allowed.
    The file is saved with a UUID-based name to prevent collisions;
    the original filename is preserved in the database.
    """
    # Validate filename and extension
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided.",
        )

    ext = _validate_extension(file.filename)

    # Read the file content into memory (async)
    content = await file.read()

    # Enforce max upload size
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )

    # Write to disk with a UUID-safe name
    upload_dir = _resolve_upload_path()
    stored_name = f"{uuid.uuid4().hex}{ext}"
    disk_path = upload_dir / stored_name
    disk_path.write_bytes(content)

    # Persist metadata
    doc = KnowledgeDocument(
        filename=file.filename,
        file_type=ext.lstrip("."),  # store "pdf" not ".pdf"
        file_path=stored_name,  # relative to UPLOAD_DIR
        file_size=len(content),
        uploaded_by=current_user.id,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    # Build response (uploader relationship is eager-loaded via `joined`)
    return _doc_to_response(doc)


# ═══════════════════════════════════════════════════════════════════════════════
#  GET /knowledge/documents
# ═══════════════════════════════════════════════════════════════════════════════


@router.get(
    "/documents",
    response_model=KnowledgeDocumentListResponse,
    summary="List all documents in the knowledge base",
)
async def list_documents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 50,
):
    """Return a paginated list of knowledge-base documents, newest first.

    The knowledge base is universal — all authenticated users see all documents.
    """
    total = await _count_documents(db)

    result = await db.execute(
        select(KnowledgeDocument)
        .order_by(KnowledgeDocument.created_at.desc())
        .offset(skip)
        .limit(limit),
    )
    docs = result.scalars().all()

    return KnowledgeDocumentListResponse(
        documents=[_doc_to_response(d) for d in docs],
        total=total,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  GET /knowledge/documents/{document_id}
# ═══════════════════════════════════════════════════════════════════════════════


@router.get(
    "/documents/{document_id}",
    summary="Download a document from the knowledge base",
)
async def download_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the raw file for download."""
    doc = await _get_doc_or_404(db, document_id)

    disk_path = _resolve_upload_path() / doc.file_path
    if not disk_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk — it may have been removed.",
        )

    return FileResponse(
        path=str(disk_path),
        filename=doc.filename,
        media_type="application/octet-stream",
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  DELETE /knowledge/documents/{document_id}
# ═══════════════════════════════════════════════════════════════════════════════


@router.delete(
    "/documents/{document_id}",
    response_model=MessageResponse,
    summary="Delete a document from the knowledge base",
)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a document's metadata and its file from disk."""
    doc = await _get_doc_or_404(db, document_id)

    # Remove file from disk (best-effort — log but don't fail if missing)
    disk_path = _resolve_upload_path() / doc.file_path
    try:
        disk_path.unlink(missing_ok=True)
    except OSError:
        pass  # Log would go here in production

    await db.delete(doc)
    return MessageResponse(message=f"Document '{doc.filename}' deleted.")


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_doc_or_404(
    db: AsyncSession, document_id: uuid.UUID
) -> KnowledgeDocument:
    """Fetch a KnowledgeDocument by ID or raise 404."""
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    return doc


def _doc_to_response(doc: KnowledgeDocument) -> KnowledgeDocumentResponse:
    """Map an ORM instance to the Pydantic response schema."""
    return KnowledgeDocumentResponse(
        id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        uploaded_by=doc.uploaded_by,
        uploaded_by_name=doc.uploader.full_name if doc.uploader else None,
        created_at=doc.created_at,
    )
