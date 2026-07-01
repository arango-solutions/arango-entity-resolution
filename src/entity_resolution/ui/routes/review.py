"""Review queue and human correction endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Response

from entity_resolution.ui.models.schemas import BatchVerdictRequest, VerdictRequest

router = APIRouter(prefix="/api/review", tags=["review"])


def _db(request: Request):
    return request.app.state.db


def _feedback_collection(collection: str) -> str:
    return f"{collection}_llm_feedback"


@router.get("/{collection}")
async def list_verdicts(
    request: Request,
    collection: str,
    status: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    source: Optional[str] = None,
    sort_by: str = "score",
    sort_order: str = "asc",
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """List verdicts from FeedbackStore, filterable by decision status and score range."""
    from entity_resolution.reasoning.feedback import FeedbackStore
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)
    fb_coll = _feedback_collection(collection)

    if not db.has_collection(fb_coll):
        return {"verdicts": [], "total": 0, "offset": offset, "limit": limit}

    store = FeedbackStore(db, collection=fb_coll)

    # FeedbackStore.query_verdicts handles filtering, sorting, and pagination in
    # AQL and returns {"items", "total", "limit", "offset"}.
    result = store.query_verdicts(
        status=status,
        score_min=min_score,
        score_max=max_score,
        source=source,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )

    return {
        "verdicts": result.get("items", []),
        "total": result.get("total", 0),
        "offset": result.get("offset", offset),
        "limit": result.get("limit", limit),
    }


@router.get("/{collection}/stats")
async def verdict_stats(request: Request, collection: str) -> Dict[str, Any]:
    """Verdict counts by decision type."""
    from entity_resolution.reasoning.feedback import FeedbackStore
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)
    fb_coll = _feedback_collection(collection)

    if not db.has_collection(fb_coll):
        return {"by_decision": [], "total": 0}

    store = FeedbackStore(db, collection=fb_coll)
    return store.stats()


@router.get("/{collection}/pair/{key_a}/{key_b}")
async def pair_comparison(
    request: Request,
    collection: str,
    key_a: str,
    key_b: str,
) -> Dict[str, Any]:
    """Full pair comparison with field-level scoring and document data."""
    from entity_resolution.mcp.tools.entity import run_explain_match
    from entity_resolution.ui.routes.collections import _conn_from_db
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)
    conn = _conn_from_db(db, request)

    explanation = run_explain_match(
        **conn,
        collection=collection,
        key_a=key_a,
        key_b=key_b,
    )

    coll = db.collection(collection)
    doc_a = coll.get(key_a)
    doc_b = coll.get(key_b)

    return {
        "explanation": explanation,
        "doc_a": doc_a,
        "doc_b": doc_b,
    }


@router.post("/{collection}/pair/{key_a}/{key_b}/verdict")
async def submit_verdict(
    request: Request,
    collection: str,
    key_a: str,
    key_b: str,
    body: VerdictRequest,
) -> Dict[str, Any]:
    """Record a human correction for a pair and apply it to the graph.

    The verdict is persisted (for threshold optimization) and then applied:
    a ``no_match`` suppresses the similarity edge, a ``match`` confirms it, and
    the affected connected component is re-clustered. ``clusters_changed`` lets
    the frontend invalidate its cluster caches.
    """
    from entity_resolution.reasoning.feedback import FeedbackStore
    from entity_resolution.services.curation_service import CurationService
    from entity_resolution.services.feedback_application_service import (
        FeedbackApplicationError,
        FeedbackApplicationService,
    )
    from entity_resolution.ui.routes.collections import resolve_collection_name
    from entity_resolution.utils.validation import validate_collection_name

    if request.app.state.readonly:
        raise HTTPException(status_code=403, detail="Read-only mode")

    validate_collection_name(collection)
    db = _db(request)
    fb_coll = _feedback_collection(collection)
    store = FeedbackStore(db, collection=fb_coll)
    actor = getattr(request.state, "reviewer", None) or "human"

    # Persist the verdict (training data for threshold optimization).
    doc_key = store.record_human_correction(
        key_a=key_a,
        key_b=key_b,
        correct_decision=body.decision,
        confidence=body.confidence if body.confidence is not None else 1.0,
        reviewer=actor,
    )

    # Audit the verdict (attribution trail).
    try:
        CurationService(db).record(
            actor=actor,
            action="verdict",
            collection=collection,
            entity_key=doc_key,
            after={"key_a": key_a, "key_b": key_b, "decision": body.decision},
        )
    except Exception:  # auditing must never block the verdict
        pass

    # Apply it to the similarity graph and re-cluster the affected component.
    edge_coll = resolve_collection_name(request, f"{collection}_similarity_edges")
    cluster_coll = resolve_collection_name(request, f"{collection}_clusters")
    golden_coll = resolve_collection_name(request, f"{collection}_golden_records")

    response: Dict[str, Any] = {"status": "ok", "verdict_key": doc_key}

    if db.has_collection(edge_coll):
        applier = FeedbackApplicationService(
            db=db,
            edge_collection=edge_coll,
            vertex_collection=collection,
            cluster_collection=cluster_coll,
            golden_collection=golden_coll,
        )
        try:
            result = applier.apply_and_recluster(
                key_a, key_b, body.decision, actor=actor
            )
            response["applied"] = result["verdict"]["action"]
            response["clusters_changed"] = result["recluster"]["cluster_keys"]
            response["recluster"] = result["recluster"]
        except FeedbackApplicationError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    else:
        response["applied"] = None
        response["clusters_changed"] = []

    return response


@router.post("/{collection}/batch-verdict")
async def batch_verdict(
    request: Request,
    collection: str,
    body: BatchVerdictRequest,
) -> Dict[str, Any]:
    """Apply many verdicts in one call (bulk actions from the review queue).

    Each verdict is persisted and applied to the graph exactly like the
    single-pair endpoint; results are aggregated and every applied pair writes
    its own audit row. Per-pair failures (e.g. lock contention) are reported
    without aborting the batch.
    """
    from entity_resolution.reasoning.feedback import FeedbackStore
    from entity_resolution.services.curation_service import CurationService
    from entity_resolution.services.feedback_application_service import (
        FeedbackApplicationError,
        FeedbackApplicationService,
    )
    from entity_resolution.ui.routes.collections import resolve_collection_name
    from entity_resolution.utils.validation import validate_collection_name

    if request.app.state.readonly:
        raise HTTPException(status_code=403, detail="Read-only mode")

    validate_collection_name(collection)
    for v in body.verdicts:
        if v.decision not in ("match", "no_match"):
            raise HTTPException(status_code=422, detail="decision must be match or no_match")

    db = _db(request)
    fb_coll = _feedback_collection(collection)
    store = FeedbackStore(db, collection=fb_coll)
    curation = CurationService(db)
    actor = getattr(request.state, "reviewer", None) or "human"

    edge_coll = resolve_collection_name(request, f"{collection}_similarity_edges")
    cluster_coll = resolve_collection_name(request, f"{collection}_clusters")
    golden_coll = resolve_collection_name(request, f"{collection}_golden_records")
    applier = None
    if db.has_collection(edge_coll):
        applier = FeedbackApplicationService(
            db=db, edge_collection=edge_coll, vertex_collection=collection,
            cluster_collection=cluster_coll, golden_collection=golden_coll,
        )

    results: List[Dict[str, Any]] = []
    clusters_changed: set = set()
    applied_count = 0
    for v in body.verdicts:
        doc_key = store.record_human_correction(
            key_a=v.key_a, key_b=v.key_b, correct_decision=v.decision,
            confidence=v.confidence if v.confidence is not None else 1.0, reviewer=actor,
        )
        try:
            curation.record(actor=actor, action="verdict", collection=collection,
                            entity_key=doc_key,
                            after={"key_a": v.key_a, "key_b": v.key_b, "decision": v.decision})
        except Exception:
            pass
        if applier is None:
            results.append({"key_a": v.key_a, "key_b": v.key_b, "applied": None})
            continue
        try:
            r = applier.apply_and_recluster(v.key_a, v.key_b, v.decision, actor=actor)
            clusters_changed.update(r["recluster"]["cluster_keys"])
            applied_count += 1
            results.append({"key_a": v.key_a, "key_b": v.key_b, "applied": r["verdict"]["action"]})
        except FeedbackApplicationError as exc:
            results.append({"key_a": v.key_a, "key_b": v.key_b, "error": str(exc)})

    return {
        "status": "ok",
        "count": len(results),
        "applied": applied_count,
        "clusters_changed": sorted(clusters_changed),
        "results": results,
    }


@router.get("/{collection}/export.csv")
async def export_verdicts_csv(
    request: Request,
    collection: str,
    status: Optional[str] = None,
    source: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
) -> Response:
    """Export the (filtered) review queue as CSV."""
    import csv
    import io

    from entity_resolution.reasoning.feedback import FeedbackStore
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)
    fb_coll = _feedback_collection(collection)

    columns = ["key_a", "key_b", "score", "decision", "confidence", "source", "reviewer", "ts"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    if db.has_collection(fb_coll):
        store = FeedbackStore(db, collection=fb_coll)
        result = store.query_verdicts(
            status=status, score_min=min_score, score_max=max_score,
            source=source, limit=100000, offset=0,
        )
        for row in result.get("items", []):
            writer.writerow({c: row.get(c) for c in columns})

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={collection}_review.csv"},
    )


@router.post("/{collection}/optimize")
async def optimize_thresholds(
    request: Request, collection: str
) -> Dict[str, Any]:
    """Trigger threshold optimization using stored feedback."""
    from entity_resolution.reasoning.feedback import (
        AdaptiveLLMVerifier,
        FeedbackStore,
        ThresholdOptimizer,
    )
    from entity_resolution.utils.validation import validate_collection_name

    if request.app.state.readonly:
        raise HTTPException(status_code=403, detail="Read-only mode")

    validate_collection_name(collection)
    db = _db(request)
    fb_coll = _feedback_collection(collection)

    if not db.has_collection(fb_coll):
        return {"optimized": False, "reason": "No feedback collection found"}

    store = FeedbackStore(db, collection=fb_coll)
    optimizer = ThresholdOptimizer(store)
    return optimizer.optimize()


@router.get("/{collection}/thresholds")
async def current_thresholds(
    request: Request, collection: str
) -> Dict[str, Any]:
    """Return current low/high thresholds from the most recent optimization."""
    from entity_resolution.reasoning.feedback import FeedbackStore, ThresholdOptimizer
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)
    fb_coll = _feedback_collection(collection)

    if not db.has_collection(fb_coll):
        return {"low_threshold": 0.55, "high_threshold": 0.80, "source": "default"}

    store = FeedbackStore(db, collection=fb_coll)
    optimizer = ThresholdOptimizer(store)
    result = optimizer.optimize()
    return {
        "low_threshold": result["low_threshold"],
        "high_threshold": result["high_threshold"],
        "source": "optimized" if result.get("optimized") else "default",
        "sample_count": result.get("sample_count", 0),
    }
