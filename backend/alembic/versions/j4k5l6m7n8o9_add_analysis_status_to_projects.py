"""Track background project analysis.

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
"""

from alembic import op
import sqlalchemy as sa

revision = "j4k5l6m7n8o9"
down_revision = "i3j4k5l6m7n8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("analysis_status", sa.String(20), server_default="idle", nullable=False),
    )
    op.add_column("projects", sa.Column("analysis_error", sa.Text(), nullable=True))
    op.execute("UPDATE projects SET analysis_status = 'completed' WHERE analysis_result IS NOT NULL")


def downgrade() -> None:
    op.drop_column("projects", "analysis_error")
    op.drop_column("projects", "analysis_status")
