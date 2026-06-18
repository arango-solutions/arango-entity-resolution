"""Evaluation-metrics endpoints (plan 1.2): threshold sweep + cluster quality."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


def _db(request: Request):
    return request.app.state.db


@router.get("/{collection}/threshold-sweep")
async def threshold_sweep(
    request: Request,
    collection: str,
    truth_collection: str = Query(..., description="Ground-truth pair collection."),
    thresholds: Optional[str] = Query(
        None, description="Optional comma-separated threshold grid (else exact curve)."
    ),
) -> Dict[str, Any]:
    """Precision/recall/F1 across thresholds for scored edges vs labeled pairs."""
    from entity_resolution.services.evaluation_service import EvaluationService
    from entity_resolution.ui.routes.collections import resolve_collection_name
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    validate_collection_name(truth_collection)
    db = _db(request)
    edge_coll = resolve_collection_name(request, f"{collection}_similarity_edges")
    if not db.has_collection(edge_coll) or not db.has_collection(truth_collection):
        raise HTTPException(status_code=404, detail="Edge or truth collection not found")

    grid: Optional[List[float]] = None
    if thresholds:
        try:
            grid = [float(x) for x in thresholds.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="thresholds must be comma-separated floats")

    service = EvaluationService(db, edge_collection=edge_coll)
    return service.threshold_sweep(truth_collection, thresholds=grid)


@router.get("/{collection}/cluster-quality")
async def cluster_quality(
    request: Request,
    collection: str,
    min_coherence: float = Query(0.5, ge=0.0, le=1.0),
) -> Dict[str, Any]:
    """Unsupervised per-cluster coherence metrics over the similarity graph."""
    from entity_resolution.services.evaluation_service import EvaluationService
    from entity_resolution.ui.routes.collections import resolve_collection_name
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)
    edge_coll = resolve_collection_name(request, f"{collection}_similarity_edges")
    cluster_coll = resolve_collection_name(request, f"{collection}_clusters")
    if not db.has_collection(edge_coll) or not db.has_collection(cluster_coll):
        raise HTTPException(status_code=404, detail="Edge or cluster collection not found")

    service = EvaluationService(db, edge_collection=edge_coll)
    return service.cluster_quality(cluster_coll, min_coherence=min_coherence)
