# ── Knowledge CRUD Tests ──────────────────────────────────────────────────────
# Tests for the knowledge-base router: list, delete, search.
# Uses mocked DB sessions following the existing test pattern.
# Routes that touch ORM relationships (_doc_to_response) are patched at
# the helper level to avoid needing fully-hydrated ORM instances.

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status

from app.models.knowledge import DocumentChunk, KnowledgeDocument
from app.routers.knowledge import (
    delete_document,
    list_documents,
    search_knowledge,
)
from app.schemas.knowledge import SearchRequest

# ═══════════════════════════════════════════════════════════════════════════════
#  List Documents
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_documents_empty(mock_db: AsyncMock, sample_user):
    """Listing documents when none exist returns empty list with total=0."""
    # _count_documents is called first — returns 0
    # Then a select query for docs returns empty
    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    select_result = MagicMock()
    select_result.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [count_result, select_result]

    response = await list_documents(db=mock_db, current_user=sample_user)

    assert response.total == 0
    assert response.documents == []


@pytest.mark.asyncio
async def test_list_documents_with_data(
    mock_db: AsyncMock, sample_user, sample_knowledge_docs
):
    """Listing returns public documents using mocked _doc_to_response."""
    count_result = MagicMock()
    count_result.scalar_one.return_value = 2
    select_result = MagicMock()
    select_result.scalars.return_value.all.return_value = sample_knowledge_docs

    mock_db.execute.side_effect = [count_result, select_result]

    # _doc_to_response accesses doc.uploader.full_name — patch it
    with patch(
        "app.routers.knowledge._doc_to_response",
        side_effect=lambda doc: MagicMock(
            id=doc.id,
            filename=doc.filename,
            file_type=doc.file_type,
            file_size=doc.file_size,
            status=doc.status,
            visibility=doc.visibility,
            uploaded_by=doc.uploaded_by,
            uploaded_by_name="Test User",
            created_at=doc.created_at,
        ),
    ):
        response = await list_documents(db=mock_db, current_user=sample_user)

    assert response.total == 2
    assert len(response.documents) == 2


# ═══════════════════════════════════════════════════════════════════════════════
#  Delete Document
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_delete_nonexistent_document(mock_db: AsyncMock, sample_user):
    """Deleting a non-existent document returns 404."""
    with pytest.raises(HTTPException) as exc:
        await delete_document(
            document_id=uuid.uuid4(), db=mock_db, current_user=sample_user
        )

    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


# ═══════════════════════════════════════════════════════════════════════════════
#  Search Documents
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_search_empty_query(mock_db: AsyncMock, sample_user):
    """An empty FAISS result returns empty list (no crash)."""
    with patch("app.services.faiss_service.get_faiss_service") as mock_faiss:
        mock_svc = MagicMock()
        mock_svc.search.return_value = []
        mock_faiss.return_value = mock_svc

        body = SearchRequest(query="nothing matches")
        response = await search_knowledge(
            body=body, db=mock_db, current_user=sample_user
        )

    assert response.results == []


@pytest.mark.asyncio
async def test_search_with_query(mock_db: AsyncMock, sample_user):
    """Search delegates to FAISS and returns formatted results when hits found."""
    from app.schemas.knowledge import DocumentRef, SearchResult, SearchResponse

    # Use the same UUID for FAISS hits and the DB chunk lookup
    fake_chunk_id = uuid.uuid4()

    # Patch FAISS and embedding model (both imported locally in search_knowledge)
    with patch("app.services.faiss_service.get_faiss_service") as mock_faiss, patch(
        "app.services.vectorization._get_embedding_model"
    ) as mock_embed:
        mock_svc = MagicMock()
        mock_svc.search.return_value = [(fake_chunk_id, 0.85)]
        mock_faiss.return_value = mock_svc
        mock_embed.return_value.embed_query.return_value = [0.1] * 384

        # Mock the DB to return a chunk whose ID matches the FAISS hit
        fake_chunk = MagicMock(spec=DocumentChunk)
        fake_chunk.id = fake_chunk_id  # MUST match FAISS hit ID
        fake_chunk.content = "Relevant text."
        fake_chunk.metadata_json = {"page": 1}
        fake_chunk.document = MagicMock(
            id=uuid.uuid4(),
            filename="policy.txt",
            file_type="txt",
        )

        chunk_result = MagicMock()
        chunk_result.scalars.return_value.all.return_value = [fake_chunk]
        mock_db.execute.return_value = chunk_result

        body = SearchRequest(query="security policy")
        response = await search_knowledge(
            body=body, db=mock_db, current_user=sample_user
        )

    assert len(response.results) == 1
    assert response.results[0].score == 0.85
    assert response.results[0].document.filename == "policy.txt"
    assert response.query == "security policy"
