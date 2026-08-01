# ── Knowledge Schemas ─────────────────────────────────────────────────────────
# Pydantic models for knowledge-document request validation and responses,
# plus the semantic search contract.

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# ── Document Response Schemas ─────────────────────────────────────────────────


class KnowledgeDocumentResponse(BaseModel):
    """Returned when listing or uploading a document."""

    id: UUID
    filename: str
    file_type: str
    file_size: int  # bytes
    status: str  # ingestion status: "processing" | "indexed" | "error"
    visibility: str  # "public" (knowledge base) | "private" (project)
    uploaded_by: UUID | None
    uploaded_by_name: str | None  # full_name of uploader, null if user deleted
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeDocumentListResponse(BaseModel):
    """Paginated list of documents."""

    documents: list[KnowledgeDocumentResponse]
    total: int


# ── Search Contract ───────────────────────────────────────────────────────────


class SearchRequest(BaseModel):
    """Request body for semantic search over the knowledge base."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Natural language query to find relevant document chunks",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Number of top results to return",
    )


class DocumentRef(BaseModel):
    """Minimal reference to a parent document in search results."""

    id: UUID
    filename: str
    file_type: str

    model_config = {"from_attributes": True}


class SearchResult(BaseModel):
    """A single search hit: a matched chunk with its score, parent document,
    and the raw loader metadata (page numbers, source path, etc.)."""

    chunk_id: UUID
    content: str
    score: float = Field(
        ...,
        description="Cosine similarity score (0.0–1.0, higher = more relevant)",
    )
    document: DocumentRef
    metadata: dict = Field(
        default_factory=dict,
        description="Raw metadata from the document loader (e.g. page number, source path)",
    )

    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    """Paginated list of semantic search results."""

    results: list[SearchResult]
    query: str
    total: int


class DocumentTextResponse(BaseModel):
    """Full reconstructed text of a document with its filename."""

    filename: str
    content: str
