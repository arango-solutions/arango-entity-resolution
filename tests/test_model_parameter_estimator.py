"""Unit tests for ModelParameterEstimator (plan 1.1 part A)."""

from __future__ import annotations

import numpy as np
import pytest

from entity_resolution.learning.model_parameter_estimator import (
    ModelParameterEstimator,
    config_hash,
)


class _FakeCollection:
    def __init__(self, name):
        self.name = name
        self.docs = {}

    def insert(self, doc, overwrite=False):
        self.docs[doc["_key"]] = dict(doc)

    def __iter__(self):
        return iter(self.docs.values())


class _FakeAQL:
    def __init__(self, db):
        self.db = db

    def execute(self, query, bind_vars=None):
        q = " ".join(query.split())
        bind_vars = bind_vars or {}
        if "SORT RAND()" in q:  # pair sampling
            return iter(self.db._sample_pairs[: bind_vars.get("n", 0)])
        if "MAX(d.version)" in q:  # next-version lookup
            coll = self.db._coll(bind_vars["@col"])
            versions = [d["version"] for d in coll.docs.values()
                        if d.get("config_hash") == bind_vars["h"]]
            return iter([max(versions)] if versions else [None])
        if "SORT d.version DESC" in q:  # load_latest
            coll = self.db._coll(bind_vars["@col"])
            docs = sorted(coll.docs.values(), key=lambda d: d["version"], reverse=True)
            return iter(docs[:1])
        return iter([])


class _FakeDB:
    def __init__(self, sample_pairs):
        self._collections = {}
        self._sample_pairs = sample_pairs
        self.aql = _FakeAQL(self)

    def _coll(self, name):
        return self._collections.setdefault(name, _FakeCollection(name))

    def has_collection(self, name):
        return name in self._collections

    def create_collection(self, name, edge=False):
        return self._coll(name)

    def collection(self, name):
        return self._coll(name)


class _StubSimilarityService:
    """Returns canned per-field scores for the sampled pairs."""

    algorithm_name = "jaro_winkler"

    def __init__(self, field_scores_by_pair):
        self._scores = field_scores_by_pair

    def compute_similarities_detailed(self, pairs, threshold=0.0):
        return [{"field_scores": self._scores[(a, b)]} for a, b in pairs]


def _make(sample_pairs, scores):
    db = _FakeDB(sample_pairs)
    svc = _StubSimilarityService(scores)
    est = ModelParameterEstimator(
        db=db, similarity_service=svc, edge_collection="similarTo",
        field_names=["name", "city"],
    )
    return db, est


def test_config_hash_stable_and_order_independent():
    a = config_hash(["name", "city"], {"name": 0.8, "city": 0.9}, "jaro_winkler")
    b = config_hash(["city", "name"], {"city": 0.9, "name": 0.8}, "jaro_winkler")
    assert a == b


def test_estimate_from_sampled_pairs():
    # 4 high-agreement (match-like) + 4 low-agreement (non-match-like) pairs.
    pairs = [(f"v/m{i}", f"v/n{i}") for i in range(4)] + [(f"v/x{i}", f"v/y{i}") for i in range(4)]
    scores = {}
    for i in range(4):
        scores[(f"m{i}", f"n{i}")] = {"name": 0.95, "city": 0.92}
        scores[(f"x{i}", f"y{i}")] = {"name": 0.10, "city": 0.15}
    # sample pairs come back as vertex-id pairs; estimator extracts keys.
    db, est = _make(pairs, scores)
    res = est.estimate(sample_size=8, max_iterations=100)
    assert res.m["name"] > res.u["name"]
    assert res.n_pairs == 8


def test_persist_versions_and_loads_latest():
    pairs = [("v/a", "v/b")]
    scores = {("a", "b"): {"name": 0.9, "city": 0.9}}
    db, est = _make(pairs, scores)
    res = est.estimate(sample_size=1, max_iterations=10)

    d1 = est.persist(res, sample_size=1)
    d2 = est.persist(res, sample_size=1)
    assert d1["version"] == 1 and d2["version"] == 2

    latest = est.load_latest()
    assert latest["version"] == 2
    assert "m" in latest and "u" in latest and "lambda" in latest


def test_empty_sample_raises():
    db, est = _make([], {})
    with pytest.raises(ValueError, match="no candidate pairs"):
        est.estimate(sample_size=10)
