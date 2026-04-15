"""Golden record management endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from entity_resolution.ui.models.schemas import GoldenRecordPreviewRequest

router = APIRouter(prefix="/api/golden", tags=["golden"])


def _db(request: Request):
    return request.app.state.db


@router.post("/{collection}/preview")
async def preview_merge(
    request: Request,
    collection: str,
    body: GoldenRecordPreviewRequest,
) -> Dict[str, Any]:
    """Preview a golden record merge without persisting."""
    from entity_resolution.mcp.tools.cluster import run_merge_entities
    from entity_resolution.ui.routes.collections import _conn_from_db
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)
    conn = _conn_from_db(db, request)

    return run_merge_entities(
        **conn,
        collection=collection,
        entity_keys=body.entity_keys,
        strategy=body.strategy,
    )


@router.post("/{collection}/merge")
async def merge_records(
    request: Request,
    collection: str,
    body: GoldenRecordPreviewRequest,
) -> Dict[str, Any]:
    """Execute a golden record merge and persist the result."""
    from entity_resolution.mcp.tools.cluster import run_merge_entities
    from entity_resolution.ui.routes.collections import _conn_from_db
    from entity_resolution.utils.validation import validate_collection_name

    if request.app.state.readonly:
        raise HTTPException(status_code=403, detail="Read-only mode")

    validate_collection_name(collection)
    db = _db(request)
    conn = _conn_from_db(db, request)

    result = run_merge_entities(
        **conn,
        collection=collection,
        entity_keys=body.entity_keys,
        strategy=body.strategy,
    )

    golden = result.get("golden_record", {})
    golden_coll_name = f"{collection}_golden_records"
    if not db.has_collection(golden_coll_name):
        db.create_collection(golden_coll_name)

    golden["_merged_keys"] = body.entity_keys
    golden["_strategy"] = body.strategy
    db.collection(golden_coll_name).insert(golden, overwrite=True)
    result["persisted"] = True
    result["golden_collection"] = golden_coll_name

    return result


@router.get("/{collection}/{entity_key}")
async def get_golden_record(
    request: Request,
    collection: str,
    entity_key: str,
) -> Dict[str, Any]:
    """Retrieve a golden record by key."""
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)

    golden_coll_name = f"{collection}_golden_records"
    if not db.has_collection(golden_coll_name):
        raise HTTPException(status_code=404, detail="Golden record collection not found")

    doc = db.collection(golden_coll_name).get(entity_key)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Golden record '{entity_key}' not found")

    return doc


@router.get("/{collection}/{entity_key}/provenance")
async def golden_provenance(
    request: Request,
    collection: str,
    entity_key: str,
) -> Dict[str, Any]:
    """Return source records and provenance for a golden record."""
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)

    golden_coll_name = f"{collection}_golden_records"
    if not db.has_collection(golden_coll_name):
        raise HTTPException(status_code=404, detail="Golden record collection not found")

    golden_doc = db.collection(golden_coll_name).get(entity_key)
    if golden_doc is None:
        raise HTTPException(status_code=404, detail=f"Golden record '{entity_key}' not found")

    merged_keys = golden_doc.get("_merged_keys", [])
    source_docs: List[Dict[str, Any]] = []
    if db.has_collection(collection):
        coll = db.collection(collection)
        for key in merged_keys:
            doc = coll.get(key)
            if doc is not None:
                source_docs.append(doc)

    return {
        "golden_record": golden_doc,
        "source_records": source_docs,
        "merged_keys": merged_keys,
    }
