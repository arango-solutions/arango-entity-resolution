"""Fellegi-Sunter EM estimation of per-field m/u probabilities.

Classic two-class Fellegi-Sunter expectation-maximization over binary
field-agreement vectors. Given comparison vectors from sampled candidate pairs
(no labels), it estimates, per field:

- ``m`` = P(field agrees | the pair is a true match)
- ``u`` = P(field agrees | the pair is a non-match)

and the match prior ``lambda`` = P(match) over the candidate set. These feed the
honest Fellegi-Sunter scorer (plan 0.2) so weights are learned from data rather
than hand-set, the defining unsupervised capability of Splink/Zingg.

The core (:func:`estimate_mu`) is pure numpy and dependency-free so it is unit
testable on synthetic data with known parameters. Higher layers build the
comparison vectors from real records and persist results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

_EPS = 1e-6


@dataclass
class EMResult:
    """Outcome of an EM run.

    ``m``/``u`` are per-field dicts keyed by field name; ``lambda_`` is the
    estimated match prior; ``converged``/``iterations`` describe the run.
    """

    fields: List[str]
    m: Dict[str, float]
    u: Dict[str, float]
    lambda_: float
    iterations: int
    converged: bool
    n_pairs: int
    log_likelihood: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "fields": list(self.fields),
            "m": dict(self.m),
            "u": dict(self.u),
            "lambda": self.lambda_,
            "iterations": self.iterations,
            "converged": self.converged,
            "n_pairs": self.n_pairs,
            "log_likelihood": self.log_likelihood,
        }


def estimate_mu(
    gamma: np.ndarray,
    field_names: Sequence[str],
    *,
    max_iterations: int = 50,
    tol: float = 1e-5,
    init_m: float = 0.9,
    init_u: float = 0.1,
    init_lambda: float = 0.1,
    weights: Optional[np.ndarray] = None,
) -> EMResult:
    """Estimate m/u/lambda from a binary agreement matrix via Fellegi-Sunter EM.

    Parameters
    ----------
    gamma:
        ``(n_pairs, n_fields)`` array of 0/1 agreement indicators.
    field_names:
        Names for the ``n_fields`` columns, in order.
    max_iterations, tol:
        Stop when the max parameter change between iterations is below ``tol``
        or after ``max_iterations``.
    init_m, init_u, init_lambda:
        Initial guesses. ``init_m > init_u`` biases the "match" class to be the
        high-agreement one, resolving the label-switching ambiguity.
    weights:
        Optional ``(n_pairs,)`` non-negative weights (e.g. counts when identical
        rows are collapsed). Defaults to all ones.

    Returns
    -------
    EMResult
    """
    gamma = np.asarray(gamma, dtype=np.float64)
    if gamma.ndim != 2:
        raise ValueError("gamma must be a 2D (n_pairs, n_fields) array")
    n_pairs, n_fields = gamma.shape
    if n_fields != len(field_names):
        raise ValueError(
            f"field_names has {len(field_names)} entries but gamma has {n_fields} columns"
        )
    if n_pairs == 0:
        raise ValueError("need at least one comparison vector")

    if weights is None:
        weights = np.ones(n_pairs, dtype=np.float64)
    else:
        weights = np.asarray(weights, dtype=np.float64)
        if weights.shape != (n_pairs,):
            raise ValueError("weights must have shape (n_pairs,)")
    total_w = weights.sum()

    m = np.full(n_fields, float(init_m))
    u = np.full(n_fields, float(init_u))
    lam = float(init_lambda)

    converged = False
    iterations = 0
    for iterations in range(1, max_iterations + 1):
        m_c = np.clip(m, _EPS, 1 - _EPS)
        u_c = np.clip(u, _EPS, 1 - _EPS)

        # E-step in log space (avoids underflow with many fields).
        # log P(gamma_i | M) = sum_f [ g*log m + (1-g)*log(1-m) ]
        log_m = gamma @ np.log(m_c) + (1 - gamma) @ np.log(1 - m_c)
        log_u = gamma @ np.log(u_c) + (1 - gamma) @ np.log(1 - u_c)
        log_pm = np.log(max(lam, _EPS)) + log_m
        log_pu = np.log(max(1 - lam, _EPS)) + log_u
        # Responsibility g_i = P(M | gamma_i) via stable log-sum-exp.
        max_log = np.maximum(log_pm, log_pu)
        denom = max_log + np.log(np.exp(log_pm - max_log) + np.exp(log_pu - max_log))
        resp = np.exp(log_pm - denom)  # (n_pairs,)

        # M-step (weighted).
        wr = weights * resp
        sum_match = wr.sum()
        new_lambda = sum_match / total_w
        new_m = (wr @ gamma) / max(sum_match, _EPS)
        w_non = weights * (1 - resp)
        sum_non = w_non.sum()
        new_u = (w_non @ gamma) / max(sum_non, _EPS)

        delta = max(
            float(np.max(np.abs(new_m - m))),
            float(np.max(np.abs(new_u - u))),
            abs(new_lambda - lam),
        )
        m, u, lam = new_m, new_u, new_lambda
        if delta < tol:
            converged = True
            break

    # Final log-likelihood (weighted) for diagnostics.
    m_c = np.clip(m, _EPS, 1 - _EPS)
    u_c = np.clip(u, _EPS, 1 - _EPS)
    log_m = gamma @ np.log(m_c) + (1 - gamma) @ np.log(1 - m_c)
    log_u = gamma @ np.log(u_c) + (1 - gamma) @ np.log(1 - u_c)
    log_pm = np.log(max(lam, _EPS)) + log_m
    log_pu = np.log(max(1 - lam, _EPS)) + log_u
    max_log = np.maximum(log_pm, log_pu)
    ll = float((weights * (max_log + np.log(np.exp(log_pm - max_log) + np.exp(log_pu - max_log)))).sum())

    # Resolve label switching: the match class must be the higher-agreement one.
    if float(np.mean(m)) < float(np.mean(u)):
        m, u = u, m
        lam = 1 - lam

    return EMResult(
        fields=list(field_names),
        m={f: float(v) for f, v in zip(field_names, m)},
        u={f: float(v) for f, v in zip(field_names, u)},
        lambda_=float(lam),
        iterations=iterations,
        converged=converged,
        n_pairs=int(n_pairs),
        log_likelihood=ll,
    )


@dataclass
class EMEstimator:
    """Builds agreement vectors from comparison records and runs :func:`estimate_mu`.

    A comparison record is a mapping of field name -> per-field similarity in
    [0, 1] (as produced by the similarity comparators). Agreement is binarized
    per field at ``agreement_thresholds[field]`` (default ``default_threshold``).
    """

    field_names: List[str]
    agreement_thresholds: Dict[str, float] = field(default_factory=dict)
    default_threshold: float = 0.85
    max_iterations: int = 50
    tol: float = 1e-5

    def build_gamma(self, comparisons: Sequence[Dict[str, float]]) -> np.ndarray:
        """Binarize similarity comparisons into a 0/1 agreement matrix.

        Missing field values are treated as disagreement (0).
        """
        rows = []
        for comp in comparisons:
            row = []
            for f in self.field_names:
                thr = self.agreement_thresholds.get(f, self.default_threshold)
                val = comp.get(f)
                row.append(1.0 if (val is not None and val >= thr) else 0.0)
            rows.append(row)
        if not rows:
            return np.empty((0, len(self.field_names)), dtype=np.float64)
        return np.asarray(rows, dtype=np.float64)

    def estimate(self, comparisons: Sequence[Dict[str, float]], **kwargs) -> EMResult:
        gamma = self.build_gamma(comparisons)
        return estimate_mu(
            gamma,
            self.field_names,
            max_iterations=self.max_iterations,
            tol=self.tol,
            **kwargs,
        )
