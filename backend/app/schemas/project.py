# ── Project Schemas ───────────────────────────────────────────────────────────
# Pydantic models for project request validation and responses.
# Follows the same conventions as schemas/knowledge.py.

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

# ── Nested Document Reference ─────────────────────────────────────────────────


class ProjectDocumentRef(BaseModel):
    """Lightweight reference to a document within a project — includes
    ingestion status so the frontend can poll per-document progress."""

    id: UUID
    filename: str
    file_type: str
    file_size: int  # bytes
    status: str  # "processing" | "indexed" | "error"

    model_config = {"from_attributes": True}


# ── Project Response ──────────────────────────────────────────────────────────


class ProjectResponse(BaseModel):
    """Returned when creating or fetching a project."""

    id: UUID
    status: str  # aggregate: "indexing" | "ready" | "error"
    documents: list[ProjectDocumentRef]
    created_at: datetime
    created_by_name: str | None  # full_name of creator, null if user deleted
    # Cached AI extraction result — None until the first analysis completes
    analysis_result: dict[str, Any] | None = None
    analysis_status: str = "idle"  # idle | running | completed | error
    analysis_error: str | None = None
    # User-reviewed action summary — None until the user saves their review
    review_summary: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    """Paginated list of projects."""

    projects: list[ProjectResponse]
    total: int


# ── Review Summary Request ────────────────────────────────────────────────────


class ReviewSummaryRequest(BaseModel):
    """Payload from the frontend's "Finalize & Save" button.

    Each array mirrors the review workspace's mutable state — facts with
    user-assigned classifications, conflicts with resolution notes, and
    action items with approve/reject decisions.
    """

    facts: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    action_items: list[dict[str, Any]]


