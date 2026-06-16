"""Tests for FeedbackApplicationService (plan 0.1 — closing the feedback loop)."""

from __future__ import annotations

import pytest

from entity_resolution.services.feedback_application_service import (
    FeedbackApplicationError,
    FeedbackApplicationService,
)


# ---------------------------------------------------------------------------
# In-memory fake ArangoDB that interprets the specific AQL the service issues.
# ---------------------------------------------------------------------------

class _FakeCollection:
    def __init__(self, name):
        self.name = name
        self.docs = {}

    def insert(self, doc, overwrite=False):
        key = doc["_key"]
        if key in self.docs and not overwrite:
            raise Exception(f"duplicate key {key}")
        self.docs[key] = dict(doc)

    def insert_many(self, docs, overwrite_mode=None):
        for d in docs:
            self.docs[d["_key"]] = dict(d)
        return len(docs)

    def update(self, doc):
        key = doc["_key"]
        if key not in self.docs:
            raise Exception("not found")
        self.docs[key].update(doc)

    def delete(self, key):
        if key not in self.docs:
            raise Exception("not found")
        del self.docs[key]

    def get(self, key):
        return self.docs.get(key)

    def count(self):
        return len(self.docs)

    def add_index(self, spec):
        return {"id": "ttl"}


class _FakeAQL:
    def __init__(self, db):
        self.db = db

    def execute(self, query, bind_vars=None):
        bind_vars = bind_vars or {}
        q = " ".join(query.split())

        if q.startswith("UPSERT"):
            edges = self.db._coll(bind_vars["@edges"])
            key = bind_vars["key"]
            if key in edges.docs:
                edges.docs[key].update(bind_vars["patch"])
            else:
                edges.docs[key] = dict(bind_vars["insert"])
            return iter([])

        if q.startswith("FOR e IN") and "RETURN { from" in q:
            # Active (non-suppressed) edges.
            edges = self.db._coll(bind_vars["@edges"])
            out = [
                {"from": e["_from"], "to": e["_to"]}
                for e in edges.docs.values()
                if not e.get("suppressed")
            ]
            return iter(out)

        if "INTERSECTION" in q and "@clusters" in bind_vars:
            clusters = self.db._coll(bind_vars["@clusters"])
            needle = set(bind_vars.get("touched") or bind_vars.get("seeds") or [])
            return iter([
                dict(c) for c in clusters.docs.values()
                if needle.intersection(c.get("member_keys", []))
            ])

        if "INTERSECTION" in q and "@golden" in bind_vars:
            golden = self.db._coll(bind_vars["@golden"])
            touched = set(bind_vars["touched"])
            return iter([
                dict(g) for g in golden.docs.values()
                if touched.intersection(g.get("memberKeys", []))
            ])

        return iter([])


class _FakeDB:
    def __init__(self):
        self._collections = {}
        self.aql = _FakeAQL(self)

    def _coll(self, name):
        return self._collections.setdefault(name, _FakeCollection(name))

    def has_collection(self, name):
        return name in self._collections

    def create_collection(self, name, edge=False):
        return self._coll(name)

    def collection(self, name):
        return self._coll(name)


def _service(db):
    return FeedbackApplicationService(
        db=db,
        edge_collection="similarTo",
        vertex_collection="Person",
        cluster_collection="person_clusters",
    )


def _add_edge(db, svc, ka, kb, score):
    from_id, to_id = svc._vid(ka), svc._vid(kb)
    key = svc._edge_key(from_id, to_id)
    c_from, c_to = (from_id, to_id) if from_id < to_id else (to_id, from_id)
    db._coll("similarTo").docs[key] = {
        "_key": key, "_from": c_from, "_to": c_to, "similarity": score,
    }
    return key


# ---------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------

def test_edge_key_matches_similarity_edge_service():
    """The service must address the same edges the pipeline created."""
    import hashlib

    svc = _service(_FakeDB())
    from_id, to_id = "Person/a", "Person/b"
    a, b = sorted([from_id, to_id])
    ref = hashlib.md5(f"{a}->{b}".encode()).hexdigest()
    assert svc._edge_key(from_id, to_id) == ref
    # Order-independent, matching SimilarityEdgeService deterministic keys.
    assert svc._edge_key(from_id, to_id) == svc._edge_key(to_id, from_id)


def test_union_find_groups_connected_vertices():
    svc = _service(_FakeDB())
    roots = svc._union_find([("Person/A", "Person/B"), ("Person/C", "Person/D")])
    assert roots["Person/A"] == roots["Person/B"]
    assert roots["Person/C"] == roots["Person/D"]
    assert roots["Person/A"] != roots["Person/C"]


def test_cluster_key_is_stable_and_order_independent():
    svc = _service(_FakeDB())
    assert svc._cluster_key(["a", "b", "c"]) == svc._cluster_key(["c", "a", "b"])


# ---------------------------------------------------------------------------
# apply_verdict edge writes
# ---------------------------------------------------------------------------

def test_no_match_suppresses_edge():
    db = _FakeDB()
    svc = _service(db)
    key = _add_edge(db, svc, "A", "B", 0.6)

    svc.apply_verdict("A", "B", "no_match", actor="alice")

    edge = db._coll("similarTo").docs[key]
    assert edge["suppressed"] is True
    assert edge["suppressed_by"] == "alice"
    assert edge["similarity"] == 0.6  # computed score preserved


def test_match_confirms_edge_without_fabricating_score():
    db = _FakeDB()
    svc = _service(db)
    key = _add_edge(db, svc, "A", "B", 0.62)

    svc.apply_verdict("A", "B", "match", actor="bob")

    edge = db._coll("similarTo").docs[key]
    assert edge["confirmed"] is True
    assert edge["confirmed_by"] == "bob"
    # Score must NOT be overwritten with 1.0 (would distort histograms/EM).
    assert edge["similarity"] == 0.62


