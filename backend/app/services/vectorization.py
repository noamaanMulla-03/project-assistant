# ── Vectorization Service ─────────────────────────────────────────────────────
# Handles the full document ingestion pipeline:
#   1. Load raw text from PDF / DOCX / TXT files via LangChain loaders.
#   2. Split into overlapping chunks via RecursiveCharacterTextSplitter.
#   3. Embed chunks via HuggingFaceEmbeddings (all-MiniLM-L6-v2, local, free).
#   4. Bulk-persist DocumentChunk rows (content + vectors) into pgvector.
#   5. Add new vectors to the in-memory FAISS index incrementally.
#
# The embedding model is loaded once as a singleton to avoid repeated
# downloads / GPU warm-up.  Ingestion runs in a FastAPI BackgroundTask so the
# upload endpoint returns immediately while chunks are processed async.

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    Docx2txtLoader,
)
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document as LCDocument
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.knowledge import DocumentChunk

logger = logging.getLogger(__name__)

# ── Singleton embedding model ─────────────────────────────────────────────────
# Lazy-loaded on first use; reused for all subsequent ingestions + queries.

_embedding_model: HuggingFaceEmbeddings | None = None


def _get_embedding_model() -> HuggingFaceEmbeddings:
    """Return the shared HuggingFaceEmbeddings instance, loading it once."""
    global _embedding_model
    if _embedding_model is None:
        logger.info("Loading embedding model: %s", settings.EMBEDDING_MODEL)
        _embedding_model = HuggingFaceEmbeddings(
            model_name=settings.EMBEDDING_MODEL,
            model_kwargs={"trust_remote_code": True},
            # encode_kwargs={"normalize_embeddings": True} — we normalize
            # lazily before inserting into FAISS, not at embed time, so we
            # keep raw embeddings for pgvector storage.
        )
    return _embedding_model


# ── Document Loaders ──────────────────────────────────────────────────────────


def _load_pdf(path: Path) -> list[LCDocument]:
    """Extract text pages from a PDF file."""
    loader = PyPDFLoader(str(path))
    return loader.load()


def _load_docx(path: Path) -> list[LCDocument]:
    """Extract text from a DOCX file via docx2txt."""
    loader = Docx2txtLoader(str(path))
    return loader.load()


def _load_txt(path: Path) -> list[LCDocument]:
    """Read plain-text file (UTF-8)."""
    loader = TextLoader(str(path), encoding="utf-8")
    return loader.load()


# Dispatcher: file_type string → loader callable
_LOADERS = {
    "pdf": _load_pdf,
    "docx": _load_docx,
    "txt": _load_txt,
}


def load_document(file_path: Path, file_type: str) -> list[LCDocument]:
    """Load a file from disk into a list of LangChain Documents (pages/sections).

    Args:
        file_path: Absolute path to the file on disk.
        file_type: Lowercase extension without dot, e.g. ``"pdf"``.

    Returns:
        Raw LangChain Documents (usually one per page for PDFs).
    """
    loader = _LOADERS.get(file_type)
    if loader is None:
        raise ValueError(f"Unsupported file type for loading: {file_type!r}")
    logger.info("Loading %s file: %s", file_type, file_path.name)
    return loader(file_path)


# ── Text Splitting ────────────────────────────────────────────────────────────

_splitter: RecursiveCharacterTextSplitter | None = None


def _get_splitter() -> RecursiveCharacterTextSplitter:
    """Return a reusable splitter configured from app settings."""
    global _splitter
    if _splitter is None:
        _splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )
    return _splitter


def split_documents(docs: list[LCDocument]) -> list[LCDocument]:
    """Chunk a list of LangChain Documents into smaller, overlapping pieces."""
    return _get_splitter().split_documents(docs)


# ── Ingestion Pipeline ────────────────────────────────────────────────────────


