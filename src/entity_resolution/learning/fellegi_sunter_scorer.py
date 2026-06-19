"""Fellegi-Sunter posterior scorer fed by learned (or configured) m/u.

Turns per-field similarity scores into a calibrated match posterior using
per-field m/u probabilities (typically EM-learned, see
:class:`entity_resolution.learning.model_parameter_estimator.ModelParameterEstimator`).
This is the runtime counterpart of the honest FS math added to the legacy
scorer in plan 0.2 — extracted so the active ``BatchSimilarityService`` path can
consume learned parameters.

``score(field_scores)`` returns the posterior P(match | agreement pattern):

    logit(posterior) = logit(prior) + sum_f LLR_f
    LLR_f = log(m_f / u_f)         if field f agrees (sim >= threshold)
          = log((1-m_f)/(1-u_f))   otherwise

The posterior is in [0, 1] and monotone in the summed log-likelihood ratio.
"""

from __future__ import annotations

import math
from typing import Dict, Mapping, Optional

_EPS = 1e-6


class FellegiSunterScorer:
    """Scores per-field similarities into a calibrated match posterior."""

    def __init__(
        self,
        m: Mapping[str, float],
        u: Mapping[str, float],
        *,
        agreement_thresholds: Optional[Mapping[str, float]] = None,
        default_threshold: float = 0.85,
        match_prior: float = 0.5,
    ) -> None:
        if not m or not u:
            raise ValueError("m and u must be non-empty per-field probability maps")
        self.fields = [f for f in m if f in u]
        if not self.fields:
            raise ValueError("m and u share no fields")
        self.m = {f: _clip(m[f]) for f in self.fields}
        self.u = {f: _clip(u[f]) for f in self.fields}
        self.agreement_thresholds = dict(agreement_thresholds or {})
        self.default_threshold = default_threshold
        self.match_prior = min(max(match_prior, _EPS), 1 - _EPS)
        self._prior_logit = math.log(self.match_prior / (1 - self.match_prior))
        # Precompute per-field agree/disagree LLRs.
        self._llr_agree = {f: math.log(self.m[f] / self.u[f]) for f in self.fields}
        self._llr_disagree = {
            f: math.log((1 - self.m[f]) / (1 - self.u[f])) for f in self.fields
        }

    @classmethod
    def from_model_doc(cls, doc: Dict, *, match_prior: Optional[float] = None) -> "FellegiSunterScorer":
        """Build from an ``er_model_params`` document (as persisted by 1.1A)."""
        return cls(
            m=doc["m"],
            u=doc["u"],
            agreement_thresholds=doc.get("agreement_thresholds"),
            match_prior=match_prior if match_prior is not None else doc.get("lambda", 0.5),
        )

    def total_llr(self, field_scores: Mapping[str, float]) -> float:
        """Sum of per-field log-likelihood ratios for an agreement pattern."""
        total = 0.0
        for f in self.fields:
            sim = field_scores.get(f)
            threshold = self.agreement_thresholds.get(f, self.default_threshold)
            agrees = sim is not None and sim >= threshold
            total += self._llr_agree[f] if agrees else self._llr_disagree[f]
        return total

    def score(self, field_scores: Mapping[str, float]) -> float:
        """Posterior match probability in [0, 1]."""
        return 1.0 / (1.0 + math.exp(-(self.total_llr(field_scores) + self._prior_logit)))


def _clip(p: float) -> float:
    return min(max(float(p), _EPS), 1 - _EPS)
