"""Search public document chunks with the existing pgvector column."""

import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.knowledge import DocumentChunk, KnowledgeDocument
from app.services.vectorization import _get_embedding_model


async def search_public_chunks(
    db: AsyncSession,
    query: str,
    top_k: int,
    exclude_doc_ids: list[UUID] | None = None,
) -> list[tuple[DocumentChunk, float]]:
    """Return public chunks ranked by cosine similarity, with metadata loaded."""
    embedding = await asyncio.to_thread(lambda: _get_embedding_model().embed_query(query))
    distance = DocumentChunk.embedding.cosine_distance(embedding)
    statement = (
        select(DocumentChunk, distance.label("distance"))
        .join(DocumentChunk.document)
        .options(selectinload(DocumentChunk.document))
        .where(KnowledgeDocument.visibility == "public")
        .order_by(distance)
        .limit(top_k)
    )
    if exclude_doc_ids:
        statement = statement.where(KnowledgeDocument.id.not_in(exclude_doc_ids))

    rows = (await db.execute(statement)).all()
    return [(chunk, 1.0 - float(distance)) for chunk, distance in rows]
