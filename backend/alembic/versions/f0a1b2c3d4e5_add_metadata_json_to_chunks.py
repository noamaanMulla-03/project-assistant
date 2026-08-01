"""add metadata_json to document_chunks

Revision ID: f0a1b2c3d4e5
Revises: d4e5f6a7b8c9
Create Date: 2026-08-01 23:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a JSON column to store raw LangChain loader metadata per chunk."""
    op.add_column(
        "document_chunks",
        sa.Column(
            "metadata_json",
            sa.JSON(none_as_null=True),
            nullable=True,
            comment="Raw metadata from the LangChain loader (source, page, etc.)",
        ),
    )


def downgrade() -> None:
    """Remove the metadata_json column."""
    op.drop_column("document_chunks", "metadata_json")
