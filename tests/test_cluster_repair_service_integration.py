"""Integration tests for ClusterRepairService on real ArangoDB (plan 1.3)."""

from __future__ import annotations

import hashlib
import uuid

import pytest

from entity_resolution.services.cluster_repair_service import ClusterRepairService


def _det_key(vid_a, vid_b):
    """Deterministic edge key matching SimilarityEdgeService/FeedbackApplicationService."""
    a, b = sorted([vid_a, vid_b])
    return hashlib.md5(f"{a}->{b}".encode()).hexdigest()


@pytest.fixture
def repair_fixture(db_connection):
    suffix = uuid.uuid4().hex[:8]
    vcol = f"itr_person_{suffix}"
    ecol = f"itr_similar_{suffix}"
    ccol = f"itr_clusters_{suffix}"
    db = db_connection
    db.create_collection(vcol)
    db.create_collection(ecol, edge=True)
    db.create_collection(ccol)

    def vid(k):
        return f"{vcol}/{k}"

    # Bridge cluster: {a,b} and {c,d} tightly linked, joined by weak b-c.
    # Edges carry deterministic keys, exactly as the real edge service writes them.
    db.collection(vcol).insert_many([{"_key": k} for k in ("a", "b", "c", "d")])
    db.collection(ecol).insert_many([
        {"_key": _det_key(vid("a"), vid("b")), "_from": vid("a"), "_to": vid("b"), "similarity": 0.95},
        {"_key": _det_key(vid("c"), vid("d")), "_from": vid("c"), "_to": vid("d"), "similarity": 0.93},
        {"_key": _det_key(vid("b"), vid("c")), "_from": vid("b"), "_to": vid("c"), "similarity": 0.20},
    ])
    db.collection(ccol).insert({
        "_key": "cluster_000000",
        "members": [vid("a"), vid("b"), vid("c"), vid("d")],
        "member_keys": ["a", "b", "c", "d"],
        "size": 4,
    })

    yield db, vcol, ecol, ccol, vid
    for n in (vcol, ecol, ccol, "er_repair_queue"):
        if db.has_collection(n):
            db.delete_collection(n)


def _service(db, vcol, ecol, ccol):
    return ClusterRepairService(
        db=db, edge_collection=ecol, vertex_collection=vcol,
        cluster_collection=ccol, min_coherence=0.5,
    )


def test_analyze_flags_bridge_cluster(repair_fixture):
    db, vcol, ecol, ccol, vid = repair_fixture
    proposals = _service(db, vcol, ecol, ccol).analyze()
    assert len(proposals) == 1
    assert proposals[0]["status"] == "split"
    assert proposals[0]["cluster_key"] == "cluster_000000"


def test_auto_split_suppresses_bridge_and_reclusters(repair_fixture):
    db, vcol, ecol, ccol, vid = repair_fixture
    out = _service(db, vcol, ecol, ccol).repair(auto_split=True)

    assert len(out["split"]) == 1

    # The 4-member cluster is gone; two 2-member clusters remain.
    clusters = list(db.collection(ccol).all())
    member_sets = sorted(tuple(sorted(c["member_keys"])) for c in clusters)
    assert member_sets == [("a", "b"), ("c", "d")]

    # The bridge edge is suppressed by cluster_repair (not deleted).
    bridge = db.collection(ecol).get(_det_key(vid("b"), vid("c")))
    assert bridge["suppressed"] is True
    assert bridge["suppressed_by"] == "cluster_repair"


def test_queue_mode_persists_without_splitting(repair_fixture):
    db, vcol, ecol, ccol, vid = repair_fixture
    out = _service(db, vcol, ecol, ccol).repair(auto_split=False)

    # Nothing split; the flagged cluster is queued for review.
    assert out["split"] == []
    assert "cluster_000000" in out["queued"]
    assert db.has_collection("er_repair_queue")
    queued = db.collection("er_repair_queue").get("cluster_000000")
    assert queued["status"] == "pending"

    # Cluster left intact.
    assert len(list(db.collection(ccol).all())) == 1


def test_confirmed_bridge_is_not_split(repair_fixture):
    db, vcol, ecol, ccol, vid = repair_fixture
    # Mark the weak bridge as human-confirmed; repair must not cut it.
    db.collection(ecol).update({"_key": _det_key(vid("b"), vid("c")), "confirmed": True})

    out = _service(db, vcol, ecol, ccol).repair(auto_split=True)
    assert out["split"] == []  # confirmed edge protected
    assert "cluster_000000" in out["queued"]
