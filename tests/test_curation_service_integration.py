"""Integration test for CurationService against a real ArangoDB (plan 2.0)."""

from __future__ import annotations

import uuid

import pytest

from entity_resolution.services.curation_service import CurationService


@pytest.fixture
def audit_collection(db_connection):
    name = f"itc_audit_{uuid.uuid4().hex[:8]}"
    yield db_connection, name
    if db_connection.has_collection(name):
        db_connection.delete_collection(name)


def test_record_and_history_roundtrip(audit_collection):
    db, name = audit_collection
    svc = CurationService(db, audit_collection=name)
    assert db.has_collection(name)  # ensured on init

    svc.record(actor="alice", action="verdict", collection="people",
               entity_key="p1", after={"decision": "match"})
    svc.record(actor="bob", action="remove_member", collection="people", entity_key="p1")
    svc.record(actor="x", action="verdict", collection="people", entity_key="other")
    # Different collection, same key — must not leak into the people/p1 history.
    svc.record(actor="y", action="verdict", collection="orgs", entity_key="p1")

    hist = svc.history("people", "p1", limit=10)
    assert len(hist) == 2
    assert {h["actor"] for h in hist} == {"alice", "bob"}
    assert hist[0]["ts"] >= hist[1]["ts"]  # newest first
