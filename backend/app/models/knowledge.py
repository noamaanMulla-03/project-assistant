# ── Knowledge Document Model ─────────────────────────────────────────────────
# Stores metadata for uploaded knowledge-base documents.
# Raw files live on the filesystem under settings.UPLOAD_DIR so they remain
# accessible for text extraction / pgvector chunking later.
# The knowledge base is universal across all user accounts — uploaded_by is
# recorded for accountability only, not for per-user filtering.

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class KnowledgeDocument(Base):
    """A document uploaded to the shared knowledge base."""

    __tablename__ = "knowledge_documents"

    # ── Columns ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    filename: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="Original filename as provided by the uploader",
    )
    file_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Extension / MIME short form, e.g. 'pdf', 'docx', 'txt'",
    )
    file_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        comment="Path on disk relative to UPLOAD_DIR; filename is a UUID",
    )
    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="File size in bytes",
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who uploaded the document (NULL if user deleted)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="processing",
        server_default="processing",
        comment="Ingestion status: 'processing' | 'indexed' | 'error'",
    )

    # ── Relationships ─────────────────────────────────────────────────────
    uploader: Mapped["User | None"] = relationship(
        "User",
        lazy="joined",
    )
    # Cascade-delete chunks when the parent document is removed
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeDocument(id={self.id}, filename={self.filename!r}, "
            f"type={self.file_type!r})>"
        )


class DocumentChunk(Base):
    """A single chunk of text extracted from a knowledge document, with its
    embedding vector stored via pgvector for semantic similarity search.

    The embedding dimension (384) matches ``all-MiniLM-L6-v2``; if you change
    the embedding model, update the Vector dimension and run a new migration.
    """

    __tablename__ = "document_chunks"

    # ── Columns ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent knowledge document — chunks are cascade-deleted",
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Zero-based position of this chunk within the source document",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The chunk's text content",
    )
    # Raw metadata dict from the LangChain document loader.  For PDFs this
    # includes ``source`` (file path) and ``page`` (0-based page number).
    # For DOCX/TXT it includes ``source``.  Stored as JSON so the frontend
    # can display page citations without a schema migration per loader.
    metadata_json: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True),
        nullable=True,
        comment="Raw metadata from the LangChain loader (source, page, etc.)",
    )
    # pgvector column storing the 384-dim embedding from all-MiniLM-L6-v2
    embedding: Mapped[list[float]] = mapped_column(
        Vector(384),
        nullable=False,
        comment="Dense vector embedding (384-d) for semantic similarity search",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────
    document: Mapped["KnowledgeDocument"] = relationship(
        "KnowledgeDocument",
        back_populates="chunks",
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentChunk(id={self.id}, doc_id={self.document_id}, "
            f"index={self.chunk_index})>"
        )
