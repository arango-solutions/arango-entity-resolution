"""
Unit tests for SimilarityEdgeService.

These tests are intentionally DB-free (no Docker/Arango required). We use
lightweight fakes to validate edge shaping, deterministic key behavior,
batch insertion behavior, and AQL query construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pytest

from entity_resolution.services.similarity_edge_service import SimilarityEdgeService


class FakeCursor(list):
    """Simple iterable cursor returned from FakeAQL.execute()."""


@dataclass
class FakeAQL:
    last_query: Optional[str] = None
    last_bind_vars: Dict[str, Any] = field(default_factory=dict)
    next_result: Iterable[Dict[str, Any]] = field(default_factory=list)

    def execute(self, query: str, *args: Any, **kwargs: Any) -> FakeCursor:
        self.last_query = query
        self.last_bind_vars = dict(kwargs.get("bind_vars") or {})
        return FakeCursor(self.next_result)


@dataclass
class InsertCall:
    docs: List[Dict[str, Any]]
    overwrite_mode: Optional[str]


@dataclass
class FakeEdgeCollection:
    insert_calls: List[InsertCall] = field(default_factory=list)
    raise_on_call_indexes: set[int] = field(default_factory=set)
    insert_attempts: int = 0

    def insert_many(self, docs: List[Dict[str, Any]], overwrite_mode: Optional[str] = None) -> None:
        call_index = self.insert_attempts
        self.insert_attempts += 1
        if call_index in self.raise_on_call_indexes:
            raise RuntimeError("insert_many failure (simulated)")
        self.insert_calls.append(InsertCall(docs=list(docs), overwrite_mode=overwrite_mode))


@dataclass
class FakeDB:
    """Minimal DB facade used by SimilarityEdgeService."""

    has_collection_value: bool = True
    created_collections: List[Tuple[str, bool]] = field(default_factory=list)
    edge_collection: FakeEdgeCollection = field(default_factory=FakeEdgeCollection)
    aql: FakeAQL = field(default_factory=FakeAQL)
    graph_definitions: List[Dict[str, Any]] = field(default_factory=list)

    def has_collection(self, name: str) -> bool:
        return self.has_collection_value

    def create_collection(self, name: str, edge: bool = False) -> FakeEdgeCollection:
        self.created_collections.append((name, edge))
        return self.edge_collection

    def collection(self, name: str) -> FakeEdgeCollection:
        return self.edge_collection

    def graphs(self) -> List[Dict[str, Any]]:
        return list(self.graph_definitions)


@pytest.fixture
def fake_db() -> FakeDB:
    return FakeDB(has_collection_value=True)


def _flatten_inserted_docs(edge_collection: FakeEdgeCollection) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    for call in edge_collection.insert_calls:
        docs.extend(call.docs)
    return docs


def test_generate_deterministic_key_order_independent(fake_db: FakeDB) -> None:
    svc = SimilarityEdgeService(db=fake_db, edge_collection="similarTo", vertex_collection="v", use_deterministic_keys=True)

    a = "v/1"
    b = "v/2"
    assert svc._generate_deterministic_key(a, b) == svc._generate_deterministic_key(b, a)


def test_create_edges_deterministic_keys_sets_key_and_overwrite_ignore(fake_db: FakeDB) -> None:
    svc = SimilarityEdgeService(db=fake_db, edge_collection="similarTo", vertex_collection="v", use_deterministic_keys=True)

    matches = [("1", "2", 0.98765)]
    created = svc.create_edges(matches, metadata={"method": "unit_test"})

    assert created == 1
    assert len(fake_db.edge_collection.insert_calls) == 1
    call = fake_db.edge_collection.insert_calls[0]
    assert call.overwrite_mode == "ignore"

    docs = call.docs
    assert len(docs) == 1
    edge = docs[0]
    assert edge["_from"] == "v/1"
    assert edge["_to"] == "v/2"
    assert edge["similarity"] == 0.9877  # rounded to 4 decimals
    assert edge["method"] == "unit_test"
    assert "timestamp" in edge
    assert "_key" in edge


def test_create_edges_without_deterministic_keys_uses_no_overwrite_and_no_key() -> None:
    db = FakeDB(has_collection_value=True)
    svc = SimilarityEdgeService(db=db, edge_collection="similarTo", vertex_collection="v", use_deterministic_keys=False)

    created = svc.create_edges([("1", "2", 0.5)])

    assert created == 1
    call = db.edge_collection.insert_calls[0]
    assert call.overwrite_mode is None
    edge = call.docs[0]
    assert "_key" not in edge


def test_create_edges_bidirectional_creates_reverse_edges_with_same_key(fake_db: FakeDB) -> None:
    svc = SimilarityEdgeService(db=fake_db, edge_collection="similarTo", vertex_collection="v", use_deterministic_keys=True)

    created = svc.create_edges([("1", "2", 0.9)], bidirectional=True)
    assert created == 2

    docs = _flatten_inserted_docs(fake_db.edge_collection)
    assert len(docs) == 2
    forward = next(d for d in docs if d["_from"] == "v/1" and d["_to"] == "v/2")
    reverse = next(d for d in docs if d["_from"] == "v/2" and d["_to"] == "v/1")
    assert forward["_key"] == reverse["_key"]


def test_auto_detection_uses_smartgraph_key_format() -> None:
    db = FakeDB(
        has_collection_value=True,
        graph_definitions=[
            {
                "name": "company_graph",
                "edge_definitions": [{"edge_collection": "similarTo"}],
                "options": {"smartGraphAttribute": "tenant_id"},
            }
        ],
    )
    svc = SimilarityEdgeService(
        db=db,
        edge_collection="similarTo",
        vertex_collection="companies",
        use_deterministic_keys=True,
    )

    created = svc.create_edges([("570:1", "571:2", 0.92)])

    assert created == 1
    edge = _flatten_inserted_docs(db.edge_collection)[0]
    assert edge["_key"].startswith("570:")
    assert edge["_key"].endswith(":571")
    assert len(edge["_key"].split(":")[1]) == 32


def test_auto_detection_accepts_live_graph_collection_field_name() -> None:
    db = FakeDB(
        has_collection_value=True,
        graph_definitions=[
            {
                "name": "company_graph",
                "edgeDefinitions": [{"collection": "similarTo", "from": ["companies"], "to": ["companies"]}],
                "smartGraphAttribute": "tenant_id",
            }
        ],
    )
    svc = SimilarityEdgeService(
        db=db,
        edge_collection="similarTo",
        vertex_collection="companies",
        use_deterministic_keys=True,
    )

    created = svc.create_edges([("570:1", "571:2", 0.92)])

    assert created == 1
    edge = _flatten_inserted_docs(db.edge_collection)[0]
    assert edge["_key"].startswith("570:")
    assert edge["_key"].endswith(":571")


def test_auto_detection_accepts_python_arango_smart_metadata() -> None:
    db = FakeDB(
        has_collection_value=True,
        graph_definitions=[
            {
                "name": "company_graph",
                "edge_definitions": [
                    {
                        "edge_collection": "similarTo",
                        "from_vertex_collections": ["companies"],
                        "to_vertex_collections": ["companies"],
                    }
                ],
                "smart": True,
                "smart_field": "tenant_id",
            }
        ],
    )
    svc = SimilarityEdgeService(
        db=db,
        edge_collection="similarTo",
        vertex_collection="companies",
        use_deterministic_keys=True,
    )

    created = svc.create_edges([("570:1", "571:2", 0.92)])

    assert created == 1
    edge = _flatten_inserted_docs(db.edge_collection)[0]
    assert edge["_key"].startswith("570:")
    assert edge["_key"].endswith(":571")


def test_explicit_smartgraph_mode_rejects_non_smartgraph_vertex_keys(fake_db: FakeDB) -> None:
    svc = SimilarityEdgeService(
        db=fake_db,
        edge_collection="similarTo",
        vertex_collection="companies",
        use_deterministic_keys=True,
        deterministic_key_mode="smartgraph",
    )

    with pytest.raises(ValueError, match="SmartGraph deterministic keys require vertex keys"):
        svc.create_edges([("1", "2", 0.92)])


def test_smartgraph_bidirectional_edges_use_direction_aware_keys() -> None:
    db = FakeDB(has_collection_value=True)
    svc = SimilarityEdgeService(
        db=db,
        edge_collection="similarTo",
        vertex_collection="companies",
        use_deterministic_keys=True,
        deterministic_key_mode="smartgraph",
    )

    created = svc.create_edges([("570:1", "571:2", 0.9)], bidirectional=True)

    assert created == 2
    docs = _flatten_inserted_docs(db.edge_collection)
    assert len(docs) == 2
    forward = next(d for d in docs if d["_from"] == "companies/570:1")
    reverse = next(d for d in docs if d["_from"] == "companies/571:2")
    assert forward["_key"].startswith("570:")
    assert forward["_key"].endswith(":571")
    assert reverse["_key"].startswith("571:")
    assert reverse["_key"].endswith(":570")
    assert forward["_key"] != reverse["_key"]


def test_create_edges_handles_batch_insert_exception_and_continues() -> None:
    db = FakeDB(has_collection_value=True)
    db.edge_collection.raise_on_call_indexes = {0}  # fail first batch insert

    svc = SimilarityEdgeService(
        db=db,
        edge_collection="similarTo",
        vertex_collection="v",
        batch_size=1,  # force one match per batch
        use_deterministic_keys=True,
    )

    created = svc.create_edges([("1", "2", 0.8), ("3", "4", 0.7)])

    # First batch fails, second batch succeeds (1 edge)
    assert created == 1
    assert len(db.edge_collection.insert_calls) == 1  # only successful call recorded

    stats = svc.get_statistics()
    assert stats["edges_created"] == 1
    assert stats["batches_processed"] == 1


def test_create_edges_detailed_skips_missing_keys(fake_db: FakeDB) -> None:
    svc = SimilarityEdgeService(db=fake_db, edge_collection="similarTo", vertex_collection="v", use_deterministic_keys=True)

    matches = [
        {"doc1_key": "1", "doc2_key": "2", "similarity": 0.9, "blocking_method": "x"},
        {"doc1_key": "3", "similarity": 0.5},  # missing doc2_key -> skipped
        {"doc2_key": "4", "similarity": 0.5},  # missing doc1_key -> skipped
    ]
    created = svc.create_edges_detailed(matches)

    assert created == 1
    docs = _flatten_inserted_docs(fake_db.edge_collection)
    assert len(docs) == 1
    edge = docs[0]
    assert edge["_from"] == "v/1"
    assert edge["_to"] == "v/2"
    assert edge["similarity"] == 0.9
    assert edge["blocking_method"] == "x"
    assert "_key" in edge


def test_clear_edges_builds_query_with_method_filter_and_returns_removed_count() -> None:
    db = FakeDB(has_collection_value=True)
    db.aql.next_result = [{"_key": "1"}, {"_key": "2"}]

    svc = SimilarityEdgeService(db=db, edge_collection="similarTo", vertex_collection="v")
    removed = svc.clear_edges(method="phone_blocking")

    assert removed == 2
    assert db.aql.last_query is not None
    assert "FOR e IN @@edge_collection" in db.aql.last_query
    # method must be passed as a bind variable, not interpolated (AQL injection
    # prevention).
    assert "FILTER e.method == @method" in db.aql.last_query
    assert '"phone_blocking"' not in db.aql.last_query
    assert db.aql.last_bind_vars.get("method") == "phone_blocking"
    assert "REMOVE e IN @@edge_collection" in db.aql.last_query


def test_clear_edges_builds_query_with_older_than_filter() -> None:
    db = FakeDB(has_collection_value=True)
    db.aql.next_result = []

    svc = SimilarityEdgeService(db=db, edge_collection="similarTo", vertex_collection="v")
    removed = svc.clear_edges(older_than="2026-01-01T00:00:00")

    assert removed == 0
    assert db.aql.last_query is not None
    # older_than must be passed as a bind variable, not interpolated (AQL
    # injection prevention).
    assert "FILTER e.timestamp < @older_than" in db.aql.last_query
    assert '"2026-01-01T00:00:00"' not in db.aql.last_query
    assert db.aql.last_bind_vars.get("older_than") == "2026-01-01T00:00:00"


def test_init_auto_create_collection_false_does_not_create_collection() -> None:
    db = FakeDB(has_collection_value=False)

    _ = SimilarityEdgeService(db=db, edge_collection="similarTo", auto_create_collection=False)

    assert db.created_collections == []

