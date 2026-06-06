"""Unit tests for the native-only ANNAdapter (detection, errors, index mgmt).

ANNAdapter has no brute-force fallback: vector search requires ArangoDB 3.12+
with a vector index, else it raises VectorSearchUnavailableError. These tests
use a fake ArangoDB and do not require a running server.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from entity_resolution.similarity.ann_adapter import (
    ANNAdapter,
    VectorSearchUnavailableError,
    METHOD_VECTOR_INDEX,
    METHOD_UNAVAILABLE,
)


class _FakeColl:
    def __init__(self, docs=None, indexes=None):
        self._docs = docs or {}
        self._indexes = list(indexes or [])
        self.added: List[Dict[str, Any]] = []

    def indexes(self):
        return self._indexes

    def count(self):
        return len(self._docs)

    def get(self, key):
        return self._docs.get(key)

    def add_index(self, definition):
        self._indexes.append(definition)
        self.added.append(definition)
        return {"id": "idx/1", **definition}


class _FakeAQL:
    def __init__(self, dim=384):
        self.calls: List[Dict[str, Any]] = []
        self.dim = dim
        self.rows: List[List[Dict[str, Any]]] = []

    def queue(self, rows):
        self.rows.append(rows)

    def execute(self, query, bind_vars=None, **kwargs):
        q = str(query)
        self.calls.append({"query": q, "bind_vars": dict(bind_vars or {})})
        if "RETURN LENGTH(" in q:
            return iter([self.dim])
        return list(self.rows.pop(0) if self.rows else [])


class _FakeDB:
    def __init__(self, version="3.12.0", docs=None, indexes=None, dim=384):
        self._version = version
        self._coll = _FakeColl(docs, indexes)
        self.aql = _FakeAQL(dim=dim)

    def properties(self):
        return {"version": self._version}

    def collection(self, name):
        return self._coll


VEC_INDEX = {"type": "vector", "fields": ["embedding_vector"], "params": {"dimension": 384}}


# --- detection -------------------------------------------------------------

def test_native_available_with_index_on_312():
    a = ANNAdapter(db=_FakeDB(version="3.12.0", indexes=[VEC_INDEX]), collection="customers")
    assert a.native_available is True
    assert a.method == METHOD_VECTOR_INDEX
    assert a.arango_version == (3, 12, 0)


def test_unavailable_without_index():
    a = ANNAdapter(db=_FakeDB(version="3.12.0", indexes=[]), collection="customers")
    assert a.native_available is False
    assert a.method == METHOD_UNAVAILABLE


def test_unavailable_old_version_even_with_index():
    a = ANNAdapter(db=_FakeDB(version="3.11.5", indexes=[VEC_INDEX]), collection="customers")
    assert a.native_available is False
    assert a.method == METHOD_UNAVAILABLE


# --- hard gate (no brute-force fallback) -----------------------------------

def test_find_all_pairs_raises_when_unavailable():
    a = ANNAdapter(db=_FakeDB(version="3.11.0", indexes=[]), collection="customers")
    with pytest.raises(VectorSearchUnavailableError):
        a.find_all_pairs()


def test_find_similar_vectors_raises_when_unavailable():
    a = ANNAdapter(db=_FakeDB(version="3.11.0", indexes=[]), collection="customers")
    with pytest.raises(VectorSearchUnavailableError):
        a.find_similar_vectors(query_vector=[1.0, 0.0])


def test_find_similar_vectors_requires_vector_or_doc_key():
    a = ANNAdapter(db=_FakeDB(version="3.12.0", indexes=[VEC_INDEX]), collection="customers")
    with pytest.raises(ValueError):
        a.find_similar_vectors(query_vector=None, query_doc_key=None)


# --- index management ------------------------------------------------------

def test_ensure_vector_index_creates_with_detected_dimension():
    db = _FakeDB(version="3.12.0", docs={"a": {"_key": "a"}, "b": {"_key": "b"}}, indexes=[], dim=384)
    a = ANNAdapter(db=db, collection="customers")
    assert a.native_available is False

    result = a.ensure_vector_index()
    assert result["created"] is True
    assert result["dimension"] == 384
    assert result["n_lists"] >= 1
    assert a.native_available is True
    created = db.collection("customers").added[-1]
    assert created["type"] == "vector"
    assert created["fields"] == ["embedding_vector"]
    assert created["params"]["dimension"] == 384
    assert created["params"]["metric"] == "cosine"
    # IVF params required by ArangoDB's vector index (omitting these can stall creation).
    assert created["params"]["trainingIterations"] == 25
    assert created["params"]["defaultNProbe"] == min(created["params"]["nLists"], 64)


def test_ensure_vector_index_noop_when_exists():
    a = ANNAdapter(db=_FakeDB(version="3.12.0", indexes=[VEC_INDEX]), collection="customers")
    assert a.ensure_vector_index()["created"] is False


def test_ensure_vector_index_rejects_old_version():
    a = ANNAdapter(db=_FakeDB(version="3.11.0", docs={"a": {"_key": "a"}}, indexes=[]), collection="customers")
    with pytest.raises(VectorSearchUnavailableError):
        a.ensure_vector_index()


def test_n_lists_clamped_to_doc_count():
    a = ANNAdapter(db=_FakeDB(version="3.12.0", docs={"a": {"_key": "a"}}, indexes=[], dim=8), collection="customers")
    assert a.ensure_vector_index(n_lists=999)["n_lists"] == 1


def test_ensure_vector_index_converts_disabled_feature_error():
    """If the server lacks --experimental-vector-index, surface a clear error."""
    db = _FakeDB(version="3.12.0", docs={"a": {"_key": "a"}}, indexes=[], dim=8)

    def _raise(definition):
        raise RuntimeError(
            "[HTTP 400][ERR 10] vector index feature is not enabled. "
            "Run ArangoDB with `--experimental-vector-index` flag turned on."
        )

    db.collection("customers").add_index = _raise
    a = ANNAdapter(db=db, collection="customers")
    with pytest.raises(VectorSearchUnavailableError, match="experimental-vector-index"):
        a.ensure_vector_index()
