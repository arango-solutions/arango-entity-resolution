"""
Tests for backward-compatible UI core additions.

Covers:
- FeedbackStore.query_verdicts (pagination, filtering, sorting)
- FeedbackStore.count_by_status
- FeedbackStore.pending_review_count
- ConfigurableERPipeline.run() on_progress callback
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from entity_resolution.reasoning.feedback import FeedbackStore
from entity_resolution.core.configurable_pipeline import ConfigurableERPipeline


# ---------------------------------------------------------------------------
# Fixtures — FeedbackStore
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.has_collection.return_value = True
    db.collection.return_value = MagicMock()
    return db


@pytest.fixture
def store(mock_db):
    return FeedbackStore(mock_db, collection="er_test_feedback")


# ---------------------------------------------------------------------------
# Fixtures — ConfigurableERPipeline (reuse fake config stubs)
# ---------------------------------------------------------------------------

@dataclass
class _BlockingCfg:
    max_block_size: int = 100
    min_block_size: int = 2
    strategy: str = "exact"
    fields: list = field(default_factory=list)
    search_field: Optional[str] = None
    blocking_field: Optional[str] = None
    embedding_field: Optional[str] = None
    similarity_threshold: float = 0.75
    limit_per_entity: int = 20
    num_hash_tables: int = 10
    num_hyperplanes: int = 8
    random_seed: Optional[int] = 42

    def parse_fields(self) -> tuple:
        names = []
        for item in self.fields or []:
            if isinstance(item, str):
                names.append(item.strip())
            elif isinstance(item, dict):
                n = (item.get("name") or item.get("field") or "").strip()
                if n:
                    names.append(n)
        return names, {}


@dataclass
class _SimilarityCfg:
    batch_size: int = 100
    threshold: float = 0.75
    algorithm: str = "jaro_winkler"
    field_weights: dict = field(default_factory=dict)
    transformers: dict = field(default_factory=dict)


@dataclass
class _ActiveLearningCfg:
    enabled: bool = False
    feedback_collection: Optional[str] = None
    refresh_every: int = 100
    model: Optional[str] = None
    low_threshold: float = 0.55
    high_threshold: float = 0.80
    optimizer_target_precision: float = 0.95
    optimizer_min_samples: int = 20


@dataclass
class _ClusteringCfg:
    store_results: bool = True
    min_cluster_size: int = 2


class _FakeConfig:
    def __init__(self, entity_type="company", store_clusters=True, embedding=None):
        self.entity_type = entity_type
        self.collection_name = "customers"
        self.edge_collection = "similarTo"
        self.cluster_collection = "clusters"
        self.blocking = _BlockingCfg()
        self.similarity = _SimilarityCfg()
        self.clustering = _ClusteringCfg(store_results=store_clusters)
        self.active_learning = _ActiveLearningCfg()
        self.embedding = embedding
        self.edges = object()

    def validate(self):
        return []


class _FakeDB:
    pass


# ===================================================================
# FeedbackStore.query_verdicts
# ===================================================================

class TestQueryVerdicts:

    SAMPLE_DOCS = [
        {"_key": "a1", "key_a": "k1", "key_b": "k2", "score": 0.85,
         "decision": "match", "confidence": 0.9, "source": "llm", "ts": 1000},
        {"_key": "a2", "key_a": "k3", "key_b": "k4", "score": 0.40,
         "decision": "no_match", "confidence": 0.95, "source": "llm", "ts": 2000},
        {"_key": "a3", "key_a": "k1", "key_b": "k2", "score": 0.90,
         "decision": "match", "confidence": 1.0, "source": "human", "ts": 3000},
    ]

    def _setup_mock(self, mock_db, count_result, data_result):
        """Configure the mock AQL to return count then data on successive calls."""
        mock_db.aql.execute.side_effect = [iter([count_result]), iter(data_result)]

    @pytest.mark.unit
    def test_no_filters_returns_all(self, store, mock_db):
        self._setup_mock(mock_db, 3, self.SAMPLE_DOCS)

        result = store.query_verdicts()

        assert result["total"] == 3
        assert result["limit"] == 50
        assert result["offset"] == 0
        assert len(result["items"]) == 3
        assert mock_db.aql.execute.call_count == 2

    @pytest.mark.unit
    def test_filter_by_status(self, store, mock_db):
        matches = [d for d in self.SAMPLE_DOCS if d["decision"] == "match"]
        self._setup_mock(mock_db, len(matches), matches)

        result = store.query_verdicts(status="match")

        call_args = mock_db.aql.execute.call_args_list
        count_bind = call_args[0][1]["bind_vars"]
        assert count_bind["status"] == "match"

    @pytest.mark.unit
    def test_filter_by_source(self, store, mock_db):
        humans = [d for d in self.SAMPLE_DOCS if d["source"] == "human"]
        self._setup_mock(mock_db, len(humans), humans)

        result = store.query_verdicts(source="human")

        count_bind = mock_db.aql.execute.call_args_list[0][1]["bind_vars"]
        assert count_bind["source"] == "human"
        assert result["total"] == 1

    @pytest.mark.unit
    def test_filter_by_score_range(self, store, mock_db):
        filtered = [d for d in self.SAMPLE_DOCS if 0.5 <= d["score"] <= 0.9]
        self._setup_mock(mock_db, len(filtered), filtered)

        result = store.query_verdicts(score_min=0.5, score_max=0.9)

        count_bind = mock_db.aql.execute.call_args_list[0][1]["bind_vars"]
        assert count_bind["score_min"] == 0.5
        assert count_bind["score_max"] == 0.9

    @pytest.mark.unit
    def test_sort_desc(self, store, mock_db):
        reversed_docs = list(reversed(self.SAMPLE_DOCS))
        self._setup_mock(mock_db, 3, reversed_docs)

        store.query_verdicts(sort_by="score", sort_order="desc")

        data_query = mock_db.aql.execute.call_args_list[1][0][0]
        assert "SORT doc.score DESC" in data_query

    @pytest.mark.unit
    def test_sort_by_created_at_maps_to_ts(self, store, mock_db):
        self._setup_mock(mock_db, 3, self.SAMPLE_DOCS)

        store.query_verdicts(sort_by="created_at", sort_order="asc")

        data_query = mock_db.aql.execute.call_args_list[1][0][0]
        assert "doc.ts" in data_query

    @pytest.mark.unit
    def test_pagination(self, store, mock_db):
        self._setup_mock(mock_db, 3, [self.SAMPLE_DOCS[1]])

        result = store.query_verdicts(limit=1, offset=1)

        data_bind = mock_db.aql.execute.call_args_list[1][1]["bind_vars"]
        assert data_bind["off"] == 1
        assert data_bind["lim"] == 1
        assert result["limit"] == 1
        assert result["offset"] == 1

    @pytest.mark.unit
    def test_uses_bind_variables_not_interpolation(self, store, mock_db):
        """All filter values must go through bind variables."""
        self._setup_mock(mock_db, 1, [self.SAMPLE_DOCS[0]])

        store.query_verdicts(status="match", score_min=0.5, source="llm")

        for call in mock_db.aql.execute.call_args_list:
            query = call[0][0]
            assert "match" not in query
            assert "0.5" not in query
            assert "'llm'" not in query

    @pytest.mark.unit
    def test_empty_result(self, store, mock_db):
        self._setup_mock(mock_db, 0, [])

        result = store.query_verdicts(status="uncertain")

        assert result["total"] == 0
        assert result["items"] == []


# ===================================================================
# FeedbackStore.count_by_status
# ===================================================================

class TestCountByStatus:

    @pytest.mark.unit
    def test_returns_dict(self, store, mock_db):
        mock_db.aql.execute.return_value = iter([
            {"decision": "match", "count": 5},
            {"decision": "no_match", "count": 3},
            {"decision": "uncertain", "count": 1},
        ])

        result = store.count_by_status()

        assert result == {"match": 5, "no_match": 3, "uncertain": 1}

    @pytest.mark.unit
    def test_empty_collection(self, store, mock_db):
        mock_db.aql.execute.return_value = iter([])

        result = store.count_by_status()

        assert result == {}

    @pytest.mark.unit
    def test_single_decision(self, store, mock_db):
        mock_db.aql.execute.return_value = iter([
            {"decision": "match", "count": 42},
        ])

        result = store.count_by_status()

        assert result == {"match": 42}


# ===================================================================
# FeedbackStore.pending_review_count
# ===================================================================

class TestPendingReviewCount:

    @pytest.mark.unit
    def test_returns_integer(self, store, mock_db):
        mock_db.aql.execute.return_value = iter([7])

        result = store.pending_review_count()

        assert result == 7
        assert isinstance(result, int)

    @pytest.mark.unit
    def test_zero_pending(self, store, mock_db):
        mock_db.aql.execute.return_value = iter([0])

        result = store.pending_review_count()

        assert result == 0

    @pytest.mark.unit
    def test_empty_cursor_returns_zero(self, store, mock_db):
        mock_db.aql.execute.return_value = iter([])

        result = store.pending_review_count()

        assert result == 0

    @pytest.mark.unit
    def test_aql_uses_bind_variables(self, store, mock_db):
        mock_db.aql.execute.return_value = iter([3])

        store.pending_review_count()

        bind_vars = mock_db.aql.execute.call_args[1]["bind_vars"]
        assert "@col" in bind_vars


# ===================================================================
# ConfigurableERPipeline.run() — on_progress callback
# ===================================================================

class TestOnProgressCallback:

    def _make_pipeline(self, monkeypatch, entity_type="company", store_clusters=True):
        cfg = _FakeConfig(entity_type=entity_type, store_clusters=store_clusters)
        pipe = ConfigurableERPipeline(db=_FakeDB(), config=cfg)
        monkeypatch.setattr(pipe, "run_blocking", lambda: [("a", "b")])
        monkeypatch.setattr(pipe, "run_similarity", lambda pairs: [("a", "b", 0.95)])
        monkeypatch.setattr(pipe, "run_edge_creation", lambda matches: 1)
        monkeypatch.setattr(pipe, "run_clustering", lambda: [["a", "b"]])
        return pipe

    @pytest.mark.unit
    def test_on_progress_none_causes_no_error(self, monkeypatch):
        pipe = self._make_pipeline(monkeypatch)
        result = pipe.run(on_progress=None)
        assert result["total_runtime_seconds"] >= 0

    @pytest.mark.unit
    def test_on_progress_default_is_none(self, monkeypatch):
        pipe = self._make_pipeline(monkeypatch)
        result = pipe.run()
        assert result["blocking"]["candidate_pairs"] == 1

    @pytest.mark.unit
    def test_callback_receives_stage_events(self, monkeypatch):
        pipe = self._make_pipeline(monkeypatch)
        events = []

        pipe.run(on_progress=lambda e: events.append(e))

        stage_starts = [e for e in events if e["type"] == "stage_start"]
        stage_completes = [e for e in events if e["type"] == "stage_complete"]

        expected_stages = {"blocking", "similarity", "edges", "clustering"}
        assert {e["stage"] for e in stage_starts} == expected_stages
        assert {e["stage"] for e in stage_completes} == expected_stages

    @pytest.mark.unit
    def test_events_have_required_keys(self, monkeypatch):
        pipe = self._make_pipeline(monkeypatch)
        events = []

        pipe.run(on_progress=lambda e: events.append(e))

        for e in events:
            assert "type" in e
            assert "timestamp" in e
            if e["type"] == "stage_start":
                assert "stage" in e
            elif e["type"] == "stage_complete":
                assert "stage" in e
                assert "result" in e
            elif e["type"] == "pipeline_complete":
                assert "total_runtime_seconds" in e
                assert "summary" in e

    @pytest.mark.unit
    def test_pipeline_complete_event_emitted(self, monkeypatch):
        pipe = self._make_pipeline(monkeypatch)
        events = []

        pipe.run(on_progress=lambda e: events.append(e))

        complete_events = [e for e in events if e["type"] == "pipeline_complete"]
        assert len(complete_events) == 1
        summary = complete_events[0]["summary"]
        assert summary["candidate_pairs"] == 1
        assert summary["matches_found"] == 1
        assert summary["edges_created"] == 1
        assert summary["clusters_found"] == 1

    @pytest.mark.unit
    def test_stage_complete_includes_result(self, monkeypatch):
        pipe = self._make_pipeline(monkeypatch)
        events = []

        pipe.run(on_progress=lambda e: events.append(e))

        blocking_complete = next(
            e for e in events
            if e["type"] == "stage_complete" and e["stage"] == "blocking"
        )
        assert blocking_complete["result"]["candidate_pairs"] == 1

    @pytest.mark.unit
    def test_timestamps_are_iso_format(self, monkeypatch):
        pipe = self._make_pipeline(monkeypatch)
        events = []

        pipe.run(on_progress=lambda e: events.append(e))

        from datetime import datetime as dt
        for e in events:
            dt.fromisoformat(e["timestamp"])

    @pytest.mark.unit
    def test_no_clustering_when_disabled(self, monkeypatch):
        pipe = self._make_pipeline(monkeypatch, store_clusters=False)
        events = []

        pipe.run(on_progress=lambda e: events.append(e))

        clustering_complete = next(
            e for e in events
            if e["type"] == "stage_complete" and e["stage"] == "clustering"
        )
        assert clustering_complete["result"]["clusters_found"] == 0


# ===================================================================
# Backward compatibility — existing API unchanged
# ===================================================================

class TestBackwardCompatibility:

    @pytest.mark.unit
    def test_feedbackstore_existing_methods_unchanged(self, store, mock_db):
        """Existing methods still work with no changes."""
        mock_db.aql.execute.return_value = iter([
            {"decision": "match", "score": 0.9},
        ])
        verdicts = store.all_verdicts()
        assert len(verdicts) == 1

    @pytest.mark.unit
    def test_pipeline_run_returns_same_structure_without_callback(self, monkeypatch):
        cfg = _FakeConfig()
        pipe = ConfigurableERPipeline(db=_FakeDB(), config=cfg)
        monkeypatch.setattr(pipe, "run_blocking", lambda: [("a", "b")])
        monkeypatch.setattr(pipe, "run_similarity", lambda pairs: [("a", "b", 0.9)])
        monkeypatch.setattr(pipe, "run_edge_creation", lambda matches: 1)
        monkeypatch.setattr(pipe, "run_clustering", lambda: [["a", "b"]])

        result = pipe.run()

        assert "blocking" in result
        assert "similarity" in result
        assert "edges" in result
        assert "clustering" in result
        assert "total_runtime_seconds" in result
        assert "embedding" in result
