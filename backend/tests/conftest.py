# ── Shared Test Fixtures ──────────────────────────────────────────────────────
# Reusable pytest fixtures for mocking DB sessions, users, and LLM responses.
# All tests use async DB session mocks — no real PostgreSQL required.

import uuid
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.user import User
from app.models.project import Project
from app.models.knowledge import KnowledgeDocument

# ═══════════════════════════════════════════════════════════════════════════════
#  User Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_user_id() -> uuid.UUID:
    """A deterministic user UUID for tests."""
    return uuid.UUID("12345678-1234-1234-1234-123456789abc")


@pytest.fixture
def sample_user(sample_user_id: uuid.UUID) -> User:
    """A fully-populated User ORM model."""
    return User(
        id=sample_user_id,
        email="test@example.com",
        hashed_password="hashed_mock",
        full_name="Test User",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  DB Session Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_db() -> AsyncMock:
    """An async DB session mock.  Use .return_value on execute() to control queries."""
    db = AsyncMock()
    # Default: execute returns an empty result
    empty_result = MagicMock()
    empty_result.scalar_one_or_none.return_value = None
    empty_result.scalar_one.return_value = None
    empty_result.scalars.return_value.all.return_value = []
    db.execute.return_value = empty_result
    return db


# ═══════════════════════════════════════════════════════════════════════════════
#  Project Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_doc_ids() -> list[uuid.UUID]:
    """Two deterministic document UUIDs."""
    return [
        uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
    ]


@pytest.fixture
def sample_project(
    sample_user_id: uuid.UUID, sample_doc_ids: list[uuid.UUID]
) -> Project:
    """A project with two doc IDs and cached analysis_result."""
    return Project(
        id=uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        created_by=sample_user_id,
        document_ids=sample_doc_ids,
        status="ready",
        created_at=datetime.now(UTC),
        analysis_result={
            "document_types": [
                {"filename": "doc1.pdf", "document_type": "meeting_notes"}
            ],
            "summary": "Test summary.",
            "facts": [
                {
                    "content": "test fact",
                    "source_document": "doc1.pdf",
                    "source_section": "chunk_0",
                    "confidence": "high",
                }
            ],
        },
        analysis_status="completed",
        analysis_error=None,
        review_summary=None,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Knowledge Document Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_knowledge_docs(
    sample_user_id: uuid.UUID, sample_doc_ids: list[uuid.UUID]
) -> list[KnowledgeDocument]:
    """Two indexed knowledge documents with full field coverage."""
    now = datetime.now(UTC)
    return [
        KnowledgeDocument(
            id=sample_doc_ids[0],
            filename="doc1.pdf",
            file_type="pdf",
            file_path="abcd1234.pdf",
            file_size=1024,
            uploaded_by=sample_user_id,
            status="indexed",
            visibility="public",
            created_at=now,
        ),
        KnowledgeDocument(
            id=sample_doc_ids[1],
            filename="doc2.txt",
            file_type="txt",
            file_path="efgh5678.txt",
            file_size=512,
            uploaded_by=sample_user_id,
            status="indexed",
            visibility="public",
            created_at=now,
        ),
    ]
