# ── Project CRUD Tests ────────────────────────────────────────────────────────
# Tests for creating projects, listing, fetching, analysing, removing documents,
# and saving reviews.  Uses mocked DB sessions consistent with existing tests.

import uuid
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException, status

from app.models.project import Project
from app.models.user import User
from app.routers.project import (
    analyze_project,
    create_project,
    get_project,
    list_projects,
    remove_project_document,
    save_review,
)
from app.schemas.project import ReviewSummaryRequest

# ═══════════════════════════════════════════════════════════════════════════════
#  GET /projects
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_projects_empty(mock_db: AsyncMock, sample_user):
    """Listing projects when none exist returns empty list with total=0."""
    # Default mock_db.execute already returns empty; override for count
    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    mock_db.execute.return_value = count_result  # only one query (count)

    # list_projects does two queries: count + select
    count_r = MagicMock()
    count_r.scalar_one.return_value = 0
    select_r = MagicMock()
    select_r.scalars.return_value.all.return_value = []
    mock_db.execute.side_effect = [count_r, select_r]

    response = await list_projects(db=mock_db, current_user=sample_user)

    assert response.total == 0
    assert response.projects == []


# ═══════════════════════════════════════════════════════════════════════════════
#  GET /projects/{id}
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_nonexistent_project(mock_db: AsyncMock, sample_user):
    """Fetching a non-existent project returns 404."""
    with pytest.raises(HTTPException) as exc:
        await get_project(project_id=uuid.uuid4(), db=mock_db, current_user=sample_user)

    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_get_other_users_project_is_forbidden(
    mock_db: AsyncMock, sample_user, sample_project
):
    sample_project.created_by = uuid.uuid4()
    project_result = MagicMock()
    project_result.scalar_one_or_none.return_value = sample_project
    mock_db.execute.return_value = project_result

    with pytest.raises(HTTPException) as exc:
        await get_project(
            project_id=sample_project.id, db=mock_db, current_user=sample_user
        )

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
    mock_db.execute.assert_awaited_once()  # No document lookup follows.


# ═══════════════════════════════════════════════════════════════════════════════
#  POST /projects/{id}/analyze
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_analyze_returns_cached_result(
    mock_db: AsyncMock, sample_user, sample_project
):
    """When cached analysis_result exists and force=False, return it immediately
    without calling the LLM."""
    # Mock project query
    project_result = MagicMock()
    project_result.scalar_one_or_none.return_value = sample_project
    mock_db.execute.return_value = project_result

    tasks = BackgroundTasks()
    with patch("app.routers.project._resolve_documents", AsyncMock(return_value=[])):
        result = await analyze_project(
            project_id=sample_project.id,
            background_tasks=tasks,
            force=False,
            db=mock_db,
            current_user=sample_user,
        )

    assert result.analysis_result["facts"][0]["content"] == "test fact"
    assert not tasks.tasks


@pytest.mark.asyncio
async def test_analyze_force_reruns_pipeline(
    mock_db: AsyncMock, sample_user, sample_project
):
    """When force=True, the pipeline re-runs even if cached result exists."""
    # Mock project query
    project_result = MagicMock()
    project_result.scalar_one_or_none.return_value = sample_project
    claim_result = MagicMock()
    claim_result.rowcount = 1
    mock_db.execute.side_effect = [project_result, claim_result]
    tasks = BackgroundTasks()

    async def refresh(project):
        project.analysis_status = "running"

    mock_db.refresh.side_effect = refresh
    with patch("app.routers.project._resolve_documents", AsyncMock(return_value=[])):
        result = await analyze_project(
            project_id=sample_project.id,
            background_tasks=tasks,
            force=True,
            db=mock_db,
            current_user=sample_user,
        )

    assert result.analysis_status == "running"
    assert len(tasks.tasks) == 1
    assert tasks.tasks[0].args[0] == sample_project.id


@pytest.mark.asyncio
async def test_analyze_running_does_not_start_duplicate(
    mock_db: AsyncMock, sample_user, sample_project
):
    sample_project.analysis_status = "running"
    project_result = MagicMock()
    project_result.scalar_one_or_none.return_value = sample_project
    mock_db.execute.return_value = project_result
    tasks = BackgroundTasks()

    with patch("app.routers.project._resolve_documents", AsyncMock(return_value=[])):
        response = await analyze_project(
            project_id=sample_project.id,
            background_tasks=tasks,
            force=True,
            db=mock_db,
            current_user=sample_user,
        )

    assert response.analysis_status == "running"
    assert not tasks.tasks
    mock_db.execute.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════════
#  POST /projects/{id}/analyze — error states
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_analyze_forbidden_wrong_user(mock_db: AsyncMock, sample_project):
    """A user who didn't create the project gets 403."""
    other_user = User(
        id=uuid.uuid4(),
        email="other@example.com",
        hashed_password="x",
        full_name="Other",
    )

    project_result = MagicMock()
    project_result.scalar_one_or_none.return_value = sample_project
    mock_db.execute.return_value = project_result

    with pytest.raises(HTTPException) as exc:
        await analyze_project(
            project_id=sample_project.id,
            background_tasks=BackgroundTasks(),
            db=mock_db,
            current_user=other_user,
        )

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


# ═══════════════════════════════════════════════════════════════════════════════
#  PUT /projects/{id}/review
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_save_review_success(mock_db: AsyncMock, sample_user, sample_project):
    """Saving a review updates the project's review_summary JSONB column."""
    # Mock project fetch
    project_result = MagicMock()
    project_result.scalar_one_or_none.return_value = sample_project
    mock_db.execute.return_value = project_result

    body = ReviewSummaryRequest(
        facts=[{"content": "Reviewed fact", "classification": "fact"}],
        conflicts=[],
        action_items=[{"content": "Do X", "status": "approved"}],
    )

    with patch(
        "app.routers.project._resolve_documents",
        AsyncMock(return_value=[]),
    ):
        await save_review(
            project_id=sample_project.id,
            body=body,
            db=mock_db,
            current_user=sample_user,
        )

    # Verify project was updated
    assert sample_project.review_summary is not None
    assert sample_project.review_summary["facts"][0]["content"] == "Reviewed fact"
    assert sample_project.review_summary["action_items"][0]["status"] == "approved"
    mock_db.flush.assert_called()


@pytest.mark.asyncio
async def test_save_review_no_analysis(mock_db: AsyncMock, sample_user):
    """Saving a review for a project that hasn't been analysed returns 409."""
    project_id = uuid.uuid4()
    # Project with no analysis_result
    proj = Project(
        id=project_id,
        created_by=sample_user.id,
        document_ids=[],
        status="ready",
        analysis_result=None,  # No analysis yet
    )

    proj_result = MagicMock()
    proj_result.scalar_one_or_none.return_value = proj
    mock_db.execute.return_value = proj_result

    body = ReviewSummaryRequest(facts=[], conflicts=[], action_items=[])

    with pytest.raises(HTTPException) as exc:
        await save_review(
            project_id=project_id,
            body=body,
            db=mock_db,
            current_user=sample_user,
        )

    assert exc.value.status_code == status.HTTP_409_CONFLICT
    assert "run analysis first" in exc.value.detail.lower()
