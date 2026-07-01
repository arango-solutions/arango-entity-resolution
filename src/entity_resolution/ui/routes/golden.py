"""Golden record management endpoints."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from entity_resolution.ui.models.schemas import (
    GoldenApplyRequest,
    GoldenRecordPreviewRequest,
    SurvivorshipPreviewRequest,
)

router = APIRouter(prefix="/api/golden", tags=["golden"])


def _db(request: Request):
    return request.app.state.db


def _golden_collection(collection: str) -> str:
    return f"{collection}_golden_records"


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


@router.post("/{collection}/survivorship-preview")
async def survivorship_preview(
    request: Request,
    collection: str,
    body: SurvivorshipPreviewRequest,
) -> Dict[str, Any]:
    """Preview a golden record from member keys using a survivorship strategy.

    Uses the same per-field consolidation engine as the pipeline
    (``GoldenRecordPersistenceService``) and returns field-level provenance and
    the set of conflicting fields, plus the source records so the UI can offer
    per-field overrides. Nothing is persisted.
    """
    from entity_resolution.services.golden_record_persistence_service import (
        GoldenRecordPersistenceService,
    )
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)
    if not db.has_collection(collection):
        raise HTTPException(status_code=404, detail="Source collection not found")

    coll = db.collection(collection)
    member_docs = [coll.get(k) for k in body.member_keys]
    member_docs = [d for d in member_docs if d is not None]
    if not member_docs:
        raise HTTPException(status_code=404, detail="No source records found for member_keys")

    try:
        service = GoldenRecordPersistenceService(
            db=db,
            source_collection=collection,
            cluster_collection=f"{collection}_clusters",
            golden_collection=_golden_collection(collection),
            resolved_edge_collection=f"{collection}_resolvedTo",
            include_provenance=True,
            merge_strategy=body.merge_strategy,
            field_strategies=body.field_strategies,
            recency_field=body.recency_field,
            source_field=body.source_field,
            source_priority=body.source_priority,
        )
        consolidated, provenance = service._consolidate(member_docs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    conflicts = [f for f, p in provenance.items() if p.get("distinctValues", 1) > 1]
    return {
        "golden_record": consolidated,
        "provenance": provenance,
        "conflicts": conflicts,
        "sources": member_docs,
        "merged_keys": body.member_keys,
    }


@router.post("/{collection}/apply")
async def apply_golden_record(
    request: Request,
    collection: str,
    body: GoldenApplyRequest,
) -> Dict[str, Any]:
    """Persist a steward-edited golden record and write an audit entry."""
    from entity_resolution.services.curation_service import CurationService
    from entity_resolution.utils.validation import validate_collection_name

    if request.app.state.readonly:
        raise HTTPException(status_code=403, detail="Read-only mode")

    validate_collection_name(collection)
    db = _db(request)
    golden_coll = _golden_collection(collection)
    if not db.has_collection(golden_coll):
        db.create_collection(golden_coll)

    key = body.golden_key or hashlib.md5(
        "|".join(sorted(body.member_keys)).encode("utf-8")
    ).hexdigest()

    coll = db.collection(golden_coll)
    before = coll.get(key)

    from datetime import datetime, timezone

    # Reserved keys are stripped from user-supplied fields to protect metadata.
    clean_fields = {k: v for k, v in body.fields.items() if not k.startswith("_")}
    doc = {
        "_key": key,
        "memberKeys": body.member_keys,
        "_merged_keys": body.member_keys,
        "stale": False,
        "editedBy": getattr(request.state, "reviewer", None) or "human",
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "manual_edit",
        **({"mergeStrategy": body.merge_strategy} if body.merge_strategy else {}),
        **clean_fields,
    }
    coll.insert(doc, overwrite=True)

    actor = getattr(request.state, "reviewer", None) or "human"
    try:
        CurationService(db).record(
            actor=actor, action="golden_edit", collection=collection,
            entity_key=key, before=before, after=doc,
        )
    except Exception:
        pass

    return {"status": "ok", "golden_key": key, "golden_record": doc}


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
