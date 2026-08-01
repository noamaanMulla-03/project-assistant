# ── Project Schemas ───────────────────────────────────────────────────────────
# Pydantic models for project request validation and responses.
# Follows the same conventions as schemas/knowledge.py.

from datetime import datetime
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

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    """Paginated list of projects."""

    projects: list[ProjectResponse]
    total: int
