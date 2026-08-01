# ── FAISS In-Memory Index Service ─────────────────────────────────────────────
# Manages a singleton FAISS IndexIDMap(IndexFlatIP) for fast approximate
# nearest-neighbour (ANN) search over document chunk embeddings.
#
# Design decisions:
#   • IndexFlatIP (inner product) with L2-normalized vectors → equivalent to
#     cosine similarity, but faster than IndexFlatL2 for normalized data.
#   • IndexIDMap wrapper lets us use arbitrary UUIDs (mapped to FAISS int64
#     IDs) so we can remove chunks by document without rebuilding the index.
#   • The index lives in memory.  On startup it's rebuilt from all pgvector
#     rows; after that, ingest and delete do incremental adds/removes.
#   • For production with 100K+ chunks, consider persisting the index to disk
#     via faiss.write_index() / faiss.read_index() on shutdown/startup.

import logging
import threading
from uuid import UUID

import numpy as np
import faiss
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import DocumentChunk

logger = logging.getLogger(__name__)

# Embedding dimensionality — must match the model (all-MiniLM-L6-v2 = 384).
_DIM = 384


class FAISSService:
    """Thread-safe singleton wrapping a FAISS index for chunk vectors.

    Public API:
        build_index(db)     — rebuild from pgvector (called once at startup).
        add_chunks([(id, vec)]) — incremental add after ingestion.
        remove_document(doc_id, db) — remove all chunks of a doc from FAISS.
        search(query_vec, k) — return top-k (chunk_id, score) pairs.
    """

    def __init__(self) -> None:
        # FAISS IndexFlatIP gives cosine similarity when vectors are L2-normalized
        self._index: faiss.IndexIDMap = faiss.IndexIDMap(
            faiss.IndexFlatIP(_DIM)
        )
        # Bidirectional mapping: chunk UUID ↔ FAISS internal int64 ID
        self._uuid_to_faiss: dict[UUID, int] = {}
        self._faiss_to_uuid: dict[int, UUID] = {}
        # Next FAISS ID to assign (monotonically increasing)
        self._next_id: int = 0
        # Mutex for index mutation operations (add, remove)
        self._lock = threading.Lock()

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(vec: list[float]) -> np.ndarray:
        """L2-normalize a vector so inner product ≡ cosine similarity."""
        arr = np.array(vec, dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr /= norm
        return arr.reshape(1, -1)

    # ── Build (startup) ───────────────────────────────────────────────────

    async def build_index(self, db: AsyncSession) -> None:
        """Rebuild the entire FAISS index from all DocumentChunk rows in pgvector.

        Called once during application startup.  Clears any existing index state.
        """
        result = await db.execute(
            select(DocumentChunk.id, DocumentChunk.embedding)
        )
        rows = result.all()

        if not rows:
            logger.info("FAISS: no chunks found — index remains empty")
            return

        # Collect vectors and IDs
        vectors = np.zeros((len(rows), _DIM), dtype=np.float32)
        with self._lock:
            self._uuid_to_faiss.clear()
            self._faiss_to_uuid.clear()
            self._next_id = 0

            for i, (chunk_id, embedding) in enumerate(rows):
                faiss_id = self._next_id
                self._next_id += 1
                self._uuid_to_faiss[chunk_id] = faiss_id
                self._faiss_to_uuid[faiss_id] = chunk_id
                vectors[i] = self._normalize(embedding)

            # Reset the index and add all vectors
            self._index = faiss.IndexIDMap(faiss.IndexFlatIP(_DIM))
            faiss_ids = np.array(
                [self._uuid_to_faiss[r[0]] for r in rows], dtype=np.int64
            )
            self._index.add_with_ids(vectors, faiss_ids)

        logger.info(
            "FAISS index built: %d vectors from %d chunks",
            self._index.ntotal,
            len(rows),
        )

    # ── Incremental Add ───────────────────────────────────────────────────

    def add_chunks(
        self, chunk_ids_and_vectors: list[tuple[UUID, list[float]]]
    ) -> None:
        """Add new chunk vectors to the FAISS index after ingestion.

        Args:
            chunk_ids_and_vectors: List of (chunk_uuid, 384-d embedding vector).
        """
        if not chunk_ids_and_vectors:
            return

        n = len(chunk_ids_and_vectors)
        vectors = np.zeros((n, _DIM), dtype=np.float32)
        faiss_ids = np.zeros(n, dtype=np.int64)

        with self._lock:
            for i, (chunk_id, vec) in enumerate(chunk_ids_and_vectors):
                faiss_id = self._next_id
                self._next_id += 1
                self._uuid_to_faiss[chunk_id] = faiss_id
                self._faiss_to_uuid[faiss_id] = chunk_id
                vectors[i] = self._normalize(vec).ravel()
                faiss_ids[i] = faiss_id

            self._index.add_with_ids(vectors, faiss_ids)

        logger.info("FAISS: added %d chunks (total: %d)", n, self._index.ntotal)

    # ── Remove by Document ────────────────────────────────────────────────

    async def remove_document(
        self, doc_id: UUID, db: AsyncSession
    ) -> None:
        """Remove all chunks belonging to a deleted document from the FAISS index.

        Called after deleting a KnowledgeDocument.  The chunk rows in pgvector
        are cascade-deleted by the FK, but we must explicitly tell FAISS to
        drop those IDs.

        Args:
            doc_id: UUID of the deleted KnowledgeDocument.
            db: Async session (unused currently — we resolve IDs from memory
                mapping; kept for symmetry and future use).
        """
        # Collect FAISS IDs for all chunks of this document
        faiss_ids_to_remove: list[int] = []
        with self._lock:
            # Find all chunk UUIDs belonging to this document
            for chunk_id, faiss_id in list(self._uuid_to_faiss.items()):
                # We don't have doc_id in the mapping, so we need to look it up.
                # Instead, we'll filter during the search phase by checking DB.
                # Actually, for removal we need to query DB or maintain a
                # doc_id -> chunk_ids mapping.
                pass

        # Re-query to get chunk IDs for this document
        result = await db.execute(
            select(DocumentChunk.id).where(
                DocumentChunk.document_id == doc_id
            )
        )
        chunk_ids = [row[0] for row in result.all()]

        if not chunk_ids:
            return

        with self._lock:
            faiss_ids_arr = np.zeros(len(chunk_ids), dtype=np.int64)
            count = 0
            for i, cid in enumerate(chunk_ids):
                fid = self._uuid_to_faiss.pop(cid, None)
                if fid is not None:
                    self._faiss_to_uuid.pop(fid, None)
                    faiss_ids_arr[i] = fid
                    count += 1

            if count > 0:
                # Only pass valid IDs to remove_ids
                valid = faiss_ids_arr[:count]
                self._index.remove_ids(valid)

        logger.info(
            "FAISS: removed %d chunks for document %s (total: %d)",
            count,
            doc_id,
            self._index.ntotal,
        )

    # ── Search ────────────────────────────────────────────────────────────

    def search(
        self, query_embedding: list[float], k: int
    ) -> list[tuple[UUID, float]]:
        """Find the top-k most similar chunk embeddings by cosine similarity.

        Args:
            query_embedding: A 384-d embedding vector of the search query.
            k: Number of top results to return.

        Returns:
            List of (chunk_uuid, similarity_score) sorted by descending score.
            Scores are cosine similarity (1.0 = identical, 0.0 = orthogonal).
        """
        if self._index.ntotal == 0:
            return []

        k = min(k, self._index.ntotal)
        query = self._normalize(query_embedding)

        distances, indices = self._index.search(query, k)

        results: list[tuple[UUID, float]] = []
        with self._lock:
            for dist, idx in zip(distances[0], indices[0]):
                if idx == -1:  # FAISS sentinel for "no result"
                    continue
                chunk_uuid = self._faiss_to_uuid.get(int(idx))
                if chunk_uuid is not None:
                    # distances from IndexFlatIP are inner products;
                    # since vectors are L2-normalized, this is cosine similarity
                    results.append((chunk_uuid, float(dist)))

        return results


# ── Singleton ─────────────────────────────────────────────────────────────────

_faiss_service: FAISSService | None = None


def get_faiss_service() -> FAISSService:
    """Return the process-wide singleton FAISSService."""
    global _faiss_service
    if _faiss_service is None:
        _faiss_service = FAISSService()
    return _faiss_service
