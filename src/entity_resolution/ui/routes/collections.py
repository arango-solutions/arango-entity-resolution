"""Collection listing and profiling endpoints."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/collections", tags=["collections"])


def _db(request: Request):
    return request.app.state.db


def resolve_collection_name(request: Request, derived_name: str) -> str:
    """Map a derived collection name through configured aliases."""
    aliases = getattr(request.app.state, "collection_aliases", {}) or {}
    return aliases.get(derived_name, derived_name)


@router.get("")
async def list_collections(request: Request) -> List[Dict[str, Any]]:
    """List all non-system collections with name, type, and count."""
    db = _db(request)
    result = []
    for coll in db.collections():
        if coll["system"]:
            continue
        try:
            count = db.collection(coll["name"]).count()
        except Exception:
            count = -1
        result.append({
            "name": coll["name"],
            "type": "edge" if coll["type"] == 3 else "document",
            "count": count,
        })
    return sorted(result, key=lambda c: c["name"])


@router.get("/{name}/profile")
async def profile_collection(
    request: Request,
    name: str,
    sample_limit: int = 10000,
) -> Dict[str, Any]:
    """Profile a collection's fields for ER-relevant statistics."""
    from entity_resolution.mcp.tools.advisor import run_profile_dataset
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(name)
    db = _db(request)
    conn = _conn_from_db(db, request)
    return run_profile_dataset(
        **conn,
        source_type="collection",
        dataset_id=name,
        sample_limit=sample_limit,
    )


@router.get("/{name}/sample")
async def collection_sample(request: Request, name: str) -> Dict[str, Any]:
    """Return schema and sample documents for a collection."""
    from entity_resolution.mcp.resources.collections import get_collection_summary
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(name)
    db = _db(request)
    conn = _conn_from_db(db, request)
    raw = get_collection_summary(**conn, collection_name=name)
    return json.loads(raw)


def _conn_from_db(db, request: Request | None = None) -> Dict[str, Any]:
    """Return connection params for creating secondary ArangoDB clients.

    Prefers explicit ``connection_params`` stored on ``app.state`` (set by the
    CLI at startup) because python-arango v8 no longer exposes credentials as
    instance attributes.  Falls back to introspection for backwards compat.
    """
    stored = {}
    if request is not None:
        stored = getattr(request.app.state, "connection_params", {}) or {}

    if stored.get("password"):
        return {
            "host": stored.get("host", "localhost"),
            "port": stored.get("port", 8529),
            "username": stored.get("username", "root"),
            "password": stored["password"],
            "database": stored.get("database") or db.name,
        }

    conn = getattr(db, "_conn", None)
    url = ""
    if conn is not None:
        url = getattr(conn, "_url_prefixes", [""])[0] if hasattr(conn, "_url_prefixes") else ""
        if not url:
            url = getattr(conn, "_url", "")
    if not url:
        url = "http://localhost:8529"

    host = "localhost"
    port = 8529
    if "://" in url:
        netloc = url.split("://", 1)[1].split("/")[0]
        parts = netloc.rsplit(":", 1)
        host = parts[0]
        if len(parts) > 1:
            try:
                port = int(parts[1])
            except ValueError:
                pass

    username = getattr(db, "_username", "root") or "root"
    password = getattr(db, "_password", "") or ""
    database = db.name

    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "database": database,
    }
