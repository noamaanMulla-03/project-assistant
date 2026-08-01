"""add projects table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-01 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the projects table for grouping documents into analysis projects."""
    op.create_table(
        "projects",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_by",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="User who created this project (NULL if user deleted)",
        ),
        sa.Column(
            "document_ids",
            postgresql.ARRAY(sa.UUID()),
            nullable=False,
            comment="1-3 UUIDs referencing knowledge_documents rows",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="indexing",
            comment="Aggregate ingestion status: 'indexing' | 'ready' | 'error'",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop the projects table."""
    op.drop_table("projects")
