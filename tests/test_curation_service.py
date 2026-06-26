"""Unit tests for CurationService (plan 2.0) using a fake ArangoDB."""

from __future__ import annotations

from typing import Any, Dict, List

from entity_resolution.services.curation_service import CurationService


class _FakeColl:
    def __init__(self):
        self.inserted: List[Dict[str, Any]] = []

    def insert(self, doc):
        self.inserted.append(doc)
        return {"_key": f"k{len(self.inserted)}"}


class _FakeAQL:
    def __init__(self, rows):
        self.rows = rows
        self.last_bind: Dict[str, Any] = {}
        self.last_query = ""

    def execute(self, query, bind_vars=None):
        self.last_query = str(query)
        self.last_bind = dict(bind_vars or {})
        return iter(self.rows)


class _FakeDB:
    def __init__(self, rows=None, has=True):
        self._coll = _FakeColl()
        self.aql = _FakeAQL(rows or [])
        self._has = has
        self.created: List[str] = []

    def has_collection(self, name):
        return self._has

    def create_collection(self, name):
        self.created.append(name)
        self._has = True

    def collection(self, name):
        return self._coll


def test_ensure_collection_created_when_missing():
    db = _FakeDB(has=False)
    CurationService(db)
    assert "er_audit_log" in db.created


def test_record_inserts_audit_doc():
    db = _FakeDB()
    svc = CurationService(db)
    key = svc.record(
        actor="alice", action="verdict", collection="customers",
        entity_key="p1", after={"decision": "match"},
    )
    assert key
    doc = db._coll.inserted[-1]
    assert doc["actor"] == "alice"
    assert doc["action"] == "verdict"
    assert doc["collection"] == "customers"
    assert doc["entity_key"] == "p1"
    assert doc["after"] == {"decision": "match"}
    assert "ts" in doc


def test_history_filters_and_limits():
    rows = [{"actor": "a", "action": "verdict", "entity_key": "p1"}]
    db = _FakeDB(rows=rows)
    svc = CurationService(db)
    out = svc.history("customers", "p1", limit=10)
    assert out == rows
    assert db.aql.last_bind["collection"] == "customers"
    assert db.aql.last_bind["entity_key"] == "p1"
    assert db.aql.last_bind["limit"] == 10


def test_history_rejects_bad_collection_name():
    import pytest
    db = _FakeDB()
    svc = CurationService(db)
    with pytest.raises(ValueError):
        svc.history("bad; name", "p1")
