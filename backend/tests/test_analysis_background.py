"""Background analysis stores completion and failure for later page loads."""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.extraction import ExtractionResult
from app.services.analysis import analyze_project_background


@pytest.mark.asyncio
async def test_analysis_completes_and_saves_result():
    db = AsyncMock()

    @asynccontextmanager
    async def session():
        yield db

    result = ExtractionResult(document_types=[], summary="Done")
    with patch("app.services.analysis.AsyncSessionLocal", session), patch(
        "app.services.analysis.run_extraction", AsyncMock(return_value=result)
    ):
        await analyze_project_background(uuid.uuid4(), [uuid.uuid4()], False)

    values = db.execute.await_args.args[0].compile().params
    assert values["analysis_status"] == "completed"
    assert values["analysis_result"]["summary"] == "Done"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_analysis_failure_is_visible_to_user():
    db = AsyncMock()

    @asynccontextmanager
    async def session():
        yield db

    with patch("app.services.analysis.AsyncSessionLocal", session), patch(
        "app.services.analysis.run_extraction", AsyncMock(side_effect=RuntimeError("LLM unavailable"))
    ):
        await analyze_project_background(uuid.uuid4(), [uuid.uuid4()], False)

    values = db.execute.await_args.args[0].compile().params
    assert values["analysis_status"] == "error"
    assert "LLM unavailable" in values["analysis_error"]
    db.commit.assert_awaited_once()
