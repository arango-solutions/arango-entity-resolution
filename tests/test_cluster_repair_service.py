"""Unit tests for cluster-repair analysis (plan 1.3)."""

from __future__ import annotations

import pytest

from entity_resolution.services.cluster_repair_service import analyze_cluster
from entity_resolution.services.evaluation_service import canonical_pair_id


def _pid(a, b):
    return canonical_pair_id(a, b)


def test_coherent_cluster_is_ok():
    members = ["a", "b", "c"]
    intra = {_pid("a", "b"): 0.95, _pid("a", "c"): 0.92, _pid("b", "c"): 0.90}
    out = analyze_cluster(members, intra, set(), min_coherence=0.5)
    assert out["status"] == "ok"


def test_bridge_cluster_splits_into_dense_halves():
    members = ["a", "b", "c", "d"]
    intra = {_pid("a", "b"): 0.95, _pid("c", "d"): 0.93, _pid("b", "c"): 0.20}
    out = analyze_cluster(members, intra, set(), min_coherence=0.5)
    assert out["status"] == "split"
    assert out["split_edge"] == _pid("b", "c")
    halves = sorted(tuple(h) for h in out["halves"])
    assert halves == [("a", "b"), ("c", "d")]


def test_confirmed_bridge_is_never_cut_and_queues():
    members = ["a", "b", "c", "d"]
    intra = {_pid("a", "b"): 0.95, _pid("c", "d"): 0.93, _pid("b", "c"): 0.20}
    confirmed = {_pid("b", "c")}  # human said b-c IS a match
    out = analyze_cluster(members, intra, confirmed, min_coherence=0.5)
    # The only weak edge is confirmed -> no eligible split -> queue (not a bad cut).
    assert out["status"] == "queue"


def test_healthy_cluster_never_flagged_so_no_split_manufactured():
    # All edges >= min_coherence -> mean >= min_coherence -> 'ok', never split.
    members = ["a", "b", "c"]
    intra = {_pid("a", "b"): 0.95, _pid("b", "c"): 0.92}  # dense path, both strong
    out = analyze_cluster(members, intra, set(), min_coherence=0.9)
    assert out["status"] == "ok"


def test_weakly_attached_leaf_is_split_off():
    # Tight pair {a,b} with a weak 0.3 edge dragging in c -> cut it, isolate c.
    members = ["a", "b", "c"]
    intra = {_pid("a", "b"): 0.95, _pid("b", "c"): 0.30}
    out = analyze_cluster(members, intra, set(), min_coherence=0.7)
    assert out["status"] == "split"
    assert out["split_edge"] == _pid("b", "c")
    halves = sorted(tuple(h) for h in out["halves"])
    assert halves == [("a", "b"), ("c",)]


def test_two_member_weak_cluster_queues():
    members = ["a", "b"]
    intra = {_pid("a", "b"): 0.2}
    out = analyze_cluster(members, intra, set(), min_coherence=0.5)
    assert out["status"] == "queue"


def test_no_intra_edges_queues():
    out = analyze_cluster(["a", "b"], {}, set(), min_coherence=0.5)
    assert out["status"] == "queue"
    assert out["reason"] == "no_intra_edges"
