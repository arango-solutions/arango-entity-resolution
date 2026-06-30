"""Evaluation-metrics endpoints (plan 1.2): threshold sweep + cluster quality."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from entity_resolution.ui.models.schemas import ApplyThresholdRequest

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

_RUNS_COLLECTION = "_er_pipeline_runs"


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


@router.get("/{collection}/score-distribution")
async def score_distribution(
    request: Request,
    collection: str,
    bucket: float = Query(0.05, gt=0.0, le=1.0),
) -> Dict[str, Any]:
    """Histogram of non-suppressed similarity-edge scores (for the tuner)."""
    from entity_resolution.services.evaluation_service import EvaluationService
    from entity_resolution.ui.routes.collections import resolve_collection_name
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)
    edge_coll = resolve_collection_name(request, f"{collection}_similarity_edges")
    if not db.has_collection(edge_coll):
        return {"buckets": [], "bucket": bucket}
    service = EvaluationService(db, edge_collection=edge_coll)
    return {"buckets": service.score_distribution(bucket=bucket), "bucket": bucket}


@router.get("/{collection}/boundary-pairs")
async def boundary_pairs(
    request: Request,
    collection: str,
    score: float = Query(..., ge=0.0, le=1.0),
    window: float = Query(0.05, gt=0.0, le=1.0),
    limit: int = Query(10, ge=1, le=100),
) -> Dict[str, Any]:
    """Candidate pairs with an edge score within ``window`` of ``score``."""
    from entity_resolution.services.evaluation_service import EvaluationService
    from entity_resolution.ui.routes.collections import resolve_collection_name
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)
    edge_coll = resolve_collection_name(request, f"{collection}_similarity_edges")
    if not db.has_collection(edge_coll):
        return {"pairs": []}
    service = EvaluationService(db, edge_collection=edge_coll)
    return {"pairs": service.boundary_pairs(score, window=window, limit=limit)}


def _latest_run_for_collection(db, collection: str) -> Optional[Dict[str, Any]]:
    """Most recent _er_pipeline_runs doc whose config targets ``collection``."""
    if not db.has_collection(_RUNS_COLLECTION):
        return None
    cursor = db.aql.execute(
        "FOR r IN @@coll SORT r.started_at DESC RETURN r",
        bind_vars={"@coll": _RUNS_COLLECTION},
    )
    for run in cursor:
        cfg = run.get("config") or {}
        er = cfg.get("entity_resolution", cfg)
        if isinstance(er, dict) and er.get("collection") == collection:
            return run
    return None


@router.post("/{collection}/apply-threshold")
async def apply_threshold(
    request: Request,
    collection: str,
    body: ApplyThresholdRequest,
) -> Dict[str, Any]:
    """Persist chosen thresholds to the run config (audited).

    Writes ``similarity.threshold`` and/or ``active_learning.low/high_threshold``
    into the target pipeline-run config. Because Fellegi-Sunter posteriors are
    stored as the edge ``similarity``, the tuner histogram and these thresholds
    share one scale — no separate score↔posterior band remap is needed.
    """
    from entity_resolution.services.curation_service import CurationService
    from entity_resolution.utils.validation import validate_collection_name

    if request.app.state.readonly:
        raise HTTPException(status_code=403, detail="Read-only mode")

    validate_collection_name(collection)
    db = _db(request)

    if body.run_id:
        run = None
        if db.has_collection(_RUNS_COLLECTION):
            run = db.collection(_RUNS_COLLECTION).get(body.run_id)
    else:
        run = _latest_run_for_collection(db, collection)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail="No pipeline run found to apply thresholds to. Run a pipeline first.",
        )

    cfg = run.get("config") or {}
    er = cfg.get("entity_resolution", cfg)
    before = {
        "threshold": (er.get("similarity") or {}).get("threshold"),
        "low_threshold": (er.get("active_learning") or {}).get("low_threshold"),
        "high_threshold": (er.get("active_learning") or {}).get("high_threshold"),
    }

    if body.threshold is not None:
        er.setdefault("similarity", {})["threshold"] = body.threshold
    if body.low_threshold is not None:
        er.setdefault("active_learning", {})["low_threshold"] = body.low_threshold
    if body.high_threshold is not None:
        er.setdefault("active_learning", {})["high_threshold"] = body.high_threshold

    after = {
        "threshold": (er.get("similarity") or {}).get("threshold"),
        "low_threshold": (er.get("active_learning") or {}).get("low_threshold"),
        "high_threshold": (er.get("active_learning") or {}).get("high_threshold"),
    }

    db.collection(_RUNS_COLLECTION).update({"_key": run["_key"], "config": cfg})

    actor = getattr(request.state, "reviewer", None) or "human"
    try:
        CurationService(db).record(
            actor=actor, action="apply_threshold", collection=collection,
            entity_key=run["_key"], before=before, after=after,
        )
    except Exception:
        pass

    return {"status": "ok", "run_id": run["_key"], "thresholds": after}
