"""Integration tests for EvaluationService against real ArangoDB (plan 1.2)."""

from __future__ import annotations

import uuid

import pytest

from entity_resolution.services.evaluation_service import (
    EvaluationService,
    canonical_pair_id,
)


@pytest.fixture
def eval_fixture(db_connection):
    suffix = uuid.uuid4().hex[:8]
    vcol = f"ite_person_{suffix}"
    ecol = f"ite_similar_{suffix}"
    ccol = f"ite_clusters_{suffix}"
    tcol = f"ite_truth_{suffix}"
    db = db_connection
    db.create_collection(vcol)
    db.create_collection(ecol, edge=True)
    db.create_collection(ccol)
    db.create_collection(tcol, edge=True)

    def vid(k):
        return f"{vcol}/{k}"

    # Scored edges: a-b strong (true), c-d medium (true), e-f medium (false).
    db.collection(ecol).insert_many([
        {"_from": vid("a"), "_to": vid("b"), "similarity": 0.95},
        {"_from": vid("c"), "_to": vid("d"), "similarity": 0.70},
        {"_from": vid("e"), "_to": vid("f"), "similarity": 0.65},
        # A suppressed edge must be ignored by the harness.
        {"_from": vid("g"), "_to": vid("h"), "similarity": 0.99, "suppressed": True},
    ])
    # Ground truth: a-b and c-d are real matches; e-f is not.
    db.collection(tcol).insert_many([
        {"_from": vid("a"), "_to": vid("b")},
        {"_from": vid("c"), "_to": vid("d")},
    ])
    # One cluster {a,b} (tight).
    db.collection(ccol).insert({
        "_key": "c1", "members": [vid("a"), vid("b")], "member_keys": ["a", "b"],
    })

    yield db, vcol, ecol, ccol, tcol, vid
    for n in (vcol, ecol, ccol, tcol):
        if db.has_collection(n):
            db.delete_collection(n)


def test_threshold_sweep_against_real_collections(eval_fixture):
    db, vcol, ecol, ccol, tcol, vid = eval_fixture
    service = EvaluationService(db, edge_collection=ecol)
    sweep = service.threshold_sweep(tcol)

    # Suppressed g-h edge excluded -> 3 scored pairs.
    assert sweep["n_scored"] == 3
    assert sweep["n_true_total"] == 2

    # At threshold 0.70: a-b and c-d predicted (both true), e-f at 0.65 excluded.
    p70 = next(p for p in sweep["points"] if p["threshold"] == 0.7)
    assert p70["true_positives"] == 2
    assert p70["false_positives"] == 0
    assert p70["precision"] == pytest.approx(1.0)
    assert p70["recall"] == pytest.approx(1.0)
    assert sweep["best_f1"]["f1"] == pytest.approx(1.0)


def test_cluster_quality_against_real_collections(eval_fixture):
    db, vcol, ecol, ccol, tcol, vid = eval_fixture
    service = EvaluationService(db, edge_collection=ecol)
    out = service.cluster_quality(ccol)

    assert out["n_clusters"] == 1
    cluster = out["clusters"][0]
    assert cluster["size"] == 2
    assert cluster["mean_edge_score"] == pytest.approx(0.95)
    assert cluster["low_coherence"] is False


def test_score_distribution_excludes_suppressed(eval_fixture):
    db, vcol, ecol, ccol, tcol, vid = eval_fixture
    service = EvaluationService(db, edge_collection=ecol)
    buckets = service.score_distribution(bucket=0.05)

    total = sum(b["count"] for b in buckets)
    assert total == 3  # suppressed g-h (0.99) excluded
    # 0.95 bucket present, 0.99 (suppressed) absent.
    los = {round(b["lo"], 2) for b in buckets}
    assert 0.95 in los
    # Each bucket is well-formed.
    for b in buckets:
        assert b["hi"] == pytest.approx(b["lo"] + 0.05)


def test_boundary_pairs_near_score(eval_fixture):
    db, vcol, ecol, ccol, tcol, vid = eval_fixture
    service = EvaluationService(db, edge_collection=ecol)
    pairs = service.boundary_pairs(0.68, window=0.05, limit=10)

    # 0.70 (c-d) and 0.65 (e-f) within 0.05 of 0.68; 0.95 and suppressed excluded.
    keys = {(p["key_a"], p["key_b"]) for p in pairs}
    assert ("c", "d") in keys
    assert ("e", "f") in keys
    assert ("a", "b") not in keys
    assert ("g", "h") not in keys
