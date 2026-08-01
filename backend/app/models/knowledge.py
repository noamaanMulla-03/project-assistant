# ── Knowledge Document Model ─────────────────────────────────────────────────
# Stores metadata for uploaded knowledge-base documents.
# Raw files live on the filesystem under settings.UPLOAD_DIR so they remain
# accessible for text extraction / pgvector chunking later.
# The knowledge base is universal across all user accounts — uploaded_by is
# recorded for accountability only, not for per-user filtering.

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
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

    # ── Relationships ─────────────────────────────────────────────────────
    uploader: Mapped["User | None"] = relationship(
        "User",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeDocument(id={self.id}, filename={self.filename!r}, "
            f"type={self.file_type!r})>"
        )
