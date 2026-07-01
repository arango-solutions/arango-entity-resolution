"""Integration tests for Phase 2.2 cluster-editing curation routes.

Drives the FastAPI routes end-to-end against a real ArangoDB via TestClient:
remove-member / merge / split each apply to the similarity graph
(suppress/confirm edges + scoped re-cluster) and write an audit entry.
"""

from __future__ import annotations

import uuid

import pytest
from starlette.testclient import TestClient

from entity_resolution.ui.app import create_app
from entity_resolution.services.similarity_edge_service import SimilarityEdgeService


@pytest.fixture
def er_app(db_connection):
    suffix = uuid.uuid4().hex[:8]
    vcol = f"itc_person_{suffix}"
    ecol = f"{vcol}_similarity_edges"
    ccol = f"{vcol}_clusters"
    gcol = f"{vcol}_golden_records"
    db = db_connection
    db.create_collection(vcol)
    db.create_collection(ecol, edge=True)
    db.create_collection(ccol)
    db.create_collection(gcol)
    db.collection(vcol).insert_many([
        {"_key": "A", "name": "Acme"},
        {"_key": "B", "name": "Acme Inc"},
        {"_key": "C", "name": "Acme Industries"},
    ])
    client = TestClient(create_app(db=db))
    yield db, vcol, ecol, ccol, client
    for n in (vcol, ecol, ccol, gcol):
        if db.has_collection(n):
            db.delete_collection(n)


def _triangle(db, vcol, ecol, ccol):
    """A-B, B-C, A-C edges + one {A,B,C} cluster."""
    edge_svc = SimilarityEdgeService(
        db=db, edge_collection=ecol, vertex_collection=vcol, auto_create_collection=False,
    )
    edge_svc.create_edges([("A", "B", 0.9), ("B", "C", 0.85), ("A", "C", 0.8)])
    db.collection(ccol).insert({
        "_key": "cluster_000000", "cluster_id": 0,
        "members": [f"{vcol}/A", f"{vcol}/B", f"{vcol}/C"],
        "member_keys": ["A", "B", "C"], "size": 3,
    })


def test_remove_member_route_splits_and_audits(er_app):
    db, vcol, ecol, ccol, client = er_app
    _triangle(db, vcol, ecol, ccol)

    resp = client.post(
        f"/api/curation/{vcol}/cluster/cluster_000000/remove-member",
        json={"member_key": "B"},
        headers={"X-Reviewer": "steward"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"

    # A-C keeps {A,C}; B ejected to a singleton (dropped).
    clusters = list(db.collection(ccol).all())
    member_sets = sorted(tuple(sorted(c["member_keys"])) for c in clusters)
    assert member_sets == [("A", "C")]

    # Audit trail recorded against the cluster key.
    hist = client.get(f"/api/curation/{vcol}/history/cluster_000000").json()["entries"]
    assert any(e["action"] == "remove_member" and e["actor"] == "steward" for e in hist)


def test_merge_route_joins_clusters(er_app):
    db, vcol, ecol, ccol, client = er_app
    edge_svc = SimilarityEdgeService(
        db=db, edge_collection=ecol, vertex_collection=vcol, auto_create_collection=False,
    )
    edge_svc.create_edges([("A", "B", 0.9)])
    # C alone; two clusters {A,B} and {C} — but singletons aren't stored, so
    # seed {A,B} and a second real pair to merge.
    db.collection(vcol).insert({"_key": "D", "name": "Beta"})
    edge_svc.create_edges([("C", "D", 0.9)])
    db.collection(ccol).insert_many([
        {"_key": "c1", "members": [f"{vcol}/A", f"{vcol}/B"], "member_keys": ["A", "B"], "size": 2},
        {"_key": "c2", "members": [f"{vcol}/C", f"{vcol}/D"], "member_keys": ["C", "D"], "size": 2},
    ])

    resp = client.post(f"/api/curation/{vcol}/merge", json={"cluster_keys": ["c1", "c2"]})
    assert resp.status_code == 200, resp.text

    clusters = list(db.collection(ccol).all())
    member_sets = sorted(tuple(sorted(c["member_keys"])) for c in clusters)
    assert member_sets == [("A", "B", "C", "D")]


def test_split_route_suppresses_bridge(er_app):
    db, vcol, ecol, ccol, client = er_app
    edge_svc = SimilarityEdgeService(
        db=db, edge_collection=ecol, vertex_collection=vcol, auto_create_collection=False,
    )
    # Chain A-B (strong), B-C (weak bridge).
    edge_svc.create_edges([("A", "B", 0.9), ("B", "C", 0.55)])
    db.collection(ccol).insert({
        "_key": "cluster_000000", "members": [f"{vcol}/A", f"{vcol}/B", f"{vcol}/C"],
        "member_keys": ["A", "B", "C"], "size": 3,
    })

    resp = client.post(
        f"/api/curation/{vcol}/cluster/cluster_000000/split",
        json={"key_a": "B", "key_b": "C"},
    )
    assert resp.status_code == 200, resp.text

    clusters = list(db.collection(ccol).all())
    member_sets = sorted(tuple(sorted(c["member_keys"])) for c in clusters)
    assert member_sets == [("A", "B")]


def test_suspect_clusters_route_reads_repair_queue(er_app):
    db, vcol, ecol, ccol, client = er_app
    _triangle(db, vcol, ecol, ccol)
    if not db.has_collection("er_repair_queue"):
        db.create_collection("er_repair_queue")
    db.collection("er_repair_queue").insert({
        "_key": "cluster_000000", "cluster_key": "cluster_000000",
        "reason": "low_coherence", "mean_edge_score": 0.4,
        "members": ["A", "B", "C"], "status": "pending",
    }, overwrite=True)

    resp = client.get(f"/api/curation/{vcol}/suspect-clusters")
    assert resp.status_code == 200, resp.text
    keys = [c["cluster_key"] for c in resp.json()["clusters"]]
    assert "cluster_000000" in keys
