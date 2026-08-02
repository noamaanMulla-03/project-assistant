"""add analysis_result JSONB column to projects

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-08-02 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "h2i3j4k5l6m7"
down_revision: Union[str, None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add analysis_result JSONB column to cache AI extraction results."""
    op.add_column(
        "projects",
        sa.Column(
            "analysis_result",
            postgresql.JSONB(),
            nullable=True,
            comment="Cached ExtractionResult JSON from POST /projects/{id}/analyze",
        ),
    )


def downgrade() -> None:
    """Remove analysis_result column."""
    op.drop_column("projects", "analysis_result")
