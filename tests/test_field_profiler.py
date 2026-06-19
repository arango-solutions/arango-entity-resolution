"""Unit tests for schema-agnostic field profiling (plan 1.4)."""

from __future__ import annotations

import pytest

from entity_resolution.learning.field_profiler import (
    FieldProfiler,
    classify_values,
    field_config,
)


def _type(values):
    return classify_values(values)["type"]


def test_classifies_email():
    assert _type([f"user{i}@example.com" for i in range(20)]) == "email"


def test_classifies_phone():
    assert _type(["+1 (555) 123-4567", "555-987-6543", "(212) 555 0100"] * 5) == "phone"


def test_classifies_date():
    assert _type(["2024-01-01", "2023-12-31", "2020-06-15"] * 5) == "date"


def test_classifies_numeric():
    assert _type([str(i) for i in range(20)]) == "numeric"


def test_classifies_person_name():
    names = ["John Smith", "Jane Doe", "Bob Martinez", "Alice Walker", "Carl Yu"] * 4
    assert _type(names) == "person_name"


def test_classifies_org_name():
    orgs = ["Acme Inc", "Globex LLC", "Initech Corp", "Umbrella Corporation"] * 5
    assert _type(orgs) == "org_name"


def test_classifies_address():
    addrs = ["123 Main St", "456 Oak Avenue", "789 Elm Road", "12 Pine Blvd"] * 5
    assert _type(addrs) == "address"


def test_classifies_free_text():
    texts = ["This is a fairly long descriptive sentence about the entity in question."] * 10
    assert _type(texts) == "free_text"


def test_empty_values_default_free_text():
    assert _type([None, "", "   "]) == "free_text"


def test_field_config_has_comparator_and_priors():
    cfg = field_config("email", "email")
    assert cfg["algorithm"] == "jaro_winkler"
    assert "lower" in cfg["transformers"]
    assert cfg["m_prior"] > cfg["u_prior"]
    assert 0.0 < cfg["agreement_threshold"] <= 1.0


def test_phone_config_uses_digits_only():
    assert "digits_only" in field_config("phone", "phone")["transformers"]


class TestEmitConfig:
    def _profiler_with(self, profile):
        prof = FieldProfiler(db=None, collection="x")
        return prof.emit_similarity_config(profile)

    def test_emits_normalized_weights_and_skips_freetext(self):
        profile = {
            "collection": "people",
            "sampled_docs": 100,
            "fields": {
                "name": {"type": "person_name", "completeness": 1.0,
                         "stats": {}, "config": field_config("name", "person_name")},
                "email": {"type": "email", "completeness": 0.9,
                          "stats": {}, "config": field_config("email", "email")},
                "bio": {"type": "free_text", "completeness": 0.8,
                        "stats": {}, "config": field_config("bio", "free_text")},
                "rare": {"type": "person_name", "completeness": 0.1,
                         "stats": {}, "config": field_config("rare", "person_name")},
            },
        }
        out = self._profiler_with(profile)["similarity"]
        weights = out["field_weights"]
        assert "bio" not in weights       # free_text excluded
        assert "rare" not in weights      # below min_completeness
        assert set(weights) == {"name", "email"}
        assert abs(sum(weights.values()) - 1.0) < 1e-6  # normalized
        assert out["agreement_thresholds"]["email"] == 0.95
        assert "lower" in out["transformers"]["email"]
        assert out["m_priors"]["name"] > out["u_priors"]["name"]
