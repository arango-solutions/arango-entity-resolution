"""Unsupervised parameter learning for entity resolution (plan Phase 1).

Currently provides Fellegi-Sunter EM estimation of per-field m/u probabilities
(:mod:`entity_resolution.learning.em_estimator`), which converts the matcher
from hand-tuned weights to self-tuning ones.
"""

from .em_estimator import EMEstimator, EMResult, estimate_mu
from .fellegi_sunter_scorer import FellegiSunterScorer
from .model_parameter_estimator import ModelParameterEstimator, config_hash

__all__ = [
    "EMEstimator",
    "EMResult",
    "estimate_mu",
    "FellegiSunterScorer",
    "ModelParameterEstimator",
    "config_hash",
]
