"""Entity resolution endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Request

from entity_resolution.ui.models.schemas import CrossResolveRequest, ResolveRequest

router = APIRouter(prefix="/api/resolve", tags=["resolve"])


def _db(request: Request):
    return request.app.state.db


@router.post("/{collection}")
async def resolve_entity(
    request: Request,
    collection: str,
    body: ResolveRequest,
) -> List[Dict[str, Any]]:
    """Resolve a record against a collection."""
    from entity_resolution.mcp.tools.entity import run_resolve_entity
    from entity_resolution.ui.routes.collections import _conn_from_db
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)
    conn = _conn_from_db(db, request)

    matches = run_resolve_entity(
        **conn,
        collection=collection,
        record=body.record,
        fields=body.fields,
        confidence_threshold=body.confidence_threshold,
        top_k=body.top_k,
    )

    # Enrich each match with a display ``key`` and the full ``record`` so the UI
    # can show record content (the resolver itself returns only keys/scores).
    coll = db.collection(collection) if db.has_collection(collection) else None
    enriched: List[Dict[str, Any]] = []
    for match in matches:
        key = match.get("_key")
        record = coll.get(key) if (coll is not None and key) else None
        enriched.append({**match, "key": key, "record": record or {}})

    return enriched


@router.post("/cross")
async def resolve_cross_collection(
    request: Request,
    body: CrossResolveRequest,
) -> Dict[str, Any]:
    """Cross-collection entity resolution."""
    from entity_resolution.mcp.tools.entity import run_resolve_entity_cross_collection
    from entity_resolution.ui.routes.collections import _conn_from_db
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(body.source_collection)
    validate_collection_name(body.target_collection)
    db = _db(request)
    conn = _conn_from_db(db, request)

    return run_resolve_entity_cross_collection(
        **conn,
        source_collection=body.source_collection,
        target_collection=body.target_collection,
        source_fields=body.source_fields,
        target_fields=body.target_fields,
        options=body.options,
    )
