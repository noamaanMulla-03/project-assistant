"""Checks that the shared search keeps visibility filtering in the SQL query."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.search import search_public_chunks


@pytest.mark.asyncio
async def test_public_search_filters_before_limit(mock_db: AsyncMock):
    chunk = MagicMock()
    chunk.id = uuid.uuid4()
    result = MagicMock()
    result.all.return_value = [(chunk, 0.15)]
    mock_db.execute.return_value = result
    excluded = uuid.uuid4()

    with patch("app.services.search._get_embedding_model") as embedding_model:
        embedding_model.return_value.embed_query.return_value = [0.1] * 384
        hits = await search_public_chunks(mock_db, "safety", 5, [excluded])

    assert hits == [(chunk, 0.85)]
    statement = mock_db.execute.await_args.args[0]
    sql = str(statement)
    assert "knowledge_documents.visibility" in sql
    assert "knowledge_documents.id NOT IN" in sql
    assert "<=>" in sql
    assert "ORDER BY" in sql
    assert statement._limit_clause.value == 5


@pytest.mark.asyncio
async def test_public_search_returns_empty_list(mock_db: AsyncMock):
    result = MagicMock()
    result.all.return_value = []
    mock_db.execute.return_value = result

    with patch("app.services.search._get_embedding_model") as embedding_model:
        embedding_model.return_value.embed_query.return_value = [0.1] * 384
        assert await search_public_chunks(mock_db, "missing", 3) == []
