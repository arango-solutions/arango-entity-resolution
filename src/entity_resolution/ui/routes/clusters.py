"""Cluster listing, detail, and graph endpoints."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request

from entity_resolution.ui.models.schemas import ClusterGraphResponse

router = APIRouter(prefix="/api/clusters", tags=["clusters"])


def _db(request: Request):
    return request.app.state.db


@router.get("/{collection}")
async def list_clusters(
    request: Request,
    collection: str,
    limit: int = 50,
    offset: int = 0,
    min_size: int = 2,
) -> Dict[str, Any]:
    """Paginated cluster list with quality metadata."""
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)

    from entity_resolution.ui.routes.collections import resolve_collection_name
    cluster_coll = resolve_collection_name(request, f"{collection}_clusters")
    if not db.has_collection(cluster_coll):
        return {"clusters": [], "total": 0, "offset": offset, "limit": limit}

    count_cursor = db.aql.execute(
        "FOR c IN @@coll FILTER LENGTH(c.members) >= @min_size COLLECT WITH COUNT INTO n RETURN n",
        bind_vars={"@coll": cluster_coll, "min_size": min_size},
    )
    total = list(count_cursor)[0]

    cursor = db.aql.execute(
        """
        FOR c IN @@coll
            FILTER LENGTH(c.members) >= @min_size
            SORT (c.quality_score != null ? c.quality_score : 0) DESC, LENGTH(c.members) DESC
            LIMIT @offset, @limit
            RETURN {
                cluster_id: c._key,
                members: c.members,
                size: LENGTH(c.members),
                representative: c.representative,
                edge_count: c.edge_count,
                average_similarity: c.average_similarity,
                min_similarity: c.min_similarity,
                max_similarity: c.max_similarity,
                density: c.density,
                quality_score: c.quality_score
            }
        """,
        bind_vars={
            "@coll": cluster_coll,
            "min_size": min_size,
            "offset": offset,
            "limit": limit,
        },
    )
    return {"clusters": list(cursor), "total": total, "offset": offset, "limit": limit}


@router.get("/{collection}/stats")
async def cluster_stats(request: Request, collection: str) -> Dict[str, Any]:
    """Aggregate cluster statistics for a collection."""
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)

    from entity_resolution.ui.routes.collections import resolve_collection_name
    cluster_coll = resolve_collection_name(request, f"{collection}_clusters")
    if not db.has_collection(cluster_coll):
        return {"total_clusters": 0}

    cursor = db.aql.execute(
        """
        LET clusters = (FOR c IN @@coll RETURN c)
        LET sizes = clusters[*].size
        LET qualities = (
            FOR c IN clusters
                FILTER c.quality_score != null
                RETURN c.quality_score
        )
        RETURN {
            total_clusters: LENGTH(clusters),
            total_members: SUM(
                FOR c IN clusters RETURN LENGTH(c.members)
            ),
            avg_size: AVERAGE(
                FOR c IN clusters RETURN LENGTH(c.members)
            ),
            max_size: MAX(
                FOR c IN clusters RETURN LENGTH(c.members)
            ),
            avg_quality: AVERAGE(qualities),
            min_quality: MIN(qualities),
            max_quality: MAX(qualities)
        }
        """,
        bind_vars={"@coll": cluster_coll},
    )
    results = list(cursor)
    return results[0] if results else {"total_clusters": 0}


@router.get("/{collection}/{key}")
async def cluster_detail(request: Request, collection: str, key: str) -> Dict[str, Any]:
    """Full cluster detail with member documents."""
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)

    from entity_resolution.ui.routes.collections import resolve_collection_name
    cluster_coll = resolve_collection_name(request, f"{collection}_clusters")
    if not db.has_collection(cluster_coll):
        return {"error": f"Cluster collection {cluster_coll} not found"}

    cluster_doc = db.collection(cluster_coll).get(key)
    if cluster_doc is None:
        return {"error": f"Cluster '{key}' not found"}

    members = cluster_doc.get("members", [])
    member_docs = []
    coll = db.collection(collection) if db.has_collection(collection) else None
    for member_id in members:
        member_key = str(member_id).split("/")[-1]
        if coll is not None:
            doc = coll.get(member_key)
            if doc:
                member_docs.append(doc)

    return {
        "cluster_id": cluster_doc.get("_key"),
        "size": len(members),
        "representative": cluster_doc.get("representative"),
        "quality_score": cluster_doc.get("quality_score"),
        "density": cluster_doc.get("density"),
        "average_similarity": cluster_doc.get("average_similarity"),
        "members": member_docs,
    }


@router.get("/{collection}/{key}/graph")
async def cluster_graph(
    request: Request, collection: str, key: str
) -> ClusterGraphResponse:
    """Return nodes and edges for cluster visualization."""
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)

    from entity_resolution.ui.routes.collections import resolve_collection_name
    cluster_coll = resolve_collection_name(request, f"{collection}_clusters")
    edge_coll = resolve_collection_name(request, f"{collection}_similarity_edges")

    if not db.has_collection(cluster_coll):
        return ClusterGraphResponse(nodes=[], edges=[])

    cluster_doc = db.collection(cluster_coll).get(key)
    if cluster_doc is None:
        return ClusterGraphResponse(nodes=[], edges=[])

    members = cluster_doc.get("members", [])
    member_ids = [
        m if "/" in str(m) else f"{collection}/{m}" for m in members
    ]

    nodes: List[Dict[str, Any]] = []
    coll = db.collection(collection) if db.has_collection(collection) else None
    for mid in member_ids:
        member_key = str(mid).split("/")[-1]
        doc: Optional[Dict[str, Any]] = None
        if coll is not None:
            doc = coll.get(member_key)
        nodes.append({
            "id": mid,
            "key": member_key,
            "data": {k: v for k, v in (doc or {}).items() if not k.startswith("_")},
        })

    edges: List[Dict[str, Any]] = []
    if db.has_collection(edge_coll) and member_ids:
        cursor = db.aql.execute(
            """
            FOR e IN @@ec
                FILTER e._from IN @ids AND e._to IN @ids
                RETURN {
                    source: e._from,
                    target: e._to,
                    similarity: e.confidence,
                    method: e.method
                }
            """,
            bind_vars={"@ec": edge_coll, "ids": member_ids},
        )
        edges = list(cursor)

    return ClusterGraphResponse(nodes=nodes, edges=edges)