async def ingest_document(
    doc_id: UUID,
    file_path: Path,
    file_type: str,
) -> None:
    """Full ingestion pipeline: load → split → embed → persist chunks → update FAISS.

    CPU-bound work (file loading, text splitting, embedding) runs *outside*
    the DB session so a long model download or large file doesn't hold a
    database connection hostage.  Embedding runs via ``asyncio.to_thread``
    to keep the event loop responsive, with a configurable timeout.

    Args:
        doc_id: UUID of the ``KnowledgeDocument`` row.
        file_path: Absolute path to the uploaded file on disk.
        file_type: Extension without dot (``"pdf"``, ``"docx"``, ``"txt"``).
    """
    from app.database import AsyncSessionLocal
    from app.models.knowledge import KnowledgeDocument
    from app.services.faiss_service import get_faiss_service

    try:
        # ── Phase 1: CPU-bound work (no DB session held) ──────────────────

        # 1a. Load raw text from file (sync, fast)
        raw_docs = load_document(file_path, file_type)
        if not raw_docs:
            logger.warning("No text extracted from document %s", doc_id)
            async with AsyncSessionLocal() as db:
                await _set_status(db, KnowledgeDocument, doc_id, "indexed")
            return

        # 1b. Split into overlapping chunks (sync, fast)
        chunks = split_documents(raw_docs)
        logger.info("Document %s: split into %d chunks", doc_id, len(chunks))

        # 1c. Embed via thread pool — runs off the event loop so the
        #     first-call model download (~90 MB) doesn't block anything.
        model = _get_embedding_model()
        texts = [chunk.page_content for chunk in chunks]
        embeddings = await asyncio.wait_for(
            asyncio.to_thread(model.embed_documents, texts),
            timeout=settings.INGESTION_TIMEOUT_SECONDS,
        )

        # ── Phase 2: Persist (short-lived DB session) ─────────────────────

        chunk_ids_and_vectors: list[tuple[UUID, list[float]]] = []

        async with AsyncSessionLocal() as db:
            # 2a. Bulk-insert DocumentChunk rows into pgvector
            chunk_models: list[DocumentChunk] = []
            for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
                chunk_model = DocumentChunk(
                    document_id=doc_id,
                    chunk_index=i,
                    content=chunk.page_content,
                    embedding=vector,
                    # Preserve loader metadata: page numbers (PDF),
                    # source path, etc.  Null-safe — if .metadata is
                    # empty we store None rather than an empty dict.
                    metadata_json=chunk.metadata if chunk.metadata else None,
                )
                chunk_models.append(chunk_model)
                chunk_ids_and_vectors.append((chunk_model.id, vector))

            db.add_all(chunk_models)
            await db.flush()

            # 2b. Incrementally add to the in-memory FAISS index
            faiss = get_faiss_service()
            faiss.add_chunks(chunk_ids_and_vectors)

            # 2c. Mark as successfully indexed
            await _set_status(db, KnowledgeDocument, doc_id, "indexed")

        logger.info(
            "Document %s ingested successfully: %d chunks indexed",
            doc_id,
            len(chunks),
        )

    except asyncio.TimeoutError:
        logger.error(
            "Ingestion timed out for document %s after %d seconds",
            doc_id,
            settings.INGESTION_TIMEOUT_SECONDS,
        )
        await _set_status_fresh(KnowledgeDocument, doc_id, "error")

    except Exception:
        logger.exception("Ingestion failed for document %s", doc_id)
        await _set_status_fresh(KnowledgeDocument, doc_id, "error")


async def _set_status(
    db: AsyncSession,
    model: type,
    doc_id: UUID,
    status: str,
) -> None:
    """Update the ingestion status of a KnowledgeDocument row and commit."""
    from sqlalchemy import update

    await db.execute(update(model).where(model.id == doc_id).values(status=status))
    await db.commit()


async def _set_status_fresh(
    model: type,
    doc_id: UUID,
    status: str,
) -> None:
    """Update ingestion status in a *fresh* DB session.

    Used from error paths where the original session may be dead.  If this
    also fails the document will stay in its current state — we log at
    CRITICAL so operators can intervene.
    """
    from app.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            await _set_status(db, model, doc_id, status)
    except Exception:
        logger.critical(
            "CRITICAL: Failed to update status to %r for document %s "
            "— document may be stuck indefinitely.",
            status,
            doc_id,
            exc_info=True,
        )
