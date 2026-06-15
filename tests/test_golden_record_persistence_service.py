from __future__ import annotations

import pytest

from entity_resolution.services.golden_record_persistence_service import GoldenRecordPersistenceService


@pytest.fixture
def db():
    class MockCollection:
        def __init__(self, name: str, edge: bool = False):
            self.name = name
            self.edge = edge
            self.docs_by_key = {}
            self.docs = []

        def get(self, key):
            return self.docs_by_key.get(key)

        def insert_many(self, docs, overwrite_mode=None):
            # Minimal overwrite semantics:
            # - update: merge by _key
            # - ignore: skip if exists
            for d in docs:
                k = d.get("_key")
                if k is None:
                    continue
                if overwrite_mode == "ignore" and k in self.docs_by_key:
                    continue
                if overwrite_mode == "update" and k in self.docs_by_key:
                    existing = dict(self.docs_by_key[k])
                    existing.update(d)
                    self.docs_by_key[k] = existing
                else:
                    self.docs_by_key[k] = dict(d)
            self.docs = list(self.docs_by_key.values())
            return len(docs)

        def __iter__(self):
            return iter(self.docs)

    class MockDB:
        def __init__(self):
            self._collections = {}

        def has_collection(self, name):
            return name in self._collections

        def create_collection(self, name, edge=False, system=False):
            self._collections[name] = MockCollection(name, edge=edge)
            return self._collections[name]

        def collection(self, name):
            return self._collections[name]

    db = MockDB()

    people = db.create_collection("Person")
    people.docs_by_key["p1"] = {"_key": "p1", "_id": "Person/p1", "name": "Alice", "panNumber": "AAAAA0000A"}
    people.docs_by_key["p2"] = {"_key": "p2", "_id": "Person/p2", "name": "Alice", "panNumber": "AAAAA0000A"}
    people.docs_by_key["p3"] = {"_key": "p3", "_id": "Person/p3", "name": "Bob", "panNumber": "BBBBB0000B"}

    clusters = db.create_collection("person_clusters")
    clusters.docs = [
        {"_key": "cluster_000001", "cluster_id": 1, "members": ["Person/p1", "Person/p2"], "member_keys": ["p1", "p2"]},
        {"_key": "cluster_000002", "cluster_id": 2, "members": ["Person/p3"], "member_keys": ["p3"]},
    ]

    return db


def test_persists_golden_records_and_resolvedto_edges(db):
    svc = GoldenRecordPersistenceService(
        db=db,
        source_collection="Person",
        cluster_collection="person_clusters",
        golden_collection="GoldenRecord",
        resolved_edge_collection="resolvedTo",
        include_fields=["name", "panNumber"],
        include_provenance=False,
    )
    out = svc.run(run_id="run-test", min_cluster_size=2)

    assert out["clusters_processed"] == 1
    assert out["golden_records_upserted"] == 1
    assert out["resolved_edges_upserted"] == 2

    golden = db.collection("GoldenRecord")
    assert len(golden.docs) == 1
    gr = golden.docs[0]
    assert gr["clusterSize"] == 2
    assert gr["name"] == "Alice"
    assert gr["panNumber"] == "AAAAA0000A"

    edges = db.collection("resolvedTo")
    assert len(edges.docs) == 2
    tos = {e["_to"] for e in edges.docs}
    assert len(tos) == 1

    # 0.7: golden records carry a source-cluster hash and a stale flag so
    # cluster changes can later invalidate them.
    assert gr["stale"] is False
    assert gr["sourceClusterHash"] == GoldenRecordPersistenceService.cluster_hash(
        gr["memberKeys"]
    )


def test_idempotent_rerun_does_not_create_more_goldens_or_edges(db):
    svc = GoldenRecordPersistenceService(
        db=db,
        source_collection="Person",
        cluster_collection="person_clusters",
        golden_collection="GoldenRecord",
        resolved_edge_collection="resolvedTo",
        include_fields=["name", "panNumber"],
        include_provenance=False,
    )
    svc.run(run_id="run-test", min_cluster_size=2)
    svc.run(run_id="run-test-2", min_cluster_size=2)

    assert len(db.collection("GoldenRecord").docs) == 1
    assert len(db.collection("resolvedTo").docs) == 2



