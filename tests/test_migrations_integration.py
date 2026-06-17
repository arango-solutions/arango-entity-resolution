"""Integration tests for the schema migration runner against real ArangoDB.

Validates that ``er_meta`` is created with a legal name, the baseline migration
applies, reruns are idempotent, and a real schema migration (creating a
collection) is applied exactly once.
"""

from __future__ import annotations

import uuid

import pytest

from entity_resolution.migrations import Migration, MigrationRunner


@pytest.fixture
def meta_name(db_connection):
    name = f"er_meta_{uuid.uuid4().hex[:8]}"
    yield name
    if db_connection.has_collection(name):
        db_connection.delete_collection(name)


def test_baseline_migration_creates_meta_and_records_version(db_connection, meta_name):
    runner = MigrationRunner(db_connection, meta_collection=meta_name)
    out = runner.migrate()

    assert db_connection.has_collection(meta_name)  # legal collection name
    assert out["to_version"] == runner.code_version()
    meta = db_connection.collection(meta_name).get("schema")
    assert meta["version"] == runner.code_version()


def test_rerun_is_idempotent(db_connection, meta_name):
    runner = MigrationRunner(db_connection, meta_collection=meta_name)
    runner.migrate()
    second = runner.migrate()
    assert second["applied"] == []
    meta = db_connection.collection(meta_name).get("schema")
    assert len(meta["applied"]) == runner.code_version()


def test_real_schema_migration_creates_collection_once(db_connection, meta_name):
    created = f"er_test_coll_{uuid.uuid4().hex[:8]}"

    def create_coll(db):
        if not db.has_collection(created):
            db.create_collection(created)

    migs = [
        Migration(1, "baseline", "", lambda db: None),
        Migration(2, "create_test_coll", "", create_coll),
    ]
    try:
        runner = MigrationRunner(db_connection, migrations=migs, meta_collection=meta_name)
        out = runner.migrate()
        assert out["applied"] == [1, 2]
        assert db_connection.has_collection(created)

        # Rerun: migration #2 must not run again (idempotent + version-gated).
        rerun = MigrationRunner(db_connection, migrations=migs, meta_collection=meta_name)
        assert rerun.migrate()["applied"] == []
    finally:
        if db_connection.has_collection(created):
            db_connection.delete_collection(created)