def test_match_below_threshold_creates_confirmed_edge():
    db = _FakeDB()
    svc = _service(db)
    # No edge exists yet (pair was below blocking/scoring threshold).
    out = svc.apply_verdict("A", "B", "match", score=0.4)
    edge = db._coll("similarTo").docs[out["edge_key"]]
    assert edge["confirmed"] is True
    assert edge["similarity"] == 0.4


def test_invalid_decision_rejected():
    svc = _service(_FakeDB())
    with pytest.raises(ValueError):
        svc.apply_verdict("A", "B", "maybe")


# ---------------------------------------------------------------------------
# Keystone acceptance test: A-B-C chain, reject B-C -> {A,B} and {C}
# ---------------------------------------------------------------------------

def test_reject_edge_splits_cluster_and_survives_rerun():
    db = _FakeDB()
    svc = _service(db)

    _add_edge(db, svc, "A", "B", 0.9)
    bc_key = _add_edge(db, svc, "B", "C", 0.55)

    # Initial cluster {A,B,C}
    db._coll("person_clusters").docs["cluster_000000"] = {
        "_key": "cluster_000000", "cluster_id": 0,
        "members": ["Person/A", "Person/B", "Person/C"],
        "member_keys": ["A", "B", "C"], "size": 3,
    }

    result = svc.apply_and_recluster("B", "C", "no_match", actor="steward")

    # B-C edge suppressed (not deleted).
    assert db._coll("similarTo").docs[bc_key]["suppressed"] is True

    clusters = db._coll("person_clusters").docs
    # Old 3-member cluster gone; one new {A,B} cluster; C dropped as singleton.
    member_sets = sorted(tuple(c["member_keys"]) for c in clusters.values())
    assert member_sets == [("A", "B")]
    assert "cluster_000000" not in clusters
    assert result["recluster"]["clusters_after"] == 1

    # Re-running clustering must not resurrect the suppressed edge: the
    # union-find backend filters it out. Simulate a re-cluster of the component.
    again = svc.recluster_component("A")
    member_sets2 = sorted(tuple(c["member_keys"]) for c in db._coll("person_clusters").docs.values())
    assert member_sets2 == [("A", "B")]
    assert again["clusters_after"] == 1


# ---------------------------------------------------------------------------
# Concurrency lock
# ---------------------------------------------------------------------------

def test_concurrent_component_lock_blocks_second_verdict():
    db = _FakeDB()
    svc = _service(db)
    _add_edge(db, svc, "A", "B", 0.9)

    # Manually hold the lock for A's component.
    lock_key = svc._acquire_lock("A")
    assert lock_key is not None

    with pytest.raises(FeedbackApplicationError):
        svc.apply_and_recluster("A", "B", "match")

    svc._release_lock(lock_key)
    # After release, it succeeds.
    out = svc.apply_and_recluster("A", "B", "match")
    assert out["verdict"]["action"] == "match"


# ---------------------------------------------------------------------------
# 0.7 — golden-record staleness on cluster change
# ---------------------------------------------------------------------------

def _service_with_golden(db):
    return FeedbackApplicationService(
        db=db,
        edge_collection="similarTo",
        vertex_collection="Person",
        cluster_collection="person_clusters",
        golden_collection="golden_records",
    )


def _seed_split_scenario(db, svc):
    _add_edge(db, svc, "A", "B", 0.9)
    _add_edge(db, svc, "B", "C", 0.55)
    db._coll("person_clusters").docs["cluster_000000"] = {
        "_key": "cluster_000000", "cluster_id": 0,
        "members": ["Person/A", "Person/B", "Person/C"],
        "member_keys": ["A", "B", "C"], "size": 3,
    }
    db._coll("golden_records").docs["g_abc"] = {
        "_key": "g_abc", "memberKeys": ["A", "B", "C"], "stale": False,
        "sourceClusterHash": "orig",
    }


def test_golden_record_flagged_stale_when_cluster_changes():
    db = _FakeDB()
    svc = _service_with_golden(db)
    _seed_split_scenario(db, svc)

    result = svc.apply_and_recluster("B", "C", "no_match")

    g = db._coll("golden_records").docs["g_abc"]
    assert g["stale"] is True
    assert "staleReason" in g
    assert result["recluster"]["golden"]["flagged_stale"] == 1


def test_golden_record_deleted_on_auto_refresh():
    db = _FakeDB()
    svc = _service_with_golden(db)
    _seed_split_scenario(db, svc)

    result = svc.apply_and_recluster("B", "C", "no_match", auto_refresh=True)

    assert "g_abc" not in db._coll("golden_records").docs
    assert result["recluster"]["golden"]["deleted"] == 1


def test_golden_record_survives_when_cluster_unchanged():
    db = _FakeDB()
    svc = _service_with_golden(db)
    # A-B cluster with a matching golden record; confirm A-B (no membership change).
    _add_edge(db, svc, "A", "B", 0.9)
    db._coll("person_clusters").docs["cluster_000000"] = {
        "_key": "cluster_000000", "cluster_id": 0,
        "members": ["Person/A", "Person/B"],
        "member_keys": ["A", "B"], "size": 2,
    }
    db._coll("golden_records").docs["g_ab"] = {
        "_key": "g_ab", "memberKeys": ["A", "B"], "stale": False,
    }

    svc.apply_and_recluster("A", "B", "match")

    g = db._coll("golden_records").docs["g_ab"]
    assert g["stale"] is False  # member set still matches a live cluster
