# ── Knowledge Router ──────────────────────────────────────────────────────────
# Endpoints for uploading, listing, downloading, deleting, and semantically
# searching knowledge-base documents.  All endpoints require authentication.
#
# Visibility model:
#   - "public"  → universal knowledge base, visible to all authenticated users
#   - "private" → project documents, visible only to the user who uploaded them

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.knowledge import DocumentChunk, KnowledgeDocument
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.knowledge import (
    DocumentRef,
    DocumentTextResponse,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from app.services.search import search_public_chunks
from app.services.uploads import save_upload, upload_dir
from app.services.vectorization import ingest_document

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# Map file_type to the correct MIME for inline browser rendering
_MIME_MAP: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}


def _mime_for_type(file_type: str) -> str:
    """Return the correct MIME type for a file type, defaulting to octet-stream."""
    return _MIME_MAP.get(file_type, "application/octet-stream")


async def _count_documents(db: AsyncSession) -> int:
    """Return total number of public knowledge-base documents."""
    result = await db.execute(
        select(func.count(KnowledgeDocument.id)).where(
            KnowledgeDocument.visibility == "public"
        )
    )
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
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept a multipart file upload, store it on disk, and trigger async ingestion.

    Only ``.pdf``, ``.docx``, and ``.txt`` extensions are allowed.
    The file is saved with a UUID-based name to prevent collisions;
    the original filename is preserved in the database.

    After the response is sent, a background task extracts text, chunks it,
    embeds the chunks, and stores them in pgvector.
    """
    doc = await save_upload(file, current_user.id, "public")
    try:
        db.add(doc)
        await db.flush()
        await db.refresh(doc)
        # Commit before the background task opens its own session.
        await db.commit()
    except BaseException:
        (upload_dir() / doc.file_path).unlink(missing_ok=True)
        raise

    background_tasks.add_task(
        ingest_document, doc.id, upload_dir() / doc.file_path, doc.file_type
    )

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

    Public docs are visible to all users; private docs only to the uploader.
    """
    total = await _count_documents(db)

    result = await db.execute(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.visibility == "public")
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
    doc = await _get_doc_or_404(db, document_id, current_user.id)

    disk_path = upload_dir() / doc.file_path
    if not disk_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk — it may have been removed.",
        )

    return FileResponse(
        path=str(disk_path),
        filename=doc.filename,
        media_type=_mime_for_type(doc.file_type),
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
    """Remove a document's metadata, file, and stored vector chunks."""
    doc = await _get_doc_or_404(db, document_id, current_user.id)
    if doc.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own documents.",
        )

    # Remove file from disk (best-effort — log but don't fail if missing)
    disk_path = upload_dir() / doc.file_path
    try:
        disk_path.unlink(missing_ok=True)
    except OSError:
        pass  # Log would go here in production

    await db.delete(doc)
    return MessageResponse(message=f"Document '{doc.filename}' deleted.")


# ═══════════════════════════════════════════════════════════════════════════════
#  POST /knowledge/documents/{document_id}/reingest
# ═══════════════════════════════════════════════════════════════════════════════


@router.post(
    "/documents/{document_id}/reingest",
    response_model=KnowledgeDocumentResponse,
    summary="Retry ingestion for a document that previously failed",
)
async def reingest_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-run the full ingestion pipeline for a document whose previous
    ingestion failed (status='error') or was cancelled.

    Deletes any stale chunks from the previous attempt, resets the status to
    'processing', and fires the ingestion
    pipeline in the background.  The frontend can poll GET /documents until
    the status changes to 'indexed' or 'error' again.
    """
    doc = await _get_doc_or_404(db, document_id, current_user.id)
    if doc.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only reingest your own documents.",
        )

    # Verify the source file still exists on disk
    disk_path = upload_dir() / doc.file_path
    if not disk_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source file not found on disk — re-upload the document instead.",
        )

    # Clear chunks from the previous attempt.
    await db.execute(
        delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )

    # ── Reset status and fire background ingestion ──
    doc.status = "processing"
    await db.flush()
    await db.commit()

    background_tasks.add_task(ingest_document, doc.id, disk_path, doc.file_type)

    return _doc_to_response(doc)


# ═══════════════════════════════════════════════════════════════════════════════
#  POST /knowledge/search
# ═══════════════════════════════════════════════════════════════════════════════


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Semantic search over the knowledge base",
)
async def search_knowledge(
    body: SearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search public document chunks by vector similarity in PostgreSQL.

    The query is embedded with the same model used during ingestion,
    then the top-k most similar chunks are returned with their scores
    and parent document metadata.
    """
    hits = await search_public_chunks(db, body.query, body.top_k)
    results = [
        SearchResult(
            chunk_id=chunk.id,
            content=chunk.content,
            score=score,
            metadata=chunk.metadata_json or {},
            document=DocumentRef(
                id=chunk.document.id,
                filename=chunk.document.filename,
                file_type=chunk.document.file_type,
            ),
        )
        for chunk, score in hits
    ]

    return SearchResponse(results=results, query=body.query, total=len(results))


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_doc_or_404(
    db: AsyncSession, document_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> KnowledgeDocument:
    """Fetch a KnowledgeDocument by ID or raise 404.

    When *user_id* is provided, also enforces visibility: the caller must
    be the uploader for private documents.
    """
    where_clause = KnowledgeDocument.id == document_id
    if user_id is not None:
        where_clause &= (KnowledgeDocument.visibility == "public") | (
            KnowledgeDocument.uploaded_by == user_id
        )
    result = await db.execute(select(KnowledgeDocument).where(where_clause))
    doc = result.scalar_one_or_none()
    if doc is None:
        detail = (
            "Document not found or you do not have permission to access it."
            if user_id is not None
            else "Document not found."
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )
    return doc


def _doc_to_response(doc: KnowledgeDocument) -> KnowledgeDocumentResponse:
    """Map an ORM instance to the Pydantic response schema."""
    return KnowledgeDocumentResponse(
        id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status=doc.status,
        visibility=doc.visibility,
        uploaded_by=doc.uploaded_by,
        uploaded_by_name=doc.uploader.full_name if doc.uploader else None,
        created_at=doc.created_at,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  GET /knowledge/documents/{document_id}/text
# ═══════════════════════════════════════════════════════════════════════════════


@router.get(
    "/documents/{document_id}/text",
    response_model=DocumentTextResponse,
    summary="Get the full reconstructed text of a document",
)
async def get_document_text(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the complete text of a document reconstructed from its chunks.

    Chunks are ordered by ``chunk_index`` so the concatenated result matches
    the original document's paragraph order.  Used by the review workspace
    to display and highlight source text.
    """
    doc = await _get_doc_or_404(db, document_id, current_user.id)

    # Fetch all chunks ordered by their position in the original document
    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    chunks = result.scalars().all()

    # Concatenate chunk text with double-newline separators for readability
    content = "\n\n".join(c.content for c in chunks)

    return DocumentTextResponse(
        filename=doc.filename,
        file_type=doc.file_type,
        content=content,
    )
