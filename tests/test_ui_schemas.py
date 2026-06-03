"""Tests for Pydantic models in entity_resolution.ui.models.schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from entity_resolution.ui.models.schemas import (
    ClusterGraphResponse,
    CollectionInfo,
    ConfigBlockingRequest,
    ConfigExportRequest,
    ConfigRecommendRequest,
    ConfigSimulateRequest,
    ConfigValidateRequest,
    CrossResolveRequest,
    ExportRequest,
    GoldenRecordPreviewRequest,
    HealthResponse,
    PipelineRunRequest,
    PipelineRunResponse,
    ResolveRequest,
    VerdictRequest,
)


# ===================================================================
# CollectionInfo
# ===================================================================

class TestCollectionInfo:

    def test_valid(self):
        obj = CollectionInfo(name="customers", type="document", count=100)
        assert obj.name == "customers"
        assert obj.type == "document"
        assert obj.count == 100

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            CollectionInfo()  # type: ignore[call-arg]

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            CollectionInfo(type="document", count=0)  # type: ignore[call-arg]


# ===================================================================
# VerdictRequest
# ===================================================================

class TestVerdictRequest:

    def test_match(self):
        obj = VerdictRequest(decision="match")
        assert obj.decision == "match"
        assert obj.confidence is None
        assert obj.notes is None

    def test_no_match(self):
        obj = VerdictRequest(decision="no_match")
        assert obj.decision == "no_match"

    def test_with_optional_fields(self):
        obj = VerdictRequest(decision="match", confidence=0.95, notes="looks good")
        assert obj.confidence == 0.95
        assert obj.notes == "looks good"

    def test_invalid_decision(self):
        with pytest.raises(ValidationError):
            VerdictRequest(decision="maybe")

    def test_empty_decision(self):
        with pytest.raises(ValidationError):
            VerdictRequest(decision="")

    def test_missing_decision(self):
        with pytest.raises(ValidationError):
            VerdictRequest()  # type: ignore[call-arg]

    def test_confidence_below_range(self):
        with pytest.raises(ValidationError):
            VerdictRequest(decision="match", confidence=-0.1)

    def test_confidence_above_range(self):
        with pytest.raises(ValidationError):
            VerdictRequest(decision="match", confidence=1.5)

    def test_confidence_boundaries(self):
        assert VerdictRequest(decision="match", confidence=0.0).confidence == 0.0
        assert VerdictRequest(decision="match", confidence=1.0).confidence == 1.0


# ===================================================================
# ClusterGraphResponse
# ===================================================================

class TestClusterGraphResponse:

    def test_valid(self):
        obj = ClusterGraphResponse(
            nodes=[{"id": "a", "key": "a"}],
            edges=[{"source": "a", "target": "b"}],
        )
        assert len(obj.nodes) == 1
        assert len(obj.edges) == 1

    def test_empty_lists(self):
        obj = ClusterGraphResponse(nodes=[], edges=[])
        assert obj.nodes == []
        assert obj.edges == []

    def test_missing_nodes(self):
        with pytest.raises(ValidationError):
            ClusterGraphResponse(edges=[])  # type: ignore[call-arg]

    def test_missing_edges(self):
        with pytest.raises(ValidationError):
            ClusterGraphResponse(nodes=[])  # type: ignore[call-arg]


# ===================================================================
# PipelineRunRequest / PipelineRunResponse
# ===================================================================

class TestPipelineRunRequest:

    def test_valid(self):
        obj = PipelineRunRequest(config={"collection": "test"})
        assert obj.config == {"collection": "test"}

    def test_missing_config(self):
        with pytest.raises(ValidationError):
            PipelineRunRequest()  # type: ignore[call-arg]


class TestPipelineRunResponse:

    def test_valid(self):
        obj = PipelineRunResponse(run_id="abc-123", status="running")
        assert obj.run_id == "abc-123"
        assert obj.status == "running"

    def test_missing_fields(self):
        with pytest.raises(ValidationError):
            PipelineRunResponse()  # type: ignore[call-arg]


# ===================================================================
# GoldenRecordPreviewRequest
# ===================================================================

class TestGoldenRecordPreviewRequest:

    def test_valid(self):
        obj = GoldenRecordPreviewRequest(entity_keys=["k1", "k2"])
        assert obj.entity_keys == ["k1", "k2"]
        assert obj.strategy == "most_complete"

    def test_custom_strategy(self):
        obj = GoldenRecordPreviewRequest(entity_keys=["k1"], strategy="majority_vote")
        assert obj.strategy == "majority_vote"

    def test_empty_entity_keys(self):
        with pytest.raises(ValidationError):
            GoldenRecordPreviewRequest(entity_keys=[])

    def test_missing_entity_keys(self):
        with pytest.raises(ValidationError):
            GoldenRecordPreviewRequest()  # type: ignore[call-arg]


# ===================================================================
# ResolveRequest
# ===================================================================

class TestResolveRequest:

    def test_valid(self):
        obj = ResolveRequest(
            record={"name": "Acme"}, fields=["name"], confidence_threshold=0.9, top_k=5
        )
        assert obj.record == {"name": "Acme"}
        assert obj.fields == ["name"]
        assert obj.confidence_threshold == 0.9
        assert obj.top_k == 5

    def test_defaults(self):
        obj = ResolveRequest(record={"a": 1}, fields=["a"])
        assert obj.confidence_threshold == 0.80
        assert obj.top_k == 10

    def test_missing_record(self):
        with pytest.raises(ValidationError):
            ResolveRequest(fields=["a"])  # type: ignore[call-arg]

    def test_missing_fields(self):
        with pytest.raises(ValidationError):
            ResolveRequest(record={"a": 1})  # type: ignore[call-arg]


# ===================================================================
# CrossResolveRequest
# ===================================================================

class TestCrossResolveRequest:

    def test_valid(self):
        obj = CrossResolveRequest(
            source_collection="a",
            target_collection="b",
            source_fields=["f1"],
            target_fields=["f2"],
        )
        assert obj.source_collection == "a"
        assert obj.options is None

    def test_with_options(self):
        obj = CrossResolveRequest(
            source_collection="a",
            target_collection="b",
            source_fields=["f1"],
            target_fields=["f2"],
            options={"threshold": 0.5},
        )
        assert obj.options == {"threshold": 0.5}

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            CrossResolveRequest(source_collection="a")  # type: ignore[call-arg]


# ===================================================================
# ConfigValidateRequest
# ===================================================================

class TestConfigValidateRequest:

    def test_valid(self):
        obj = ConfigValidateRequest(config={"entity_type": "person"})
        assert obj.config == {"entity_type": "person"}

    def test_missing_config(self):
        with pytest.raises(ValidationError):
            ConfigValidateRequest()  # type: ignore[call-arg]


# ===================================================================
# ConfigRecommendRequest
# ===================================================================

class TestConfigRecommendRequest:

    def test_valid(self):
        obj = ConfigRecommendRequest(
            profile={"fields": ["name"]}, objective_profile={"goal": "precision"}
        )
        assert obj.allow_embedding_models is True
        assert obj.allow_graph_clustering is True
        assert obj.request_id is None

    def test_all_fields(self):
        obj = ConfigRecommendRequest(
            profile={"fields": ["name"]},
            objective_profile={"goal": "recall"},
            request_id="req-1",
            allow_embedding_models=False,
            allow_graph_clustering=False,
        )
        assert obj.request_id == "req-1"
        assert obj.allow_embedding_models is False

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            ConfigRecommendRequest(profile={"x": 1})  # type: ignore[call-arg]


# ===================================================================
# ConfigBlockingRequest
# ===================================================================

class TestConfigBlockingRequest:

    def test_valid_with_defaults(self):
        obj = ConfigBlockingRequest(profile={"fields": ["name"]})
        assert obj.max_composite_size == 3
        assert obj.max_results == 20
        assert obj.must_include_fields is None
        assert obj.must_exclude_fields is None
        assert obj.request_id is None

    def test_all_fields(self):
        obj = ConfigBlockingRequest(
            profile={"x": 1},
            request_id="r1",
            max_composite_size=5,
            max_results=50,
            must_include_fields=["email"],
            must_exclude_fields=["ssn"],
        )
        assert obj.must_include_fields == ["email"]

    def test_missing_profile(self):
        with pytest.raises(ValidationError):
            ConfigBlockingRequest()  # type: ignore[call-arg]


# ===================================================================
# ConfigSimulateRequest
# ===================================================================

class TestConfigSimulateRequest:

    def test_valid(self):
        obj = ConfigSimulateRequest(variants=[{"a": 1}, {"b": 2}])
        assert len(obj.variants) == 2
        assert obj.objective_profile is None

    def test_too_few_variants(self):
        with pytest.raises(ValidationError):
            ConfigSimulateRequest(variants=[{"a": 1}])

    def test_missing_variants(self):
        with pytest.raises(ValidationError):
            ConfigSimulateRequest()  # type: ignore[call-arg]


# ===================================================================
# ConfigExportRequest
# ===================================================================

class TestConfigExportRequest:

    def test_valid_with_defaults(self):
        obj = ConfigExportRequest(recommendation={"strategy": "exact"})
        assert obj.format == "json"
        assert obj.include_rationale is True
        assert obj.request_id is None

    def test_yaml_format(self):
        obj = ConfigExportRequest(recommendation={"x": 1}, format="yaml")
        assert obj.format == "yaml"

    def test_missing_recommendation(self):
        with pytest.raises(ValidationError):
            ConfigExportRequest()  # type: ignore[call-arg]


# ===================================================================
# ExportRequest
# ===================================================================

class TestExportRequest:

    def test_valid_with_defaults(self):
        obj = ExportRequest(output_dir="/tmp/out")
        assert obj.filename_prefix == "cluster_export"
        assert obj.limit is None
        assert obj.cluster_collection is None
        assert obj.edge_collection is None

    def test_all_fields(self):
        obj = ExportRequest(
            output_dir="/tmp/out",
            filename_prefix="test",
            limit=100,
            cluster_collection="cl",
            edge_collection="ed",
        )
        assert obj.limit == 100

    def test_output_dir_optional(self):
        # output_dir is optional: the server falls back to a temp dir so browser
        # clients do not need to supply server filesystem paths.
        obj = ExportRequest()
        assert obj.output_dir is None
        assert obj.filename_prefix == "cluster_export"


# ===================================================================
# HealthResponse
# ===================================================================

class TestHealthResponse:

    def test_valid(self):
        obj = HealthResponse(status="ok", version="3.5.1")
        assert obj.status == "ok"
        assert obj.version == "3.5.1"

    def test_missing_fields(self):
        with pytest.raises(ValidationError):
            HealthResponse()  # type: ignore[call-arg]
