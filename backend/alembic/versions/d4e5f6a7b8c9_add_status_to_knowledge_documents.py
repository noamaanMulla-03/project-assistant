"""add status to knowledge_documents

Revision ID: d4e5f6a7b8c9
Revises: c7d8e9f0a1b2
Create Date: 2026-08-01 23:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add status column to knowledge_documents (processing | indexed | error)."""
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="processing",
            comment="Ingestion status: 'processing' | 'indexed' | 'error'",
        ),
    )


def downgrade() -> None:
    """Remove the status column."""
    op.drop_column("knowledge_documents", "status")
