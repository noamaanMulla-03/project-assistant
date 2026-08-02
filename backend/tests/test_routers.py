import uuid
import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException, status

from app.routers.project import save_review
from app.schemas.project import ReviewSummaryRequest
from app.models.project import Project
from app.models.user import User


@pytest.mark.asyncio
async def test_save_review_success():
    """Test that save_review updates the project's review_summary and flushes to the DB."""
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()
    
    # Setup mock user and project
    mock_user = User(id=user_id, email="test@example.com")
    mock_project = Project(
        id=project_id,
        created_by=user_id,
        document_ids=[],
        status="indexing",
        created_at=datetime.now(UTC),
        analysis_result={"facts": []},
        review_summary=None
    )
    
    # Mock DB session
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mock_result
    
    # Mock review summary payload
    request_payload = ReviewSummaryRequest(
        facts=[{"content": "fact 1"}],
        conflicts=[],
        action_items=[]
    )
    
    # Call the router function directly
    # Note: We skip the `_resolve_documents` call internally by raising an expected exception
    # or by mocking it. In this test, we just want to verify the db flush happens and
    # the project model is updated before we error out on the helper.
    # To fully test the router, we would patch `_resolve_documents` as well, but for
    # unit testing the important behaviour (saving), we can just inspect the project object.
    
    # Patch _resolve_documents to return empty list
    with pytest.MonkeyPatch.context() as m:
        m.setattr("app.routers.project._resolve_documents", AsyncMock(return_value=[]))
        
        response = await save_review(
            project_id=project_id,
            body=request_payload,
            db=mock_db,
            current_user=mock_user
        )
        
    assert mock_project.review_summary is not None
    assert len(mock_project.review_summary["facts"]) == 1
    assert mock_project.review_summary["facts"][0]["content"] == "fact 1"
    
    # Ensure flush was called
    mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_save_review_no_analysis_result():
    """Test that save_review raises 409 if no analysis has been run yet."""
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()
    
    mock_user = User(id=user_id)
    # Project has NO analysis_result
    mock_project = Project(
        id=project_id,
        created_by=user_id,
        analysis_result=None,
        review_summary=None
    )
    
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mock_result
    
    request_payload = ReviewSummaryRequest(facts=[], conflicts=[], action_items=[])
    
    with pytest.raises(HTTPException) as exc:
        await save_review(
            project_id=project_id,
            body=request_payload,
            db=mock_db,
            current_user=mock_user
        )
        
    assert exc.value.status_code == status.HTTP_409_CONFLICT
    assert "run analysis first" in exc.value.detail


@pytest.mark.asyncio
async def test_save_review_forbidden():
    """Test that save_review raises 403 if the user is not the creator."""
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    
    mock_user = User(id=other_user_id)
    mock_project = Project(
        id=project_id,
        created_by=user_id, # Different user!
        analysis_result={"facts": []},
    )
    
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mock_result
    
    request_payload = ReviewSummaryRequest(facts=[], conflicts=[], action_items=[])
    
    with pytest.raises(HTTPException) as exc:
        await save_review(
            project_id=project_id,
            body=request_payload,
            db=mock_db,
            current_user=mock_user
        )
        
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
