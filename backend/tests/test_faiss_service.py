# ── FAISS Service Tests ───────────────────────────────────────────────────────
# Unit tests for the in-memory FAISS index: build, add, search, remove.
# Uses synthetic 384-d vectors (matching all-MiniLM-L6-v2 dimensionality)
# and a real FAISSService instance — no DB required.

import uuid
import math

import numpy as np
import pytest

from app.services.faiss_service import FAISSService, get_faiss_service

# all-MiniLM-L6-v2 produces 384-d embeddings
VEC_DIM = 384


# ═══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _make_normalized_vec(seed: int) -> list[float]:
    """Return a 384-d L2-normalized vector (deterministic from seed)."""
    rng = np.random.default_rng(seed)
    vec = rng.random(VEC_DIM, dtype=np.float32)
    vec /= np.linalg.norm(vec)
    return vec.tolist()


def _chunk_id(prefix: int, i: int) -> uuid.UUID:
    """Deterministic chunk UUID from a prefix byte + index."""
    # Build a deterministic 16-byte value: first byte = prefix, next 4 = i (big-endian), rest = 0
    raw = prefix.to_bytes(1, "big") + i.to_bytes(4, "big") + b"\x00" * 11
    return uuid.UUID(bytes=raw)


# ═══════════════════════════════════════════════════════════════════════════════
#  Build / Add Tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_build_index_populates_faiss():
    """Verify FAISS index total matches the number of vectors added."""
    svc = FAISSService()

    chunks = [(_chunk_id(0, i), _make_normalized_vec(i)) for i in range(10)]
    svc.add_chunks(chunks)

    assert svc._index.ntotal == 10
    assert len(svc._uuid_to_faiss) == 10
    assert len(svc._faiss_to_uuid) == 10


def test_add_chunks_is_idempotent_mapping():
    """Verify repeated add_chunks calls don't corrupt the ID mapping."""
    svc = FAISSService()

    batch1 = [(_chunk_id(0, i), _make_normalized_vec(i)) for i in range(5)]
    batch2 = [(_chunk_id(1, i), _make_normalized_vec(100 + i)) for i in range(3)]

    svc.add_chunks(batch1)
    svc.add_chunks(batch2)

    assert svc._index.ntotal == 8
    # UUID→FAISS mapping should have 8 entries
    assert len(svc._uuid_to_faiss) == 8
    # Every chunk UUID should map to a unique FAISS int64 ID
    faiss_ids = set(svc._uuid_to_faiss.values())
    assert len(faiss_ids) == 8


def test_empty_add_does_nothing():
    """Verify add_chunks with an empty list is a safe no-op."""
    svc = FAISSService()
    n_before = svc._index.ntotal
    svc.add_chunks([])
    assert svc._index.ntotal == n_before


# ═══════════════════════════════════════════════════════════════════════════════
#  Search Tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_search_returns_top_k():
    """Verify search returns exactly k results with scores in [0,1]."""
    svc = FAISSService()

    # Add 20 random chunks
    chunks = [(_chunk_id(0, i), _make_normalized_vec(i)) for i in range(20)]
    svc.add_chunks(chunks)

    # Search with a random query
    query = _make_normalized_vec(999)
    results = svc.search(query, k=5)

    assert len(results) == 5
    for chunk_id, score in results:
        assert isinstance(chunk_id, uuid.UUID)
        assert (
            0.0 <= score <= 1.0
        )  # Inner-product of normalized vectors ∈ [−1, 1], but typically ≥ 0


def test_search_self_match_perfect():
    """Verify that searching with an existing chunk's vector returns that chunk
    as the top result with a near-perfect score (inner product ≈ 1.0)."""
    svc = FAISSService()

    chunk_id = _chunk_id(42, 0)
    vec = _make_normalized_vec(42)
    svc.add_chunks([(chunk_id, vec)])

    # Add noise chunks to ensure the index has to distinguish
    for i in range(10):
        svc.add_chunks([(_chunk_id(99, i), _make_normalized_vec(100 + i))])

    results = svc.search(vec, k=1)
    assert len(results) == 1
    assert results[0][0] == chunk_id
    assert results[0][1] > 0.99  # Near-perfect self-match


def test_empty_index_search():
    """Verify searching an empty index returns an empty list (no crash)."""
    svc = FAISSService()
    results = svc.search(_make_normalized_vec(0), k=5)
    assert results == []
