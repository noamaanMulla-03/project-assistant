"""Agent tool calls use separate sessions when they run concurrently."""

import asyncio
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.extraction import _build_tools


@pytest.mark.asyncio
async def test_parallel_document_tools_use_separate_sessions():
    doc_id = uuid.uuid4()
    initial_db = AsyncMock()
    docs = MagicMock()
    docs.scalars.return_value.all.return_value = [
        SimpleNamespace(id=doc_id, filename="notes.txt")
    ]
    initial_db.execute.return_value = docs
    opened = []

    @asynccontextmanager
    async def session():
        db = AsyncMock()
        chunks = MagicMock()
        chunks.scalars.return_value.all.return_value = [
            SimpleNamespace(chunk_index=0, metadata_json=None, content="hello")
        ]
        db.execute.return_value = chunks
        opened.append(db)
        yield db

    with patch("app.services.extraction.AsyncSessionLocal", session):
        tools = await _build_tools(initial_db, [doc_id])
        results = await asyncio.gather(
            tools[0].ainvoke({"filename": "notes.txt"}),
            tools[0].ainvoke({"filename": "notes.txt"}),
        )

    assert len(opened) == 2
    assert opened[0] is not opened[1]
    assert all("hello" in result for result in results)
