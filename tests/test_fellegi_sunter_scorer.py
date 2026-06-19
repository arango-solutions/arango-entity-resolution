"""Unit tests for the runtime FellegiSunterScorer (plan 1.1B)."""

from __future__ import annotations

import math

import pytest

from entity_resolution.learning.fellegi_sunter_scorer import FellegiSunterScorer


def _scorer(**kw):
    return FellegiSunterScorer(
        m={"name": 0.9, "city": 0.8},
        u={"name": 0.05, "city": 0.2},
        default_threshold=0.85,
        **kw,
    )


def test_full_agreement_scores_higher_than_full_disagreement():
    s = _scorer()
    agree = s.score({"name": 0.99, "city": 0.95})
    disagree = s.score({"name": 0.1, "city": 0.2})
    assert agree > 0.5 > disagree
    assert 0.0 <= disagree < agree <= 1.0


def test_posterior_matches_sigmoid_of_llr_plus_prior_logit():
    s = _scorer(match_prior=0.3)
    fs = {"name": 0.99, "city": 0.10}  # name agrees, city disagrees
    llr = math.log(0.9 / 0.05) + math.log((1 - 0.8) / (1 - 0.2))
    prior_logit = math.log(0.3 / 0.7)
    expected = 1.0 / (1.0 + math.exp(-(llr + prior_logit)))
    assert s.score(fs) == pytest.approx(expected)


def test_more_agreeing_fields_increase_posterior():
    s = _scorer()
    one = s.score({"name": 0.99, "city": 0.1})
    two = s.score({"name": 0.99, "city": 0.99})
    assert two > one


def test_missing_field_treated_as_disagreement():
    s = _scorer()
    explicit = s.score({"name": 0.99, "city": 0.0})
    missing = s.score({"name": 0.99})  # city absent
    assert missing == pytest.approx(explicit)


def test_from_model_doc_uses_stored_thresholds_and_lambda():
    doc = {
        "m": {"name": 0.9}, "u": {"name": 0.1},
        "agreement_thresholds": {"name": 0.6}, "lambda": 0.2,
    }
    s = FellegiSunterScorer.from_model_doc(doc)
    # sim 0.7 >= stored threshold 0.6 -> agreement, even though < default 0.85.
    assert s.score({"name": 0.7}) > s.score({"name": 0.5})
    assert s.match_prior == pytest.approx(0.2)


def test_rejects_empty_params():
    with pytest.raises(ValueError):
        FellegiSunterScorer(m={}, u={})
