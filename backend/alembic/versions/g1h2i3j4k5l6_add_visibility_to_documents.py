"""add visibility to knowledge_documents

Revision ID: g1h2i3j4k5l6
Revises: f0a1b2c3d4e5
Create Date: 2026-08-01 23:50:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add visibility column — defaults to 'public' for existing rows."""
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "visibility",
            sa.String(length=16),
            nullable=False,
            server_default="public",
            comment="Visibility: 'public' (knowledge base) or 'private' (project)",
        ),
    )


def downgrade() -> None:
    """Remove the visibility column."""
    op.drop_column("knowledge_documents", "visibility")
