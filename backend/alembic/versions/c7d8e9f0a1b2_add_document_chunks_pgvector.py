"""add document_chunks with pgvector

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
Create Date: 2026-08-01 23:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable pgvector extension and create the document_chunks table."""
    # Enable the pgvector extension (safe to run multiple times)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create document_chunks table with a Vector(384) column for all-MiniLM-L6-v2
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "document_id",
            sa.UUID(),
            nullable=False,
            comment="Parent knowledge document — chunks are cascade-deleted",
        ),
        sa.Column(
            "chunk_index",
            sa.Integer(),
            nullable=False,
            comment="Zero-based position of this chunk within the source document",
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            comment="The chunk's text content",
        ),
        sa.Column(
            "embedding",
            Vector(384),
            nullable=False,
            comment="Dense vector embedding (384-d) for semantic similarity search",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            ondelete="CASCADE",
        ),
    )
    # Index for fast FK lookups (get all chunks of a document)
    op.create_index(
        op.f("ix_document_chunks_document_id"),
        "document_chunks",
        ["document_id"],
    )
    # HNSW index for cosine-distance search on embeddings.
    op.execute("""
        CREATE INDEX ix_document_chunks_embedding
        ON document_chunks
        USING hnsw (embedding vector_cosine_ops)
        """)


def downgrade() -> None:
    """Drop the document_chunks table. (Extension is kept — safe to leave.)"""
    op.drop_index(
        op.f("ix_document_chunks_embedding"),
        table_name="document_chunks",
        postgresql_using="hnsw",
    )
    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_table("document_chunks")
