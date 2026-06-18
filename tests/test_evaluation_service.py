"""Unit tests for the evaluation harness metric core (plan 1.2)."""

from __future__ import annotations

import pytest

from entity_resolution.services.evaluation_service import (
    canonical_pair_id,
    cluster_quality_summary,
    confusion_at,
    threshold_sweep,
)


def _truth(*pairs):
    return {canonical_pair_id(a, b) for a, b in pairs}


def test_canonical_pair_id_is_order_independent():
    assert canonical_pair_id("a", "b") == canonical_pair_id("b", "a")


def test_confusion_at_threshold():
    scored = [("a", "b", 0.9), ("c", "d", 0.6), ("e", "f", 0.3)]
    truth = _truth(("a", "b"), ("e", "f"))  # one high, one low
    out = confusion_at(scored, truth, threshold=0.5)
    assert out["true_positives"] == 1   # a-b
    assert out["false_positives"] == 1  # c-d
    assert out["false_negatives"] == 1  # e-f missed (below threshold)
    assert out["precision"] == pytest.approx(0.5)
    assert out["recall"] == pytest.approx(0.5)


def test_threshold_sweep_curve_and_best_f1():
    scored = [
        ("a", "b", 0.95),  # true
        ("c", "d", 0.80),  # true
        ("e", "f", 0.60),  # false
        ("g", "h", 0.40),  # true
    ]
    truth = _truth(("a", "b"), ("c", "d"), ("g", "h"))
    sweep = threshold_sweep(scored, truth)

    # One point per distinct score.
    assert [p["threshold"] for p in sweep["points"]] == [0.95, 0.8, 0.6, 0.4]

    # At 0.80: tp=2 (a-b, c-d), fp=0 -> precision 1.0, recall 2/3.
    p80 = next(p for p in sweep["points"] if p["threshold"] == 0.8)
    assert p80["true_positives"] == 2
    assert p80["false_positives"] == 0
    assert p80["precision"] == pytest.approx(1.0)
    assert p80["recall"] == pytest.approx(2 / 3)

    # Best F1 here is at 0.80 (P=1, R=0.667, F1=0.8) vs 0.40 (P=0.75, R=1, F1=0.857).
    assert sweep["best_f1"]["threshold"] == 0.4
    assert sweep["n_true_total"] == 3
    assert sweep["n_scored"] == 4


def test_threshold_sweep_recall_monotonic_nondecreasing_as_threshold_drops():
    scored = [("a", "b", 0.9), ("c", "d", 0.7), ("e", "f", 0.5)]
    truth = _truth(("a", "b"), ("c", "d"), ("e", "f"))
    sweep = threshold_sweep(scored, truth)
    recalls = [p["recall"] for p in sweep["points"]]  # thresholds descending
    assert recalls == sorted(recalls)  # non-decreasing as threshold falls


def test_threshold_sweep_explicit_grid():
    scored = [("a", "b", 0.9), ("c", "d", 0.4)]
    truth = _truth(("a", "b"))
    sweep = threshold_sweep(scored, truth, thresholds=[0.95, 0.5, 0.1])
    assert [p["threshold"] for p in sweep["points"]] == [0.95, 0.5, 0.1]
    assert sweep["points"][0]["true_positives"] == 0  # nothing >= 0.95
    assert sweep["points"][1]["true_positives"] == 1  # a-b >= 0.5


def test_duplicate_pairs_collapse_to_max_score():
    scored = [("a", "b", 0.4), ("b", "a", 0.9)]  # same pair, two scores
    truth = _truth(("a", "b"))
    out = confusion_at(scored, truth, threshold=0.8)
    assert out["n_scored"] == 1
    assert out["true_positives"] == 1  # max score 0.9 used


def test_recall_counts_blocking_misses():
    """A true pair never scored still counts against recall."""
    scored = [("a", "b", 0.9)]
    truth = _truth(("a", "b"), ("x", "y"))  # x-y was never produced by blocking
    out = confusion_at(scored, truth, threshold=0.5)
    assert out["recall"] == pytest.approx(0.5)         # vs all truth
    assert out["candidate_recall"] == pytest.approx(1.0)  # vs truth in candidates


class TestClusterQuality:
    def test_tight_vs_low_coherence_clusters(self):
        clusters = [["a", "b", "c"], ["x", "y"]]
        edge_scores = {
            canonical_pair_id("a", "b"): 0.95,
            canonical_pair_id("a", "c"): 0.92,
            canonical_pair_id("b", "c"): 0.90,
            canonical_pair_id("x", "y"): 0.30,  # weak cluster
        }
        out = cluster_quality_summary(clusters, edge_scores, min_coherence=0.5)
        assert out["n_clusters"] == 2
        assert out["low_coherence_clusters"] == 1
        tight = next(c for c in out["clusters"] if c["size"] == 3)
        assert tight["density"] == pytest.approx(1.0)
        assert tight["low_coherence"] is False

    def test_bridge_edge_flagged(self):
        # Two tight pairs {a,b} and {c,d} joined by a single weak b-c edge:
        # removing b-c disconnects the cluster, so it's a genuine bridge.
        clusters = [["a", "b", "c", "d"]]
        edge_scores = {
            canonical_pair_id("a", "b"): 0.95,
            canonical_pair_id("c", "d"): 0.93,
            canonical_pair_id("b", "c"): 0.20,  # weak bridge between the halves
        }
        out = cluster_quality_summary(clusters, edge_scores)
        assert out["clusters"][0]["possible_bridge"] is True
        assert out["clusters"][0]["density"] < 1.0

    def test_singletons_counted_separately(self):
        out = cluster_quality_summary([["a"], ["b", "c"]], {canonical_pair_id("b", "c"): 0.9})
        assert out["n_singletons"] == 1
        assert out["n_clusters"] == 1

    def test_size_histogram(self):
        clusters = [["a", "b"], ["c", "d", "e"], list("fghijklmno")]  # sizes 2, 3, 10
        out = cluster_quality_summary(clusters, {})
        assert out["size_distribution"]["2"] == 1
        assert out["size_distribution"]["3-5"] == 1
        assert out["size_distribution"]["6-10"] == 1
