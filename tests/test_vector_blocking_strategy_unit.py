"""Unit tests for the native-only VectorBlockingStrategy.

Vector blocking requires ArangoDB 3.12+ with a vector index; there is no
brute-force fallback. Uses a fake ArangoDB; no running server needed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from entity_resolution.strategies.vector_blocking import VectorBlockingStrategy
from entity_resolution.similarity.ann_adapter import VectorSearchUnavailableError


VEC_INDEX = {"type": "vector", "fields": ["embedding_vector"], "params": {"dimension": 384}}


class _FakeCursor:
    def __init__(self, rows):
        self._rows = list(rows)

    def next(self):
        return self._rows[0]

    def __iter__(self):
        return iter(self._rows)


class _FakeColl:
    def __init__(self, indexes):
        self._indexes = list(indexes)

    def indexes(self):
        return self._indexes

    def count(self):
        return 10


class _FakeAQL:
    def __init__(self, coverage, pairs):
        self.calls: List[Dict[str, Any]] = []
        self._coverage = coverage
        self._pairs = pairs

    def execute(self, query, bind_vars=None, **kwargs):
        q = str(query)
        self.calls.append({"query": q, "bind_vars": dict(bind_vars or {})})
        if "coverage_percent" in q:
            return _FakeCursor([self._coverage])
        if "APPROX_NEAR_COSINE" in q:
            return _FakeCursor(self._pairs)
        return _FakeCursor([])


class _FakeDB:
    def __init__(self, indexes, coverage, pairs=None):
        self._coll = _FakeColl(indexes)
        self.aql = _FakeAQL(coverage, pairs or [])

    def properties(self):
        return {"version": "3.12.0"}

    def collection(self, name):
        return self._coll


def _cov(with_emb, total=10):
    return {
        "total": total,
        "with_embeddings": with_emb,
        "without_embeddings": total - with_emb,
        "coverage_percent": (with_emb / total * 100) if total else 0.0,
    }


def test_generate_candidates_raises_if_no_embeddings():
    db = _FakeDB(indexes=[VEC_INDEX], coverage=_cov(0))
    strat = VectorBlockingStrategy(db=db, collection="customers")
    with pytest.raises(RuntimeError, match="No embeddings found"):
        strat.generate_candidates()


def test_generate_candidates_native_path_normalizes_pairs():
    pairs = [
        {"doc1_key": "1", "doc2_key": "2", "similarity": 0.9, "method": "arango_vector_index"},
        # reverse-direction duplicate that _normalize_pairs should collapse
        {"doc1_key": "2", "doc2_key": "1", "similarity": 0.9, "method": "arango_vector_index"},
    ]
    db = _FakeDB(indexes=[VEC_INDEX], coverage=_cov(10), pairs=pairs)
    strat = VectorBlockingStrategy(
        db=db, collection="customers", similarity_threshold=0.7, limit_per_entity=10
    )
    result = strat.generate_candidates()
    assert len(result) == 1
    assert result[0]["doc1_key"] == "1"
    assert result[0]["doc2_key"] == "2"
    # The search used the native APPROX_NEAR_COSINE path.
    assert any("APPROX_NEAR_COSINE" in c["query"] for c in db.aql.calls)


def test_generate_candidates_raises_when_not_native():
    # 3.12 reported but no vector index -> hard gate, no brute-force fallback.
    db = _FakeDB(indexes=[], coverage=_cov(10))
    strat = VectorBlockingStrategy(db=db, collection="customers")
    with pytest.raises(VectorSearchUnavailableError):
        strat.generate_candidates()


def test_repr_contains_collection_and_params():
    db = _FakeDB(indexes=[VEC_INDEX], coverage=_cov(10))
    strat = VectorBlockingStrategy(
        db=db, collection="customers", similarity_threshold=0.8, limit_per_entity=5
    )
    s = repr(strat)
    assert "customers" in s
    assert "0.8" in s
