import pytest

from entity_resolution.services.cross_collection_matching_service import CrossCollectionMatchingService


class _FakeAQL:
    def __init__(self):
        self.calls = []
        self._batch_call_count = 0

    def execute(self, query, bind_vars=None, **kwargs):
        q = str(query)
        self.calls.append({"query": q, "bind_vars": dict(bind_vars or {}), "kwargs": dict(kwargs)})

        if "COLLECT WITH COUNT INTO cnt" in q:
            return [3]

        # match batch query (first returns results, second returns empty)
        if "LET candidates" in q and "RETURN {" in q:
            self._batch_call_count += 1
            if self._batch_call_count == 1:
                return [
                    {
                        "source_key": "s1",
                        "target_key": "t1",
                        "confidence": 0.91,
                        "bm25_score": 5.0,
                        "field_scores": {"name": 0.91},
                    }
                ]
            return []

        # clear inferred edges returns two OLD docs
        if "FILTER e.inferred == true" in q and "REMOVE e IN" in q:
            return [{"_key": "1"}, {"_key": "2"}]

        return []


class _FakeEdgeCollection:
    def __init__(self, should_fail: bool = False):
        self.inserted = []
        self.should_fail = should_fail

    def insert_many(self, docs):
        if self.should_fail:
            raise RuntimeError("insert failed")
        self.inserted.extend(list(docs))


class _FakeDB:
    def __init__(self, edge_collection: _FakeEdgeCollection | None = None):
        self.aql = _FakeAQL()
        self._edge = edge_collection or _FakeEdgeCollection()

    def collection(self, name: str):
        if name == "edges":
            return self._edge
        return object()

    def has_collection(self, name: str) -> bool:
        return True

    def create_collection(self, name: str, edge: bool = False):
        return self.collection(name)


def _configured_service(db: _FakeDB, search_view: str | None = None) -> CrossCollectionMatchingService:
    svc = CrossCollectionMatchingService(
        db=db,
        source_collection="source",
        target_collection="target",
        edge_collection="edges",
        search_view=search_view,
        auto_create_edge_collection=True,
    )
    svc.configure_matching(
        source_fields={"name": "company_name"},
        target_fields={"name": "legal_name"},
        field_weights={"name": 1.0},
        blocking_fields=["name"],
        custom_filters={
            "source": {"state": {"equals": "CA", "not_null": True}},
            "target": {"city": {"min_length": 2}},
        },
    )
    return svc


def test_build_count_query_includes_edge_exclusion_and_filters() -> None:
    db = _FakeDB()
    svc = _configured_service(db)
    q = svc._build_count_query()
    assert "FOR s IN @@source_collection" in q
    assert "FOR e IN @@edge_collection" in q
    assert "FILTER s.state != null" in q
    assert 'FILTER s.state == "CA"' in q


def test_build_matching_query_levenshtein_path_includes_target_filters_and_blocking() -> None:
    db = _FakeDB()
    svc = _configured_service(db, search_view=None)
    q = svc._build_matching_query(batch_size=10, offset=0, threshold=0.85, use_bm25=False, bm25_weight=0.2)
    assert "FOR s IN @@source_collection" in q
    assert "FOR t IN @@target_collection" in q
    assert "FILTER LENGTH(t.city) >= 2" in q
    assert "FILTER t.legal_name == s.company_name" in q
    assert "LEVENSHTEIN_DISTANCE" in q


def test_build_matching_query_bm25_path_uses_search_view() -> None:
    db = _FakeDB()
    svc = _configured_service(db, search_view="myview")
    q = svc._build_matching_query(batch_size=10, offset=0, threshold=0.85, use_bm25=True, bm25_weight=0.2)
    assert "FOR t IN @@search_view" in q
    assert "LET bm25_score = BM25(t)" in q


def test_normalize_weights_raises_when_all_zero() -> None:
    db = _FakeDB()
    svc = CrossCollectionMatchingService(db=db, source_collection="source", target_collection="target", edge_collection="edges")
    with pytest.raises(ValueError, match="cannot all be zero"):
        svc._normalize_weights({"a": 0.0, "b": 0.0})


def test_create_edges_from_matches_inserts_edges_and_sets_inferred() -> None:
    edge = _FakeEdgeCollection()
    db = _FakeDB(edge_collection=edge)
    svc = _configured_service(db)

    created = svc._create_edges_from_matches(
        matches=[{"source_key": "s1", "target_key": "t1", "confidence": 0.91234, "field_scores": {"name": 0.9}}],
        mark_as_inferred=True,
    )
    assert created == 1
    assert len(edge.inserted) == 1
    doc = edge.inserted[0]
    assert doc["_from"] == "target/t1"
    assert doc["_to"] == "source/s1"
    assert doc["inferred"] is True
    assert doc["confidence"] == 0.9123
    assert doc["match_details"]["method"] == "cross_collection_matching"


def test_create_edges_from_matches_handles_insert_failure() -> None:
    edge = _FakeEdgeCollection(should_fail=True)
    db = _FakeDB(edge_collection=edge)
    svc = _configured_service(db)

    created = svc._create_edges_from_matches(
        matches=[{"source_key": "s1", "target_key": "t1", "confidence": 0.9}],
        mark_as_inferred=False,
    )
    assert created == 0


def test_match_entities_executes_batches_and_creates_edges() -> None:
    edge = _FakeEdgeCollection()
    db = _FakeDB(edge_collection=edge)
    svc = _configured_service(db, search_view=None)

    stats = svc.match_entities(threshold=0.85, batch_size=10, limit=None, use_bm25=False, mark_as_inferred=True)
    assert stats["edges_created"] == 1
    assert stats["candidates_evaluated"] == 1
    assert stats["batches_processed"] == 1
    assert len(edge.inserted) == 1

    # bind vars used for matching query execution
    match_calls = [c for c in db.aql.calls if c["bind_vars"].get("threshold") == 0.85]
    assert match_calls


def test_clear_inferred_edges_returns_removed_count_and_builds_query() -> None:
    db = _FakeDB()
    svc = _configured_service(db)

    removed = svc.clear_inferred_edges(older_than="2020-01-01T00:00:00")
    assert removed == 2
    last_call = db.aql.calls[-1]
    last = last_call["query"]
    assert "FILTER e.inferred == true" in last
    # older_than must be passed as a bind variable, not interpolated into the
    # query string (AQL injection prevention).
    assert "FILTER e.created_at < @older_than" in last
    assert '"2020-01-01T00:00:00"' not in last
    assert last_call["bind_vars"].get("older_than") == "2020-01-01T00:00:00"

