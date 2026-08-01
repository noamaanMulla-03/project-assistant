# ── Knowledge Router ──────────────────────────────────────────────────────────
# Endpoints for uploading, listing, downloading, deleting, and semantically
# searching knowledge-base documents.  All endpoints require authentication.
#
# Visibility model:
#   - "public"  → universal knowledge base, visible to all authenticated users
#   - "private" → project documents, visible only to the user who uploaded them

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models.knowledge import DocumentChunk, KnowledgeDocument
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.knowledge import (
    DocumentRef,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
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


async def _count_documents(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Return total number of documents visible to *user_id*.

    Public docs are visible to everyone; private docs only to the uploader.
    """
    result = await db.execute(
        select(func.count(KnowledgeDocument.id)).where(
            (KnowledgeDocument.visibility == "public")
            | (
                (KnowledgeDocument.visibility == "private")
                & (KnowledgeDocument.uploaded_by == user_id)
            )
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept a multipart file upload, store it on disk, and trigger async ingestion.

    Only ``.pdf``, ``.docx``, and ``.txt`` extensions are allowed.
    The file is saved with a UUID-based name to prevent collisions;
    the original filename is preserved in the database.

    After the response is sent, a background task extracts text, chunks it,
    embeds the chunks, and indexes them in pgvector + FAISS.
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

    # Persist metadata — status starts as "processing" until background ingestion finishes
    doc = KnowledgeDocument(
        filename=file.filename,
        file_type=ext.lstrip("."),  # store "pdf" not ".pdf"
        file_path=stored_name,  # relative to UPLOAD_DIR
        file_size=len(content),
        uploaded_by=current_user.id,
        status="processing",
        visibility="public",  # Knowledge Base → shared across all accounts
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    # Commit now so the background task's separate DB session can see this row.
    # (The get_db dependency will also try to commit, which becomes a no-op.)
    await db.commit()

    # Trigger async ingestion in the background (creates its own DB session).
    # Using asyncio.create_task instead of BackgroundTasks because the latter
    # does not reliably await async coroutines in all FastAPI versions.
    import asyncio
    from app.services.vectorization import ingest_document

    async def _safe_ingest() -> None:
        """Run ingestion in background, logging any failures."""
        try:
            await ingest_document(
                doc_id=doc.id,
                file_path=disk_path,
                file_type=doc.file_type,
            )
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Background ingestion failed for document %s",
                doc.id,
            )

    asyncio.create_task(_safe_ingest())

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
    total = await _count_documents(db, current_user.id)

    result = await db.execute(
        select(KnowledgeDocument)
        .where(
            (KnowledgeDocument.visibility == "public")
            | (
                (KnowledgeDocument.visibility == "private")
                & (KnowledgeDocument.uploaded_by == current_user.id)
            )
        )
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
    """Remove a document's metadata, file from disk, and FAISS index entries.

    Chunks in pgvector are cascade-deleted by the FK; FAISS is cleaned up here.
    """
    doc = await _get_doc_or_404(db, document_id, current_user.id)

    # Remove from FAISS before DB cascade (need chunk IDs from DB first)
    from app.services.faiss_service import get_faiss_service

    faiss = get_faiss_service()
    await faiss.remove_document(document_id, db)

    # Remove file from disk (best-effort — log but don't fail if missing)
    disk_path = _resolve_upload_path() / doc.file_path
    try:
        disk_path.unlink(missing_ok=True)
    except OSError:
        pass  # Log would go here in production

    await db.delete(doc)
    return MessageResponse(message=f"Document '{doc.filename}' deleted.")


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
    """Search document chunks by natural-language query using FAISS ANN + pgvector.

    The query is embedded with the same model used during ingestion,
    then the top-k most similar chunks are returned with their scores
    and parent document metadata.
    """
    from app.services.faiss_service import get_faiss_service
    from app.services.vectorization import _get_embedding_model

    # 1. Embed the query with the same model used during ingestion
    model = _get_embedding_model()
    query_embedding = model.embed_query(body.query)

    # 2. FAISS ANN search → get (chunk_id, score) pairs
    faiss = get_faiss_service()
    hits = faiss.search(query_embedding, body.top_k)

    if not hits:
        return SearchResponse(results=[], query=body.query, total=0)

    # 3. Fetch chunk content + parent document metadata from pgvector
    chunk_ids = [chunk_id for chunk_id, _score in hits]

    result = await db.execute(
        select(DocumentChunk)
        .options(selectinload(DocumentChunk.document))
        .where(DocumentChunk.id.in_(chunk_ids))
    )
    chunks = result.scalars().all()

    # Build a dict for O(1) lookup by chunk ID
    chunks_by_id = {c.id: c for c in chunks}

    # 4. Assemble response preserving FAISS rank order
    results: list[SearchResult] = []
    for chunk_id, score in hits:
        chunk = chunks_by_id.get(chunk_id)
        if chunk is None:
            continue
        results.append(
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
        )

    return SearchResponse(
        results=results,
        query=body.query,
        total=len(results),
    )


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
