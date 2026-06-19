"""Integration test: ModelParameterEstimator end-to-end on real ArangoDB (plan 1.1A)."""

from __future__ import annotations

import uuid

import pytest

from entity_resolution.learning import ModelParameterEstimator
from entity_resolution.services.batch_similarity_service import BatchSimilarityService


@pytest.fixture
def estimation_fixture(db_connection):
    suffix = uuid.uuid4().hex[:8]
    vcol = f"itm_person_{suffix}"
    ecol = f"itm_similar_{suffix}"
    db = db_connection
    db.create_collection(vcol)
    db.create_collection(ecol, edge=True)

    def vid(k):
        return f"{vcol}/{k}"

    # 10 near-duplicate (match-like) pairs and 10 clearly-different pairs.
    records = []
    edges = []
    for i in range(10):
        records += [
            # Match pairs: near-identical names (one-char variation), same city.
            {"_key": f"m{i}a", "name": "Jonathon Smith", "city": "Boston"},
            {"_key": f"m{i}b", "name": "Jonathan Smith", "city": "Boston"},
            # Non-match pairs: clearly different names and cities.
            {"_key": f"x{i}a", "name": "Alice Walker", "city": "Seattle"},
            {"_key": f"x{i}b", "name": "Bob Martinez", "city": "Miami"},
        ]
        edges += [
            {"_from": vid(f"m{i}a"), "_to": vid(f"m{i}b"), "similarity": 0.9},
            {"_from": vid(f"x{i}a"), "_to": vid(f"x{i}b"), "similarity": 0.3},
        ]
    db.collection(vcol).insert_many(records)
    db.collection(ecol).insert_many(edges)

    yield db, vcol, ecol
    for n in (vcol, ecol, "er_model_params", "er_term_frequencies"):
        if db.has_collection(n):
            db.delete_collection(n)


def test_estimate_persist_and_term_frequencies(estimation_fixture):
    db, vcol, ecol = estimation_fixture
    sim = BatchSimilarityService(
        db=db, collection=vcol,
        field_weights={"name": 0.6, "city": 0.4},
        similarity_algorithm="jaro_winkler",
    )
    estimator = ModelParameterEstimator(
        db=db, similarity_service=sim, edge_collection=ecol,
        field_names=["name", "city"], default_threshold=0.7,
    )

    out = estimator.run(source_collection=vcol, sample_size=100)

    # m should exceed u for both fields (matches agree far more often).
    model = out["model"]
    assert model["m"]["name"] > model["u"]["name"]
    assert model["m"]["city"] > model["u"]["city"]
    assert out["version"] == 1

    # Params persisted and reloadable.
    latest = estimator.load_latest()
    assert latest["version"] == 1
    assert latest["fields"] == ["name", "city"]

    # Term-frequency table: 'Boston' is the most common city.
    tf = db.collection("er_term_frequencies").get("city")
    assert tf is not None
    assert tf["top_values"][0]["value"] == "Boston"


def test_learned_params_drive_fs_scoring_and_separate_classes(estimation_fixture):
    """End-to-end: estimate m/u, score with FS, and verify it separates the classes."""
    db, vcol, ecol = estimation_fixture
    sim = BatchSimilarityService(
        db=db, collection=vcol,
        field_weights={"name": 0.6, "city": 0.4},
        similarity_algorithm="jaro_winkler",
    )
    estimator = ModelParameterEstimator(
        db=db, similarity_service=sim, edge_collection=ecol,
        field_names=["name", "city"], default_threshold=0.7,
    )
    estimator.run(source_collection=vcol, sample_size=100)

    # Build an FS-scoring similarity service from the learned params.
    from entity_resolution.learning.fellegi_sunter_scorer import FellegiSunterScorer

    doc = estimator.load_latest()
    fs_scorer = FellegiSunterScorer.from_model_doc(doc)
    fs_sim = BatchSimilarityService(
        db=db, collection=vcol,
        field_weights={"name": 0.6, "city": 0.4},
        similarity_algorithm="jaro_winkler",
        scoring_method="fellegi_sunter",
        fs_scorer=fs_scorer,
    )

    match_scores = fs_sim.compute_similarities([("m0a", "m0b")], threshold=0.0, return_all=True)
    non_scores = fs_sim.compute_similarities([("x0a", "x0b")], threshold=0.0, return_all=True)

    # FS posterior should be high for the match pair, low for the non-match.
    assert match_scores[0][2] > 0.9
    assert non_scores[0][2] < 0.1
    # And the posteriors are valid probabilities.
    assert 0.0 <= non_scores[0][2] < match_scores[0][2] <= 1.0
