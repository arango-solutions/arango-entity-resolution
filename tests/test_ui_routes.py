"""Integration tests for FastAPI UI backend routes.

Uses a mock ArangoDB database handle so no real database is needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from entity_resolution.ui.app import create_app


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def mock_db():
    """Minimal mock of a python-arango StandardDatabase."""
    db = MagicMock()
    db.name = "_system"
    db.has_collection.return_value = True

    mock_coll = MagicMock()
    mock_coll.count.return_value = 42
    mock_coll.get.return_value = None
    mock_coll.insert.return_value = {"_key": "new"}
    db.collection.return_value = mock_coll

    db.collections.return_value = [
        {"name": "customers", "system": False, "type": 2},
        {"name": "similarTo", "system": False, "type": 3},
        {"name": "_system", "system": True, "type": 2},
    ]

    db.aql = MagicMock()
    db.aql.execute.return_value = iter([])

    db.create_collection.return_value = mock_coll

    return db


@pytest.fixture
def app(mock_db):
    return create_app(db=mock_db)


@pytest.fixture
def client(app):
    return TestClient(app)


# ===================================================================
# Health
# ===================================================================

class TestHealth:

    def test_health_returns_200(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "version" in data
        assert data["status"] == "ok"


# ===================================================================
# Collections
# ===================================================================

class TestCollections:

    def test_list_collections(self, client, mock_db):
        resp = client.get("/api/collections")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        names = [c["name"] for c in data]
        assert "customers" in names
        assert "similarTo" in names
        assert "_system" not in names

    def test_collection_types(self, client):
        resp = client.get("/api/collections")
        data = resp.json()
        by_name = {c["name"]: c for c in data}
        assert by_name["customers"]["type"] == "document"
        assert by_name["similarTo"]["type"] == "edge"

    @patch("entity_resolution.mcp.tools.advisor.run_profile_dataset")
    @patch("entity_resolution.utils.validation.validate_collection_name")
    def test_profile_collection(self, mock_validate, mock_profile, client):
        mock_profile.return_value = {"field_count": 5, "sample_size": 100}
        resp = client.get("/api/collections/customers/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["field_count"] == 5

    @patch("entity_resolution.mcp.resources.collections.get_collection_summary")
    @patch("entity_resolution.utils.validation.validate_collection_name")
    def test_collection_sample(self, mock_validate, mock_summary, client):
        import json
        mock_summary.return_value = json.dumps({"schema": {}, "samples": []})
        resp = client.get("/api/collections/customers/sample")
        assert resp.status_code == 200
        data = resp.json()
        assert "schema" in data


# ===================================================================
# Clusters
# ===================================================================

class TestClusters:

    def test_list_clusters_empty(self, client, mock_db):
        mock_db.has_collection.return_value = False
        resp = client.get("/api/clusters/customers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["clusters"] == []
        assert data["total"] == 0

    def test_list_clusters_with_data(self, client, mock_db):
        mock_db.has_collection.return_value = True
        cluster_data = [
            {
                "cluster_id": "c1",
                "members": ["a", "b"],
                "size": 2,
                "representative": "a",
                "edge_count": 1,
                "average_similarity": 0.9,
                "min_similarity": 0.9,
                "max_similarity": 0.9,
                "density": 1.0,
                "quality_score": 0.95,
            }
        ]
        mock_db.aql.execute.side_effect = [iter([1]), iter(cluster_data)]
        resp = client.get("/api/clusters/customers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["clusters"]) == 1
        assert data["clusters"][0]["cluster_id"] == "c1"

    def test_cluster_detail_not_found(self, client, mock_db):
        mock_db.has_collection.return_value = True
        mock_db.collection.return_value.get.return_value = None
        resp = client.get("/api/clusters/customers/nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data

    def test_cluster_detail_found(self, client, mock_db):
        mock_db.has_collection.return_value = True
        mock_db.collection.return_value.get.return_value = {
            "_key": "c1",
            "members": ["k1", "k2"],
            "representative": "k1",
            "quality_score": 0.9,
            "density": 1.0,
            "average_similarity": 0.85,
        }
        resp = client.get("/api/clusters/customers/c1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cluster_id"] == "c1"
        assert data["size"] == 2

    def test_cluster_graph_returns_nodes_edges(self, client, mock_db):
        mock_db.has_collection.return_value = True
        mock_db.collection.return_value.get.side_effect = [
            {"_key": "c1", "members": ["k1", "k2"]},
            {"_key": "k1", "name": "Alice"},
            {"_key": "k2", "name": "Bob"},
        ]
        mock_db.aql.execute.return_value = iter([
            {"source": "customers/k1", "target": "customers/k2", "similarity": 0.9, "method": "jw"},
        ])
        resp = client.get("/api/clusters/customers/c1/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 2

    def test_cluster_graph_missing_cluster(self, client, mock_db):
        mock_db.has_collection.return_value = True
        mock_db.collection.return_value.get.return_value = None
        resp = client.get("/api/clusters/customers/missing/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert data["nodes"] == []
        assert data["edges"] == []

    def test_cluster_stats_no_collection(self, client, mock_db):
        mock_db.has_collection.return_value = False
        resp = client.get("/api/clusters/customers/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_clusters"] == 0


# ===================================================================
# Review
# ===================================================================

class TestReview:

    @patch("entity_resolution.reasoning.feedback.FeedbackStore")
    @patch("entity_resolution.utils.validation.validate_collection_name")
    def test_list_verdicts_empty(self, mock_val, mock_fs_cls, client, mock_db):
        mock_db.has_collection.return_value = False
        resp = client.get("/api/review/customers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdicts"] == []
        assert data["total"] == 0

    @patch("entity_resolution.reasoning.feedback.FeedbackStore")
    @patch("entity_resolution.utils.validation.validate_collection_name")
    def test_list_verdicts_with_data(self, mock_val, mock_fs_cls, client, mock_db):
        mock_db.has_collection.return_value = True
        verdicts_list = [
            {"decision": "match", "score": 0.9},
            {"decision": "no_match", "score": 0.3},
        ]
        store_inst = MagicMock()
        # query_verdicts returns a paginated dict (see FeedbackStore.query_verdicts).
        store_inst.query_verdicts.return_value = {
            "items": list(verdicts_list),
            "total": len(verdicts_list),
            "limit": 50,
            "offset": 0,
        }
        mock_fs_cls.return_value = store_inst
        resp = client.get("/api/review/customers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["verdicts"]) == 2

    @patch("entity_resolution.reasoning.feedback.FeedbackStore")
    @patch("entity_resolution.utils.validation.validate_collection_name")
    def test_list_verdicts_forwards_correct_kwargs(self, mock_val, mock_fs_cls, client, mock_db):
        """Regression: the route must use FeedbackStore.query_verdicts' real signature."""
        mock_db.has_collection.return_value = True
        store_inst = MagicMock()
        store_inst.query_verdicts.return_value = {"items": [], "total": 0, "limit": 50, "offset": 0}
        mock_fs_cls.return_value = store_inst
        resp = client.get(
            "/api/review/customers?status=match&min_score=0.5&max_score=0.9&source=llm"
        )
        assert resp.status_code == 200
        kwargs = store_inst.query_verdicts.call_args.kwargs
        assert kwargs["status"] == "match"
        assert kwargs["score_min"] == 0.5
        assert kwargs["score_max"] == 0.9
        assert kwargs["source"] == "llm"

    @patch("entity_resolution.reasoning.feedback.FeedbackStore")
    @patch("entity_resolution.utils.validation.validate_collection_name")
    def test_verdict_stats(self, mock_val, mock_fs_cls, client, mock_db):
        mock_db.has_collection.return_value = True
        store_inst = MagicMock()
        store_inst.stats.return_value = {
            "by_decision": [{"decision": "match", "count": 5}],
            "total": 5,
        }
        mock_fs_cls.return_value = store_inst
        resp = client.get("/api/review/customers/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "by_decision" in data
        assert "total" in data

    @patch("entity_resolution.reasoning.feedback.FeedbackStore")
    @patch("entity_resolution.utils.validation.validate_collection_name")
    def test_submit_verdict_success(self, mock_val, mock_fs_cls, client, mock_db):
        store_inst = MagicMock()
        store_inst.record_human_correction.return_value = "verdict-key-abc"
        mock_fs_cls.return_value = store_inst
        resp = client.post(
            "/api/review/customers/pair/k1/k2/verdict",
            json={"decision": "match", "confidence": 0.95},
        )
        assert resp.status_code == 200

    @patch("entity_resolution.reasoning.feedback.FeedbackStore")
    @patch("entity_resolution.utils.validation.validate_collection_name")
    def test_submit_verdict_records_reviewer(self, mock_val, mock_fs_cls, client, mock_db):
        store_inst = MagicMock()
        store_inst.record_human_correction.return_value = "verdict-key-abc"
        mock_fs_cls.return_value = store_inst
        resp = client.post(
            "/api/review/customers/pair/k1/k2/verdict",
            json={"decision": "match"},
            headers={"X-Reviewer": "alice"},
        )
        assert resp.status_code == 200
        # The resolved reviewer is attributed to the persisted verdict.
        assert store_inst.record_human_correction.call_args.kwargs["reviewer"] == "alice"
        data = resp.json()
        assert data["status"] == "ok"
        assert "verdict_key" in data

    def test_submit_verdict_invalid_decision(self, client):
        resp = client.post(
            "/api/review/customers/pair/k1/k2/verdict",
            json={"decision": "maybe"},
        )
        assert resp.status_code == 422

    def test_submit_verdict_missing_body(self, client):
        resp = client.post("/api/review/customers/pair/k1/k2/verdict")
        assert resp.status_code == 422

    @patch("entity_resolution.reasoning.feedback.FeedbackStore")
    @patch("entity_resolution.utils.validation.validate_collection_name")
    def test_submit_verdict_readonly(self, mock_val, mock_fs_cls, mock_db):
        readonly_app = create_app(db=mock_db, readonly=True)
        readonly_client = TestClient(readonly_app)
        resp = readonly_client.post(
            "/api/review/customers/pair/k1/k2/verdict",
            json={"decision": "match"},
        )
        assert resp.status_code == 403

    @patch("entity_resolution.mcp.tools.entity.run_explain_match")
    @patch("entity_resolution.utils.validation.validate_collection_name")
    def test_pair_comparison(self, mock_val, mock_explain, client, mock_db):
        mock_explain.return_value = {"overall_score": 0.85, "field_scores": {}}
        mock_db.collection.return_value.get.side_effect = [
            {"_key": "k1", "name": "Alice"},
            {"_key": "k2", "name": "Alicia"},
        ]
        resp = client.get("/api/review/customers/pair/k1/k2")
        assert resp.status_code == 200
        data = resp.json()
        assert "explanation" in data
        assert "doc_a" in data
        assert "doc_b" in data


# ===================================================================
# Pipeline
# ===================================================================

class TestPipeline:

    @patch("entity_resolution.utils.pipeline_utils.count_inferred_edges")
    @patch("entity_resolution.utils.validation.validate_collection_name")
    def test_pipeline_status(self, mock_val, mock_count, client, mock_db):
        mock_count.return_value = {"total": 100, "by_method": {"jaro_winkler": 100}}
        mock_db.has_collection.return_value = True
        mock_db.collection.return_value.count.return_value = 500
        resp = client.get("/api/pipeline/status/customers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["collection"] == "customers"
        assert "total_documents" in data
        assert "edge_stats" in data
        assert "cluster_count" in data

    def test_pipeline_history_empty(self, client, mock_db):
        mock_db.has_collection.return_value = False
        resp = client.get("/api/pipeline/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["runs"] == []
        assert data["total"] == 0

    def test_pipeline_run_returns_run_id(self, client, mock_db):
        mock_db.has_collection.return_value = False
        resp = client.post("/api/pipeline/run", json={"config": {"collection": "test"}})
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "running"

    def test_pipeline_run_readonly(self, mock_db):
        readonly_app = create_app(db=mock_db, readonly=True)
        readonly_client = TestClient(readonly_app)
        resp = readonly_client.post(
            "/api/pipeline/run", json={"config": {"collection": "test"}}
        )
        assert resp.status_code == 403


# ===================================================================
# Golden
# ===================================================================

class TestGolden:

    @patch("entity_resolution.mcp.tools.cluster.run_merge_entities")
    @patch("entity_resolution.utils.validation.validate_collection_name")
    def test_preview_merge(self, mock_val, mock_merge, client, mock_db):
        mock_merge.return_value = {
            "golden_record": {"name": "Acme Inc"},
            "source_records": [{"_key": "k1"}, {"_key": "k2"}],
        }
        resp = client.post(
            "/api/golden/customers/preview",
            json={"entity_keys": ["k1", "k2"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "golden_record" in data

    def test_preview_merge_empty_keys(self, client):
        resp = client.post(
            "/api/golden/customers/preview",
            json={"entity_keys": []},
        )
        assert resp.status_code == 422

    def test_get_golden_record_not_found(self, client, mock_db):
        mock_db.has_collection.return_value = True
        mock_db.collection.return_value.get.return_value = None
        resp = client.get("/api/golden/customers/k1")
        assert resp.status_code == 404

    def test_get_golden_record_found(self, client, mock_db):
        mock_db.has_collection.return_value = True
        mock_db.collection.return_value.get.return_value = {
            "_key": "g1", "name": "Acme", "_merged_keys": ["k1", "k2"]
        }
        resp = client.get("/api/golden/customers/g1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["_key"] == "g1"

    def test_get_golden_record_no_collection(self, client, mock_db):
        mock_db.has_collection.return_value = False
        resp = client.get("/api/golden/customers/k1")
        assert resp.status_code == 404

    def test_golden_provenance(self, client, mock_db):
        mock_db.has_collection.return_value = True
        mock_db.collection.return_value.get.side_effect = [
            {"_key": "g1", "name": "Acme", "_merged_keys": ["k1", "k2"]},
            {"_key": "k1", "name": "Acme Corp"},
            {"_key": "k2", "name": "ACME Inc"},
        ]
        resp = client.get("/api/golden/customers/g1/provenance")
        assert resp.status_code == 200
        data = resp.json()
        assert "golden_record" in data
        assert "source_records" in data
        assert "merged_keys" in data


# ===================================================================
# Config
# ===================================================================

class TestConfig:

    @patch("entity_resolution.config.er_config.ERPipelineConfig")
    def test_validate_config_valid(self, mock_cfg_cls, client):
        mock_instance = MagicMock()
        mock_instance.validate.return_value = []
        mock_cfg_cls.from_dict.return_value = mock_instance
        resp = client.post(
            "/api/config/validate",
            json={"config": {"entity_type": "person", "collection": "test"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []

    @patch("entity_resolution.config.er_config.ERPipelineConfig")
    def test_validate_config_invalid(self, mock_cfg_cls, client):
        mock_cfg_cls.from_dict.side_effect = ValueError("Missing entity_type")
        resp = client.post("/api/config/validate", json={"config": {}})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_validate_config_missing_body(self, client):
        resp = client.post("/api/config/validate")
        assert resp.status_code == 422

    @patch("entity_resolution.mcp.tools.advisor.run_recommend_resolution_strategy")
    def test_recommend_strategy(self, mock_recommend, client):
        mock_recommend.return_value = {"strategy": "hybrid", "rationale": "..."}
        resp = client.post(
            "/api/config/recommend",
            json={
                "profile": {"fields": ["name"]},
                "objective_profile": {"goal": "precision"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["strategy"] == "hybrid"

    @patch("entity_resolution.mcp.tools.advisor.run_recommend_blocking_candidates")
    def test_recommend_blocking(self, mock_blocking, client):
        mock_blocking.return_value = {"candidates": [{"field": "email", "score": 0.9}]}
        resp = client.post(
            "/api/config/blocking",
            json={"profile": {"fields": ["email", "name"]}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "candidates" in data

    @patch("entity_resolution.mcp.tools.advisor.run_simulate_pipeline_variants")
    def test_simulate_variants(self, mock_simulate, client):
        mock_simulate.return_value = {"comparison": []}
        resp = client.post(
            "/api/config/simulate",
            json={"variants": [{"a": 1}, {"b": 2}]},
        )
        assert resp.status_code == 200

    @patch("entity_resolution.mcp.tools.advisor.run_export_recommended_config")
    def test_export_config(self, mock_export, client):
        mock_export.return_value = {"output": "...yaml..."}
        resp = client.post(
            "/api/config/export",
            json={"recommendation": {"strategy": "exact"}},
        )
        assert resp.status_code == 200


# ===================================================================
# Resolve
# ===================================================================

class TestResolve:

    @patch("entity_resolution.mcp.tools.entity.run_resolve_entity")
    @patch("entity_resolution.utils.validation.validate_collection_name")
    def test_resolve_entity(self, mock_val, mock_resolve, client, mock_db):
        mock_resolve.return_value = [
            {"_key": "k1", "score": 0.92, "name": "Acme"},
        ]
        resp = client.post(
            "/api/resolve/customers",
            json={"record": {"name": "Acme Corp"}, "fields": ["name"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["score"] == 0.92

    def test_resolve_missing_record(self, client):
        resp = client.post(
            "/api/resolve/customers",
            json={"fields": ["name"]},
        )
        assert resp.status_code == 422

    def test_resolve_missing_fields(self, client):
        resp = client.post(
            "/api/resolve/customers",
            json={"record": {"name": "test"}},
        )
        assert resp.status_code == 422

    @patch("entity_resolution.mcp.tools.entity.run_resolve_entity")
    @patch("entity_resolution.utils.validation.validate_collection_name")
    def test_resolve_with_custom_threshold(self, mock_val, mock_resolve, client, mock_db):
        mock_resolve.return_value = []
        resp = client.post(
            "/api/resolve/customers",
            json={
                "record": {"name": "Test"},
                "fields": ["name"],
                "confidence_threshold": 0.5,
                "top_k": 3,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ===================================================================
# Export
# ===================================================================

class TestExport:

    @patch("entity_resolution.services.cluster_export_service.ClusterExportService")
    @patch("entity_resolution.utils.validation.validate_collection_name")
    def test_export_clusters(self, mock_val, mock_svc_cls, client, mock_db):
        mock_svc = MagicMock()
        mock_svc.export.return_value = {
            "json": "/tmp/out.json",
            "csv": "/tmp/out.csv",
            "clusters_exported": 10,
        }
        mock_svc_cls.return_value = mock_svc
        resp = client.post(
            "/api/export/customers",
            json={"output_dir": "/tmp/out"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["clusters_exported"] == 10
        assert "output_files" in data

    def test_export_readonly(self, mock_db):
        readonly_app = create_app(db=mock_db, readonly=True)
        readonly_client = TestClient(readonly_app)
        resp = readonly_client.post(
            "/api/export/customers",
            json={"output_dir": "/tmp/out"},
        )
        assert resp.status_code == 403

    def test_download_invalid_filename(self, client):
        resp = client.get("/api/export/customers/download/bad@file.json")
        assert resp.status_code == 400

    def test_download_file_not_found(self, client):
        resp = client.get("/api/export/customers/download/does_not_exist.json")
        assert resp.status_code == 404


# ===================================================================
# Pipeline progress WebSocket
# ===================================================================

class _WsColl:
    def __init__(self, doc):
        self._doc = doc

    def get(self, key):
        return self._doc


class _WsDB:
    def __init__(self, doc):
        self._doc = doc

    def has_collection(self, name):
        return True

    def collection(self, name):
        return _WsColl(self._doc)


class TestPipelineWebSocket:

    def test_ws_streams_stage_events_then_completion(self):
        run_doc = {
            "_key": "r1",
            "status": "completed",
            "result": {"clustering": {"clusters_found": 2}},
            "progress_events": [
                {"type": "stage_start", "stage": "blocking"},
                {"type": "stage_complete", "stage": "blocking", "result": {"candidate_pairs": 5}},
                # The pipeline also emits a pipeline_complete event; the WS must
                # NOT forward it (it generates its own terminal event).
                {"type": "pipeline_complete", "summary": {}},
            ],
        }
        client = TestClient(create_app(db=_WsDB(run_doc)))
        with client.websocket_connect("/ws/pipeline/r1") as ws:
            msgs = [ws.receive_json() for _ in range(3)]
        types = [m["type"] for m in msgs]
        assert types == ["stage_start", "stage_complete", "pipeline_complete"]
        assert msgs[1]["stage"] == "blocking"
        assert msgs[2]["summary"] == {"clustering": {"clusters_found": 2}}

    def test_ws_emits_failure(self):
        run_doc = {"_key": "r2", "status": "failed", "error": "boom", "progress_events": []}
        client = TestClient(create_app(db=_WsDB(run_doc)))
        with client.websocket_connect("/ws/pipeline/r2") as ws:
            msg = ws.receive_json()
        assert msg["type"] == "pipeline_failed"
        assert msg["error"] == "boom"


# ===================================================================
# Curation audit (plan 2.0)
# ===================================================================

class TestCuration:

    def test_history_returns_entries(self, client, mock_db):
        mock_db.aql.execute.return_value = iter(
            [{"actor": "alice", "action": "verdict", "entity_key": "k1"}]
        )
        resp = client.get("/api/curation/customers/history/k1?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert data["entries"][0]["actor"] == "alice"

    def test_history_rejects_bad_collection(self, client):
        resp = client.get("/api/curation/bad@name/history/k1")
        assert resp.status_code in (400, 422)


# ===================================================================
# Threshold tuner metrics (plan 2.1)
# ===================================================================

class TestThresholdTuner:

    def test_score_distribution(self, client, mock_db):
        mock_db.aql.execute.return_value = iter(
            [{"lo": 0.7, "hi": 0.75, "count": 3}, {"lo": 0.95, "hi": 1.0, "count": 1}]
        )
        resp = client.get("/api/metrics/customers/score-distribution?bucket=0.05")
        assert resp.status_code == 200
        data = resp.json()
        assert data["bucket"] == 0.05
        assert data["buckets"][0]["count"] == 3

    def test_boundary_pairs(self, client, mock_db):
        mock_db.aql.execute.return_value = iter(
            [{"key_a": "c", "key_b": "d", "score": 0.7}]
        )
        resp = client.get("/api/metrics/customers/boundary-pairs?score=0.68&window=0.05")
        assert resp.status_code == 200
        assert resp.json()["pairs"][0]["key_a"] == "c"

    def test_apply_threshold_no_run_404(self, client, mock_db):
        mock_db.aql.execute.return_value = iter([])  # no runs
        resp = client.post(
            "/api/metrics/customers/apply-threshold",
            json={"low_threshold": 0.5, "high_threshold": 0.8},
        )
        assert resp.status_code == 404

    def test_apply_threshold_success(self, client, mock_db):
        run_doc = {
            "_key": "run1",
            "started_at": 1.0,
            "config": {"entity_resolution": {"collection": "customers",
                                              "similarity": {}, "active_learning": {}}},
        }
        mock_db.aql.execute.return_value = iter([run_doc])
        resp = client.post(
            "/api/metrics/customers/apply-threshold",
            json={"low_threshold": 0.5, "high_threshold": 0.8},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == "run1"
        assert data["thresholds"]["low_threshold"] == 0.5
        assert data["thresholds"]["high_threshold"] == 0.8

    def test_apply_threshold_readonly(self, mock_db):
        readonly_app = create_app(db=mock_db, readonly=True)
        readonly_client = TestClient(readonly_app)
        resp = readonly_client.post(
            "/api/metrics/customers/apply-threshold",
            json={"high_threshold": 0.8},
        )
        assert resp.status_code == 403
