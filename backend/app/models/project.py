# ── Project Model ─────────────────────────────────────────────────────────────
# Groups 1-3 uploaded KnowledgeDocuments into a "project" for the AI
# document-to-action workflow.  Documents remain standalone — the project
# stores their IDs in a PostgreSQL ARRAY(UUID) column rather than a foreign
# key on KnowledgeDocument, so the same document can belong to multiple
# projects in the future without model changes.
#
# The analysis_result JSONB column caches the full ExtractionResult so
# reopening a project from the sidebar loads instantly without re-running
# the LLM pipeline.

import uuid
from datetime import datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Project(Base):
    """A user-created project grouping up to 3 uploaded documents."""

    __tablename__ = "projects"

    # ── Columns ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who created this project (NULL if user deleted)",
    )
    document_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        comment="1-3 UUIDs referencing knowledge_documents rows",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="indexing",
        server_default="indexing",
        comment="Aggregate ingestion status: 'indexing' | 'ready' | 'error'",
    )
    # Cached AI extraction result — NULL until the first analysis completes.
    # Stored as JSONB so it can be returned inline on GET /projects/{id}.
    analysis_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
        comment="Cached ExtractionResult JSON from POST /projects/{id}/analyze",
    )
    analysis_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="idle", server_default="idle"
    )
    analysis_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Human-reviewed action summary — NULL until the user clicks "Finalize & Save".
    # Contains the user's corrections, reclassifications, and conflict resolutions.
    review_summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
        comment="User-reviewed action summary JSON from PUT /projects/{id}/review",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────
    creator: Mapped["User | None"] = relationship(
        "User",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<Project(id={self.id}, doc_count={len(self.document_ids)}, "
            f"status={self.status!r})>"
        )
