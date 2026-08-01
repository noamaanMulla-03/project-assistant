# ── Knowledge Schemas ─────────────────────────────────────────────────────────
# Pydantic models for knowledge-document request validation and responses.

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

# ── Response Schema ───────────────────────────────────────────────────────────


class KnowledgeDocumentResponse(BaseModel):
    """Returned when listing or uploading a document."""

    id: UUID
    filename: str
    file_type: str
    file_size: int  # bytes
    uploaded_by: UUID | None
    uploaded_by_name: str | None  # full_name of uploader, null if user deleted
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeDocumentListResponse(BaseModel):
    """Paginated list of documents."""

    documents: list[KnowledgeDocumentResponse]
    total: int
