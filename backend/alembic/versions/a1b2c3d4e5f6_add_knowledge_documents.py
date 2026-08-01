"""add knowledge_documents table

Revision ID: a1b2c3d4e5f6
Revises: 0b95bf9b4587
Create Date: 2026-08-01 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "0b95bf9b4587"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the knowledge_documents table for the shared knowledge base."""
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "filename",
            sa.String(length=512),
            nullable=False,
            comment="Original filename as provided by the uploader",
        ),
        sa.Column(
            "file_type",
            sa.String(length=32),
            nullable=False,
            comment="Extension / MIME short form, e.g. 'pdf', 'docx', 'txt'",
        ),
        sa.Column(
            "file_path",
            sa.String(length=1024),
            nullable=False,
            comment="Path on disk relative to UPLOAD_DIR; filename is a UUID",
        ),
        sa.Column(
            "file_size",
            sa.BigInteger(),
            nullable=False,
            comment="File size in bytes",
        ),
        sa.Column(
            "uploaded_by",
            sa.UUID(),
            nullable=True,
            comment="User who uploaded the document (NULL if user deleted)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        op.f("ix_knowledge_documents_created_at"),
        "knowledge_documents",
        ["created_at"],
    )


def downgrade() -> None:
    """Remove the knowledge_documents table."""
    op.drop_index(
        op.f("ix_knowledge_documents_created_at"),
        table_name="knowledge_documents",
    )
    op.drop_table("knowledge_documents")
