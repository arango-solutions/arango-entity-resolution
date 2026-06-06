"""Query-construction tests for the native vector-index path (APPROX_NEAR_COSINE).

Verifies the generated AQL uses APPROX_NEAR_COSINE and applies blocking/filters,
using a fake ArangoDB that reports a 3.12 vector index. No running server needed.
"""

from __future__ import annotations

from typing import Any, Dict, List

from entity_resolution.similarity.ann_adapter import ANNAdapter, METHOD_VECTOR_INDEX


class _FakeColl:
    def __init__(self, docs, indexes):
        self._docs = docs
        self._indexes = list(indexes)

    def indexes(self):
        return self._indexes

    def count(self):
        return len(self._docs)

    def get(self, key):
        return self._docs.get(key)


class _FakeAQL:
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self.rows: List[List[Dict[str, Any]]] = []

    def queue(self, rows):
        self.rows.append(rows)

    def execute(self, query, bind_vars=None, **kwargs):
        self.calls.append({"query": str(query), "bind_vars": dict(bind_vars or {})})
        return list(self.rows.pop(0) if self.rows else [])


class _FakeDB:
    def __init__(self, docs=None, indexes=None):
        self._coll = _FakeColl(docs or {}, indexes or [])
        self.aql = _FakeAQL()

    def properties(self):
        return {"version": "3.12.0"}

    def collection(self, name):
        return self._coll


VEC_INDEX = {"type": "vector", "fields": ["embedding_vector"], "params": {"dimension": 384}}


def test_find_all_pairs_uses_approx_near_cosine():
    db = _FakeDB(indexes=[VEC_INDEX])
    db.aql.queue([{"doc1_key": "1", "doc2_key": "2", "similarity": 0.9, "method": METHOD_VECTOR_INDEX}])
    a = ANNAdapter(db=db, collection="customers")
    assert a.method == METHOD_VECTOR_INDEX

    pairs = a.find_all_pairs(similarity_threshold=0.8, limit_per_entity=5)
    assert pairs and pairs[0]["method"] == METHOD_VECTOR_INDEX
    q = db.aql.calls[-1]["query"]
    assert "APPROX_NEAR_COSINE" in q
    assert "dot_product" not in q


def test_find_all_pairs_applies_blocking_and_filters():
    db = _FakeDB(indexes=[VEC_INDEX])
    db.aql.queue([])
    a = ANNAdapter(db=db, collection="customers")
    a.find_all_pairs(
        similarity_threshold=0.7, limit_per_entity=10,
        blocking_field="state", filters={"country": {"equals": "US"}},
    )
    call = db.aql.calls[-1]
    assert "doc2.state == doc1.state" in call["query"]
    assert call["bind_vars"]["filter_country"] == "US"


def test_find_similar_vectors_uses_approx_near_cosine():
    db = _FakeDB(docs={"a": {"_key": "a", "embedding_vector": [1.0, 0.0]}}, indexes=[VEC_INDEX])
    db.aql.queue([{"doc_key": "b", "similarity": 0.95, "method": METHOD_VECTOR_INDEX}])
    a = ANNAdapter(db=db, collection="customers")

    res = a.find_similar_vectors(query_doc_key="a", similarity_threshold=0.7, limit=10)
    assert res and res[0]["doc_key"] == "b"
    q = db.aql.calls[-1]["query"]
    assert "APPROX_NEAR_COSINE" in q
    assert "FILTER doc._key != @exclude_key" in q
