"""Unit tests for Fellegi-Sunter EM estimation (plan 1.1)."""

from __future__ import annotations

import numpy as np
import pytest

from entity_resolution.learning.em_estimator import EMEstimator, estimate_mu


def _synthesize(rng, n, lam, m, u):
    """Generate (gamma, is_match) from known parameters."""
    m = np.asarray(m)
    u = np.asarray(u)
    is_match = rng.random(n) < lam
    probs = np.where(is_match[:, None], m[None, :], u[None, :])
    gamma = (rng.random((n, len(m))) < probs).astype(float)
    return gamma, is_match


def test_recovers_known_parameters():
    """Acceptance: EM recovers synthetic m/u/lambda within tolerance."""
    rng = np.random.default_rng(42)
    true_lambda = 0.2
    true_m = [0.95, 0.90, 0.85]
    true_u = [0.05, 0.10, 0.20]
    gamma, _ = _synthesize(rng, 40000, true_lambda, true_m, true_u)

    res = estimate_mu(gamma, ["f0", "f1", "f2"])

    assert res.converged
    assert res.lambda_ == pytest.approx(true_lambda, abs=0.03)
    for i, f in enumerate(["f0", "f1", "f2"]):
        assert res.m[f] == pytest.approx(true_m[i], abs=0.05)
        assert res.u[f] == pytest.approx(true_u[i], abs=0.05)


def test_resolves_label_switching_from_inverted_init():
    """Even initialized 'backwards', the match class ends up high-agreement."""
    rng = np.random.default_rng(7)
    gamma, _ = _synthesize(rng, 20000, 0.25, [0.92, 0.88], [0.08, 0.15])

    res = estimate_mu(gamma, ["a", "b"], init_m=0.1, init_u=0.9, init_lambda=0.9)

    # m must dominate u regardless of initialization.
    assert res.m["a"] > res.u["a"]
    assert res.m["b"] > res.u["b"]
    assert res.lambda_ < 0.5


def test_weights_collapse_equivalent_to_expanded():
    """Weighted unique patterns == expanding them into repeated rows."""
    patterns = np.array([[1.0, 1.0], [1.0, 0.0], [0.0, 0.0]])
    counts = np.array([500.0, 300.0, 200.0])
    weighted = estimate_mu(patterns, ["a", "b"], weights=counts, init_lambda=0.4)

    expanded = np.repeat(patterns, counts.astype(int), axis=0)
    full = estimate_mu(expanded, ["a", "b"], init_lambda=0.4)

    assert weighted.lambda_ == pytest.approx(full.lambda_, abs=1e-6)
    assert weighted.m["a"] == pytest.approx(full.m["a"], abs=1e-6)
    assert weighted.u["b"] == pytest.approx(full.u["b"], abs=1e-6)


def test_empty_input_raises():
    with pytest.raises(ValueError, match="at least one"):
        estimate_mu(np.empty((0, 2)), ["a", "b"])


def test_field_count_mismatch_raises():
    with pytest.raises(ValueError, match="columns"):
        estimate_mu(np.ones((3, 2)), ["only_one"])


def test_result_to_dict_roundtrips_fields():
    rng = np.random.default_rng(1)
    gamma, _ = _synthesize(rng, 5000, 0.3, [0.9, 0.8], [0.1, 0.2])
    d = estimate_mu(gamma, ["x", "y"]).to_dict()
    assert set(d["m"]) == {"x", "y"}
    assert 0.0 <= d["lambda"] <= 1.0
    assert d["n_pairs"] == 5000


class TestEMEstimatorWrapper:
    def test_build_gamma_binarizes_at_threshold(self):
        est = EMEstimator(field_names=["name", "city"], default_threshold=0.85)
        comparisons = [
            {"name": 0.95, "city": 0.40},
            {"name": 0.20, "city": 0.90},
            {"name": 0.86},  # city missing -> disagreement
        ]
        gamma = est.build_gamma(comparisons)
        assert gamma.tolist() == [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]]

    def test_per_field_thresholds(self):
        est = EMEstimator(
            field_names=["name", "zip"],
            agreement_thresholds={"name": 0.7, "zip": 0.99},
        )
        gamma = est.build_gamma([{"name": 0.75, "zip": 0.95}])
        assert gamma.tolist() == [[1.0, 0.0]]  # zip 0.95 < 0.99 -> disagree

    def test_estimate_end_to_end(self):
        rng = np.random.default_rng(3)
        # High-similarity matches vs low-similarity non-matches.
        comps = []
        for _ in range(8000):
            if rng.random() < 0.3:
                comps.append({"a": rng.uniform(0.85, 1.0), "b": rng.uniform(0.8, 1.0)})
            else:
                comps.append({"a": rng.uniform(0.0, 0.5), "b": rng.uniform(0.0, 0.6)})
        est = EMEstimator(field_names=["a", "b"], default_threshold=0.7)
        res = est.estimate(comps)
        assert res.m["a"] > res.u["a"]
        assert res.lambda_ == pytest.approx(0.3, abs=0.06)