@pytest.fixture
def survivorship_db(db):
    """Three-member cluster with conflicting field values for strategy tests."""
    people = db.collection("Person")
    people.docs_by_key["s1"] = {
        "_key": "s1", "_id": "Person/s1",
        "name": "Bob", "email": "bob@a.com",
        "updated_at": "2024-01-01T00:00:00Z", "source": "crm",
    }
    people.docs_by_key["s2"] = {
        "_key": "s2", "_id": "Person/s2",
        "name": "Robert Smith", "email": "bob@b.com",
        "updated_at": "2026-03-01T00:00:00Z", "source": "web_signup",
    }
    people.docs_by_key["s3"] = {
        "_key": "s3", "_id": "Person/s3",
        "name": "Bob", "email": "bob@c.com",
        "updated_at": "2025-06-01T00:00:00Z", "source": "import",
    }
    db.collection("person_clusters").docs.append(
        {"_key": "cluster_000003", "cluster_id": 3,
         "members": ["Person/s1", "Person/s2", "Person/s3"],
         "member_keys": ["s1", "s2", "s3"]}
    )
    return db


def _run(svc_db, **kwargs):
    svc = GoldenRecordPersistenceService(
        db=svc_db,
        source_collection="Person",
        cluster_collection="person_clusters",
        golden_collection="GoldenRecord",
        resolved_edge_collection="resolvedTo",
        **kwargs,
    )
    svc.run(run_id="run-strategy", min_cluster_size=3)
    return next(g for g in svc_db.collection("GoldenRecord").docs if g["clusterSize"] == 3)


def test_field_voting_default_picks_most_frequent(survivorship_db):
    gr = _run(survivorship_db, include_fields=["name"])
    assert gr["name"] == "Bob"
    assert gr["mergeStrategy"] == "field_voting"


def test_most_complete_picks_longest_value(survivorship_db):
    gr = _run(survivorship_db, include_fields=["name"], merge_strategy="most_complete")
    assert gr["name"] == "Robert Smith"


def test_most_recent_picks_value_from_latest_doc(survivorship_db):
    gr = _run(
        survivorship_db,
        include_fields=["name", "email"],
        merge_strategy="most_recent",
        recency_field="updated_at",
    )
    assert gr["name"] == "Robert Smith"
    assert gr["email"] == "bob@b.com"


def test_source_priority_picks_value_from_ranked_source(survivorship_db):
    gr = _run(
        survivorship_db,
        include_fields=["email"],
        merge_strategy="source_priority",
        source_field="source",
        source_priority=["import", "crm", "web_signup"],
    )
    assert gr["email"] == "bob@c.com"


def test_per_field_strategy_overrides(survivorship_db):
    gr = _run(
        survivorship_db,
        include_fields=["name", "email"],
        merge_strategy="field_voting",
        field_strategies={"email": "most_recent"},
        recency_field="updated_at",
    )
    assert gr["name"] == "Bob"
    assert gr["email"] == "bob@b.com"


def test_provenance_records_strategy(survivorship_db):
    svc = GoldenRecordPersistenceService(
        db=survivorship_db,
        source_collection="Person",
        cluster_collection="person_clusters",
        golden_collection="GoldenRecord",
        resolved_edge_collection="resolvedTo",
        include_fields=["name"],
        include_provenance=True,
        merge_strategy="most_complete",
    )
    svc.run(run_id="run-prov", min_cluster_size=3)
    gr = next(g for g in survivorship_db.collection("GoldenRecord").docs if g["clusterSize"] == 3)
    assert gr["fieldProvenance"]["name"]["strategy"] == "most_complete"
    assert gr["fieldProvenance"]["name"]["chosenFrom"] == "Person/s2"


def test_unknown_strategy_rejected(survivorship_db):
    with pytest.raises(ValueError, match="Unknown merge strategy"):
        GoldenRecordPersistenceService(
            db=survivorship_db,
            source_collection="Person",
            cluster_collection="person_clusters",
            merge_strategy="newest",
        )


def test_most_recent_requires_recency_field(survivorship_db):
    with pytest.raises(ValueError, match="recency_field"):
        GoldenRecordPersistenceService(
            db=survivorship_db,
            source_collection="Person",
            cluster_collection="person_clusters",
            merge_strategy="most_recent",
        )


def test_source_priority_requires_source_config(survivorship_db):
    with pytest.raises(ValueError, match="source_field"):
        GoldenRecordPersistenceService(
            db=survivorship_db,
            source_collection="Person",
            cluster_collection="person_clusters",
            field_strategies={"email": "source_priority"},
        )
