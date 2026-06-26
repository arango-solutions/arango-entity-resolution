"""Curation audit endpoints (plan 2.0)."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/curation", tags=["curation"])


def _db(request: Request):
    return request.app.state.db


@router.get("/{collection}/history/{key}")
async def curation_history(
    request: Request,
    collection: str,
    key: str,
    limit: int = 50,
) -> Dict[str, Any]:
    """Return the audit trail (newest first) for a cluster/entity/pair key."""
    from entity_resolution.services.curation_service import CurationService
    from entity_resolution.utils.validation import validate_collection_name

    try:
        validate_collection_name(collection)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db = _db(request)
    service = CurationService(db)
    return {"entries": service.history(collection, key, limit=limit)}
