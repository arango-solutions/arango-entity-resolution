"""Curation endpoints (plan 2.0 audit + 2.2 cluster editing).

Cluster edits route through :class:`FeedbackApplicationService` so every
manual change (remove-member / merge / split) applies to the similarity graph
the same way a review verdict does — suppress/confirm edges (never hard-delete),
scoped re-cluster under a lock — and is written to ``er_audit_log``.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from entity_resolution.ui.models.schemas import (
    MergeClustersRequest,
    RemoveMemberRequest,
    SplitClusterRequest,
)

router = APIRouter(prefix="/api/curation", tags=["curation"])

_REPAIR_QUEUE = "er_repair_queue"


def _db(request: Request):
    return request.app.state.db


def _validate(collection: str) -> None:
    from entity_resolution.utils.validation import validate_collection_name

    try:
        validate_collection_name(collection)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _build_applier(request: Request, collection: str):
    """Resolve derived collections and construct a FeedbackApplicationService.

    Returns ``(applier, cluster_coll)`` or raises 404 when no similarity edges
    exist yet for the collection.
    """
    from entity_resolution.services.feedback_application_service import (
        FeedbackApplicationService,
    )
    from entity_resolution.ui.routes.collections import resolve_collection_name

    db = _db(request)
    edge_coll = resolve_collection_name(request, f"{collection}_similarity_edges")
    cluster_coll = resolve_collection_name(request, f"{collection}_clusters")
    golden_coll = resolve_collection_name(request, f"{collection}_golden_records")
    if not db.has_collection(edge_coll):
        raise HTTPException(status_code=404, detail="No similarity edges for collection")
    applier = FeedbackApplicationService(
        db=db,
        edge_collection=edge_coll,
        vertex_collection=collection,
        cluster_collection=cluster_coll,
        golden_collection=golden_coll,
    )
    return applier, cluster_coll


def _cluster_member_keys(db, cluster_coll: str, key: str) -> List[str]:
    if not db.has_collection(cluster_coll):
        raise HTTPException(status_code=404, detail="Cluster collection not found")
    doc = db.collection(cluster_coll).get(key)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Cluster '{key}' not found")
    return list(doc.get("member_keys") or [])


def _audit(request: Request, collection: str, action: str, entity_key: str,
           before: Any, after: Any) -> None:
    from entity_resolution.services.curation_service import CurationService

    actor = getattr(request.state, "reviewer", None) or "human"
    try:
        CurationService(_db(request)).record(
            actor=actor, action=action, collection=collection,
            entity_key=entity_key, before=before, after=after,
        )
    except Exception:  # auditing must never block the edit
        pass


def _guard_writable(request: Request, collection: str) -> None:
    if request.app.state.readonly:
        raise HTTPException(status_code=403, detail="Read-only mode")
    _validate(collection)


@router.post("/{collection}/cluster/{key}/remove-member")
async def remove_member(
    request: Request,
    collection: str,
    key: str,
    body: RemoveMemberRequest,
) -> Dict[str, Any]:
    """Eject a member from a cluster (suppress its intra-cluster edges)."""
    from entity_resolution.services.feedback_application_service import (
        FeedbackApplicationError,
    )

    _guard_writable(request, collection)
    db = _db(request)
    applier, cluster_coll = _build_applier(request, collection)
    members = _cluster_member_keys(db, cluster_coll, key)
    if body.member_key not in members:
        raise HTTPException(status_code=400, detail="member_key not in cluster")

    others = [m for m in members if m != body.member_key]
    try:
        result = applier.remove_member(body.member_key, others,
                                       actor=getattr(request.state, "reviewer", None) or "human")
    except FeedbackApplicationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    _audit(request, collection, "remove_member", key,
           before={"members": members},
           after={"removed": body.member_key, "cluster_keys": result["recluster"]["cluster_keys"]})
    return {"status": "ok", "clusters_changed": result["recluster"]["cluster_keys"],
            "recluster": result["recluster"]}


@router.post("/{collection}/merge")
async def merge_clusters(
    request: Request,
    collection: str,
    body: MergeClustersRequest,
) -> Dict[str, Any]:
    """Merge two or more clusters by confirming edges between representatives."""
    from entity_resolution.services.feedback_application_service import (
        FeedbackApplicationError,
    )

    _guard_writable(request, collection)
    db = _db(request)
    applier, cluster_coll = _build_applier(request, collection)

    reps: List[str] = []
    before: Dict[str, Any] = {}
    for ck in body.cluster_keys:
        members = _cluster_member_keys(db, cluster_coll, ck)
        if not members:
            raise HTTPException(status_code=400, detail=f"Cluster '{ck}' has no members")
        reps.append(members[0])
        before[ck] = members

    try:
        result = applier.merge_members(reps,
                                       actor=getattr(request.state, "reviewer", None) or "human")
    except FeedbackApplicationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    _audit(request, collection, "merge", body.cluster_keys[0],
           before=before,
           after={"cluster_keys": result["recluster"]["cluster_keys"]})
    return {"status": "ok", "clusters_changed": result["recluster"]["cluster_keys"],
            "recluster": result["recluster"]}


@router.post("/{collection}/cluster/{key}/split")
async def split_cluster(
    request: Request,
    collection: str,
    key: str,
    body: SplitClusterRequest,
) -> Dict[str, Any]:
    """Split a cluster by suppressing a bridge edge between two members."""
    from entity_resolution.services.feedback_application_service import (
        FeedbackApplicationError,
    )

    _guard_writable(request, collection)
    db = _db(request)
    applier, cluster_coll = _build_applier(request, collection)
    members = _cluster_member_keys(db, cluster_coll, key)
    if body.key_a not in members or body.key_b not in members:
        raise HTTPException(status_code=400, detail="both keys must belong to the cluster")

    try:
        result = applier.apply_and_recluster(
            body.key_a, body.key_b, "no_match",
            actor=getattr(request.state, "reviewer", None) or "human",
        )
    except FeedbackApplicationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    _audit(request, collection, "split", key,
           before={"members": members},
           after={"suppressed_edge": [body.key_a, body.key_b],
                  "cluster_keys": result["recluster"]["cluster_keys"]})
    return {"status": "ok", "clusters_changed": result["recluster"]["cluster_keys"],
            "recluster": result["recluster"]}


@router.get("/{collection}/suspect-clusters")
async def suspect_clusters(
    request: Request,
    collection: str,
    limit: int = 50,
) -> Dict[str, Any]:
    """Pending entries from the cluster repair queue, scoped to this collection."""
    from entity_resolution.ui.routes.collections import resolve_collection_name

    _validate(collection)
    db = _db(request)
    if not db.has_collection(_REPAIR_QUEUE):
        return {"clusters": []}
    cluster_coll = resolve_collection_name(request, f"{collection}_clusters")
    # Scope to this collection's clusters: the queue is keyed by cluster _key,
    # so keep only entries whose cluster still lives in this cluster collection.
    cursor = db.aql.execute(
        """
        FOR q IN @@queue
            FILTER q.status == "pending"
            FILTER DOCUMENT(CONCAT(@cc, "/", q.cluster_key)) != null
            SORT q.mean_edge_score ASC
            LIMIT @limit
            RETURN q
        """,
        bind_vars={"@queue": _REPAIR_QUEUE, "cc": cluster_coll, "limit": limit},
    )
    return {"clusters": list(cursor)}


@router.get("/{collection}/history/{key}")
async def curation_history(
    request: Request,
    collection: str,
    key: str,
    limit: int = 50,
) -> Dict[str, Any]:
    """Return the audit trail (newest first) for a cluster/entity/pair key."""
    from entity_resolution.services.curation_service import CurationService

    _validate(collection)
    db = _db(request)
    service = CurationService(db)
    return {"entries": service.history(collection, key, limit=limit)}
