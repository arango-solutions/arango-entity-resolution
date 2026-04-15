"""Review queue and human correction endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from entity_resolution.ui.models.schemas import VerdictRequest

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

    if hasattr(store, "query_verdicts"):
        verdicts = store.query_verdicts(
            decision=status,
            min_score=min_score,
            max_score=max_score,
        )
    else:
        verdicts = store.all_verdicts()
        if status:
            verdicts = [v for v in verdicts if v.get("decision") == status]
        if min_score is not None:
            verdicts = [v for v in verdicts if (v.get("score") or 0) >= min_score]
        if max_score is not None:
            verdicts = [v for v in verdicts if (v.get("score") or 0) <= max_score]

    reverse = sort_order == "desc"
    verdicts.sort(key=lambda v: v.get(sort_by, 0) or 0, reverse=reverse)

    total = len(verdicts)
    page = verdicts[offset : offset + limit]
    return {"verdicts": page, "total": total, "offset": offset, "limit": limit}


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
    """Record a human correction for a pair."""
    from entity_resolution.reasoning.feedback import FeedbackStore
    from entity_resolution.utils.validation import validate_collection_name

    if request.app.state.readonly:
        raise HTTPException(status_code=403, detail="Read-only mode")

    validate_collection_name(collection)
    db = _db(request)
    fb_coll = _feedback_collection(collection)
    store = FeedbackStore(db, collection=fb_coll)

    doc_key = store.record_human_correction(
        key_a=key_a,
        key_b=key_b,
        correct_decision=body.decision,
        confidence=body.confidence if body.confidence is not None else 1.0,
    )
    return {"status": "ok", "verdict_key": doc_key}


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
