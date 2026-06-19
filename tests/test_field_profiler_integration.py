"""Integration test: FieldProfiler against a real ArangoDB collection (plan 1.4)."""

from __future__ import annotations

import uuid

import pytest

from entity_resolution.learning import FieldProfiler


@pytest.fixture
def profiled_collection(db_connection):
    suffix = uuid.uuid4().hex[:8]
    col = f"itp_people_{suffix}"
    db = db_connection
    db.create_collection(col)
    docs = []
    for i in range(50):
        docs.append({
            "_key": f"p{i}",
            "name": ["John Smith", "Jane Doe", "Bob Martinez", "Alice Walker"][i % 4],
            "email": f"user{i}@example.com",
            "phone": f"+1 555-{1000 + i:04d}",
            "city": ["Boston", "Seattle", "Miami"][i % 3],
        })
    db.collection(col).insert_many(docs)
    yield db, col
    if db.has_collection(col):
        db.delete_collection(col)


def test_profile_detects_field_types(profiled_collection):
    db, col = profiled_collection
    prof = FieldProfiler(db=db, collection=col, sample_size=50).profile()

    fields = prof["fields"]
    assert fields["email"]["type"] == "email"
    assert fields["phone"]["type"] == "phone"
    assert fields["name"]["type"] == "person_name"
    assert all(info["completeness"] == 1.0 for info in fields.values())
    assert "_key" not in fields  # system fields excluded


def test_emit_config_produces_usable_similarity_block(profiled_collection):
    db, col = profiled_collection
    profiler = FieldProfiler(db=db, collection=col, sample_size=50)
    cfg = profiler.emit_similarity_config()["similarity"]

    assert set(cfg["field_weights"]) <= {"name", "email", "phone", "city"}
    # Weights are rounded seed values (renormalized downstream), so allow rounding slack.
    assert abs(sum(cfg["field_weights"].values()) - 1.0) < 1e-3
    assert cfg["transformers"]["phone"] == ["digits_only"]
    assert cfg["agreement_thresholds"]["email"] == 0.95
    # Seed priors present for EM to refine.
    assert cfg["m_priors"]["email"] > cfg["u_priors"]["email"]
