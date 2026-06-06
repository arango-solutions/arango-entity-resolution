"""
Integration tests for the native-only ANN Adapter (ArangoDB 3.12+).

These require a running ArangoDB with the native vector index available
(APPROX_NEAR_COSINE). Tests skip automatically when the vector index cannot be
created (older version or the experimental vector index is not enabled).
"""

import pytest
import numpy as np
from typing import List

from entity_resolution.similarity.ann_adapter import (
    ANNAdapter,
    VectorSearchUnavailableError,
)


@pytest.fixture
def test_collection_name():
    return "test_ann_adapter"


@pytest.fixture
def setup_test_data(db_connection, test_collection_name):
    """Create a test collection with deterministic clustered embeddings."""
    collection_name = test_collection_name
    if db_connection.has_collection(collection_name):
        db_connection.delete_collection(collection_name)
    collection = db_connection.create_collection(collection_name)

    rng = np.random.RandomState(42)
    dim = 32
    centers = {"A": rng.normal(size=dim), "B": rng.normal(size=dim), "C": rng.normal(size=dim)}

    def normalize(vec: np.ndarray) -> List[float]:
        norm = np.linalg.norm(vec)
        return (vec / norm).tolist() if norm else vec.tolist()

    docs = []
    for i in range(30):
        grp = ["A", "B", "C"][i % 3]
        emb = normalize(centers[grp] + rng.normal(scale=0.05, size=dim))
        docs.append({"_key": f"d{i}", "category": grp, "embedding_vector": emb})
    collection.import_bulk(docs)

    yield collection_name

    if db_connection.has_collection(collection_name):
        db_connection.delete_collection(collection_name)


def _native_adapter(db, collection):
    """Return a native ANN adapter (index created), or skip if unavailable."""
    adapter = ANNAdapter(db=db, collection=collection)
    try:
        adapter.ensure_vector_index()
    except VectorSearchUnavailableError as e:
        pytest.skip(f"native vector index unavailable: {e}")
    if not adapter.native_available:
        pytest.skip("native vector index not available")
    return adapter


class TestANNAdapterInit:
    def test_init_defaults(self, db_connection, setup_test_data):
        adapter = ANNAdapter(db=db_connection, collection=setup_test_data)
        assert adapter.collection == setup_test_data
        assert adapter.embedding_field == "embedding_vector"
        assert adapter.method in ("arango_vector_index", "unavailable")

    def test_search_raises_without_index(self, db_connection, setup_test_data):
        adapter = ANNAdapter(db=db_connection, collection=setup_test_data)
        if adapter.native_available:
            pytest.skip("collection already has a vector index")
        with pytest.raises(VectorSearchUnavailableError):
            adapter.find_all_pairs(similarity_threshold=0.5, limit_per_entity=10)


class TestANNAdapterNative:
    def test_find_similar_vectors_by_doc_key_excludes_self(self, db_connection, setup_test_data):
        adapter = _native_adapter(db_connection, setup_test_data)
        results = adapter.find_similar_vectors(
            query_doc_key="d0", similarity_threshold=0.5, limit=10, exclude_self=True
        )
        keys = {r["doc_key"] for r in results}
        assert "d0" not in keys
        assert all(r["similarity"] >= 0.5 for r in results)
        assert all(r["method"] == "arango_vector_index" for r in results)

    def test_find_all_pairs_returns_structured_pairs(self, db_connection, setup_test_data):
        adapter = _native_adapter(db_connection, setup_test_data)
        pairs = adapter.find_all_pairs(similarity_threshold=0.5, limit_per_entity=10)
        for p in pairs:
            assert {"doc1_key", "doc2_key", "similarity", "method"} <= set(p)
            assert p["similarity"] >= 0.5

    def test_threshold_monotonic(self, db_connection, setup_test_data):
        adapter = _native_adapter(db_connection, setup_test_data)
        low = adapter.find_all_pairs(similarity_threshold=0.5, limit_per_entity=20)
        high = adapter.find_all_pairs(similarity_threshold=0.9, limit_per_entity=20)
        assert len(high) <= len(low)


class TestANNAdapterEdgeCases:
    def test_missing_query_vector_and_key(self, db_connection, setup_test_data):
        adapter = _native_adapter(db_connection, setup_test_data)
        with pytest.raises(ValueError, match="Either query_vector or query_doc_key"):
            adapter.find_similar_vectors(similarity_threshold=0.5, limit=10)

    def test_invalid_doc_key_returns_empty(self, db_connection, setup_test_data):
        adapter = _native_adapter(db_connection, setup_test_data)
        results = adapter.find_similar_vectors(
            query_doc_key="nonexistent", similarity_threshold=0.5, limit=10
        )
        assert results == []
