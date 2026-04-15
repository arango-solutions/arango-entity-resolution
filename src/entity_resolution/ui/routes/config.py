"""Configuration builder endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Request

from entity_resolution.ui.models.schemas import (
    ConfigBlockingRequest,
    ConfigExportRequest,
    ConfigRecommendRequest,
    ConfigSimulateRequest,
    ConfigValidateRequest,
)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.post("/validate")
async def validate_config(body: ConfigValidateRequest) -> Dict[str, Any]:
    """Validate a pipeline configuration dict and return errors."""
    from entity_resolution.config.er_config import ERPipelineConfig

    try:
        cfg = ERPipelineConfig.from_dict(body.config)
        errors = cfg.validate()
    except Exception as exc:
        errors = [str(exc)]

    return {"valid": len(errors) == 0, "errors": errors}


@router.post("/recommend")
async def recommend_strategy(body: ConfigRecommendRequest) -> Dict[str, Any]:
    """Get strategy recommendations from profile and objectives."""
    from entity_resolution.mcp.tools.advisor import run_recommend_resolution_strategy

    return run_recommend_resolution_strategy(
        profile=body.profile,
        objective_profile=body.objective_profile,
        request_id=body.request_id,
        allow_embedding_models=body.allow_embedding_models,
        allow_graph_clustering=body.allow_graph_clustering,
    )


@router.post("/blocking")
async def recommend_blocking(body: ConfigBlockingRequest) -> Dict[str, Any]:
    """Get blocking key recommendations from a profile."""
    from entity_resolution.mcp.tools.advisor import run_recommend_blocking_candidates

    return run_recommend_blocking_candidates(
        profile=body.profile,
        request_id=body.request_id,
        max_composite_size=body.max_composite_size,
        max_results=body.max_results,
        must_include_fields=body.must_include_fields,
        must_exclude_fields=body.must_exclude_fields,
    )


@router.post("/simulate")
async def simulate_variants(body: ConfigSimulateRequest) -> Dict[str, Any]:
    """Compare pipeline configurations by simulating variants."""
    from entity_resolution.mcp.tools.advisor import run_simulate_pipeline_variants

    return run_simulate_pipeline_variants(
        variants=body.variants,
        objective_profile=body.objective_profile,
        request_id=body.request_id,
    )


@router.post("/export")
async def export_config(body: ConfigExportRequest) -> Dict[str, Any]:
    """Export a config recommendation as YAML or JSON."""
    from entity_resolution.mcp.tools.advisor import run_export_recommended_config

    return run_export_recommended_config(
        recommendation=body.recommendation,
        format=body.format,
        include_rationale=body.include_rationale,
        request_id=body.request_id,
    )
