"""Integration tests for FeedbackApplicationService against a real ArangoDB.

These exercise the actual AQL the service relies on — UPSERT merge semantics,
the path-filtered ANY traversal, and INTERSECTION cluster/golden lookups —
which the unit tests can only approximate with in-memory fakes. Edges are
created via the real SimilarityEdgeService so the deterministic-key contract is
validated end-to-end.
"""

from __future__ import annotations

import uuid

import pytest

from entity_resolution.services.feedback_application_service import (
    FeedbackApplicationService,
)
from entity_resolution.services.similarity_edge_service import SimilarityEdgeService


@pytest.fixture
def er_collections(db_connection):
    """Create unique vertex/edge/cluster/golden collections; drop them after."""
    suffix = uuid.uuid4().hex[:8]
    names = {
        "vertex": f"itf_person_{suffix}",
        "edge": f"itf_similar_{suffix}",
        "cluster": f"itf_clusters_{suffix}",
        "golden": f"itf_golden_{suffix}",
    }
    db = db_connection
    db.create_collection(names["vertex"])
    db.create_collection(names["edge"], edge=True)
    db.create_collection(names["cluster"])
    db.create_collection(names["golden"])

    # Three records that form an A-B-C chain.
    db.collection(names["vertex"]).insert_many([
        {"_key": "A", "name": "Acme"},
        {"_key": "B", "name": "Acme Inc"},
        {"_key": "C", "name": "Acme Industries"},
    ])

    yield db, names

    for n in names.values():
        if db.has_collection(n):
            db.delete_collection(n)


def _service(db, names):
    return FeedbackApplicationService(
        db=db,
        edge_collection=names["edge"],
        vertex_collection=names["vertex"],
        cluster_collection=names["cluster"],
        golden_collection=names["golden"],
    )


def _seed_chain(db, names):
    """A-B (0.9) and B-C (0.55) via the real edge service; one {A,B,C} cluster."""
    edge_svc = SimilarityEdgeService(
        db=db,
        edge_collection=names["edge"],
        vertex_collection=names["vertex"],
        auto_create_collection=False,
    )
    edge_svc.create_edges([("A", "B", 0.9), ("B", "C", 0.55)])
    db.collection(names["cluster"]).insert({
        "_key": "cluster_000000", "cluster_id": 0,
        "members": [f"{names['vertex']}/A", f"{names['vertex']}/B", f"{names['vertex']}/C"],
        "member_keys": ["A", "B", "C"], "size": 3,
    })
    db.collection(names["golden"]).insert({
        "_key": "g_abc", "memberKeys": ["A", "B", "C"], "stale": False,
    })


def test_no_match_suppresses_real_edge_and_preserves_score(er_collections):
    db, names = er_collections
    _seed_chain(db, names)
    svc = _service(db, names)

    # Address the real edge created by SimilarityEdgeService (key contract).
    bc_key = svc._edge_key(svc._vid("B"), svc._vid("C"))
    assert db.collection(names["edge"]).get(bc_key) is not None  # contract holds

    svc.apply_verdict("B", "C", "no_match", actor="steward")

    edge = db.collection(names["edge"]).get(bc_key)
    assert edge["suppressed"] is True
    assert edge["suppressed_by"] == "steward"
    assert edge["similarity"] == 0.55  # UPSERT UPDATE merged, did not clobber


def test_reject_edge_splits_cluster_and_flags_golden_stale(er_collections):
    db, names = er_collections
    _seed_chain(db, names)
    svc = _service(db, names)

    result = svc.apply_and_recluster("B", "C", "no_match", actor="steward")

    # Cluster split: {A,B,C} -> {A,B} (C drops as a singleton).
    clusters = list(db.collection(names["cluster"]).all())
    member_sets = sorted(tuple(sorted(c["member_keys"])) for c in clusters)
    assert member_sets == [("A", "B")]

    # Golden record built from the old {A,B,C} cluster is flagged stale.
    g = db.collection(names["golden"]).get("g_abc")
    assert g["stale"] is True
    assert result["recluster"]["golden"]["flagged_stale"] == 1


def test_suppressed_edge_not_resurrected_on_rerun(er_collections):
    db, names = er_collections
    _seed_chain(db, names)
    svc = _service(db, names)

    svc.apply_and_recluster("B", "C", "no_match")
    # A second re-cluster of the same component must keep the split.
    again = svc.recluster_component("A")
    assert again["clusters_after"] == 1
    clusters = list(db.collection(names["cluster"]).all())
    member_sets = sorted(tuple(sorted(c["member_keys"])) for c in clusters)
    assert member_sets == [("A", "B")]


def test_match_below_threshold_creates_confirmed_edge_and_clusters(er_collections):
    db, names = er_collections
    # Only A and B exist as an edge; C is unconnected. Confirm A-C (no edge yet).
    edge_svc = SimilarityEdgeService(
        db=db, edge_collection=names["edge"], vertex_collection=names["vertex"],
        auto_create_collection=False,
    )
    edge_svc.create_edges([("A", "B", 0.9)])
    svc = _service(db, names)

    svc.apply_and_recluster("A", "C", "match", score=0.4)

    ac_key = svc._edge_key(svc._vid("A"), svc._vid("C"))
    edge = db.collection(names["edge"]).get(ac_key)
    assert edge is not None and edge["confirmed"] is True
    assert edge["similarity"] == 0.4  # no fabricated 1.0

    # A, B, C now one cluster (A-B and confirmed A-C).
    clusters = list(db.collection(names["cluster"]).all())
    assert len(clusters) == 1
    assert sorted(clusters[0]["member_keys"]) == ["A", "B", "C"]


def test_auto_refresh_deletes_orphaned_golden(er_collections):
    db, names = er_collections
    _seed_chain(db, names)
    svc = _service(db, names)

    svc.apply_and_recluster("B", "C", "no_match", auto_refresh=True)

    # Orphaned golden record (its {A,B,C} cluster no longer exists) is deleted.
    assert db.collection(names["golden"]).get("g_abc") is None
