"""Pydantic models for UI API request/response shapes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CollectionInfo(BaseModel):
    name: str
    type: str
    count: int


class VerdictRequest(BaseModel):
    decision: str = Field(..., pattern="^(match|no_match)$")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    notes: Optional[str] = None


class ClusterGraphResponse(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]


class PipelineRunRequest(BaseModel):
    config: Dict[str, Any]


class PipelineRunResponse(BaseModel):
    run_id: str
    status: str


class GoldenRecordPreviewRequest(BaseModel):
    entity_keys: List[str] = Field(..., min_length=1)
    strategy: str = "most_complete"


class ResolveRequest(BaseModel):
    record: Dict[str, Any]
    fields: List[str]
    confidence_threshold: float = 0.80
    top_k: int = 10


class CrossResolveRequest(BaseModel):
    source_collection: str
    target_collection: str
    source_fields: List[str]
    target_fields: List[str]
    options: Optional[Dict[str, Any]] = None


class ConfigValidateRequest(BaseModel):
    config: Dict[str, Any]


class ConfigRecommendRequest(BaseModel):
    profile: Dict[str, Any]
    objective_profile: Dict[str, Any]
    request_id: Optional[str] = None
    allow_embedding_models: bool = True
    allow_graph_clustering: bool = True


class ConfigBlockingRequest(BaseModel):
    profile: Dict[str, Any]
    request_id: Optional[str] = None
    max_composite_size: int = 3
    max_results: int = 20
    must_include_fields: Optional[List[str]] = None
    must_exclude_fields: Optional[List[str]] = None


class ConfigSimulateRequest(BaseModel):
    variants: List[Dict[str, Any]] = Field(..., min_length=2)
    objective_profile: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None


class ConfigExportRequest(BaseModel):
    recommendation: Dict[str, Any]
    format: str = "json"
    include_rationale: bool = True
    request_id: Optional[str] = None


class ApplyThresholdRequest(BaseModel):
    # All optional; only the provided thresholds are written to the run config.
    threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    low_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    high_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    run_id: Optional[str] = None


class ExportRequest(BaseModel):
    # Optional: when omitted the server writes to a temp dir so browser clients
    # do not need to know server filesystem paths.
    output_dir: Optional[str] = None
    filename_prefix: str = "cluster_export"
    limit: Optional[int] = None
    cluster_collection: Optional[str] = None
    edge_collection: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
