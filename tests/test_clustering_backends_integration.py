"""Integration tests for clustering backends' suppressed-edge handling.

The unit tests mock the AQL cursor, so they cannot validate that the real
queries — especially the aql_graph path-filtered traversal
(``p.edges[*].suppressed ALL != true``) — are accepted by ArangoDB and split
components correctly. These run the real backends against a live database.
"""

from __future__ import annotations

import uuid

import pytest

from entity_resolution.services.clustering_backends.aql_graph import AQLGraphBackend
from entity_resolution.services.clustering_backends.python_union_find import (
    PythonUnionFindBackend,
)


@pytest.fixture
def chain_graph(db_connection):
    """A-B-C chain with B-C suppressed; expect {A,B} as the only component."""
    suffix = uuid.uuid4().hex[:8]
    vcol = f"itb_person_{suffix}"
    ecol = f"itb_similar_{suffix}"
    db = db_connection
    db.create_collection(vcol)
    db.create_collection(ecol, edge=True)
    db.collection(vcol).insert_many([{"_key": k} for k in ("A", "B", "C")])
    db.collection(ecol).insert_many([
        {"_from": f"{vcol}/A", "_to": f"{vcol}/B", "similarity": 0.9},
        # Suppressed: must NOT connect B and C.
        {"_from": f"{vcol}/B", "_to": f"{vcol}/C", "similarity": 0.6, "suppressed": True},
    ])
    yield db, vcol, ecol
    for n in (vcol, ecol):
        if db.has_collection(n):
            db.delete_collection(n)


def _clusters(backend):
    return sorted(tuple(sorted(c)) for c in backend.cluster())


def test_aql_graph_backend_excludes_suppressed_edges(chain_graph):
    db, vcol, ecol = chain_graph
    backend = AQLGraphBackend(db, edge_collection_name=ecol, vertex_collection=vcol)
    # The path-filtered traversal must be valid AQL and split the chain:
    # only {A,B} remains a cluster; C is isolated.
    assert _clusters(backend) == [("A", "B")]


def test_union_find_backend_excludes_suppressed_edges(chain_graph):
    db, vcol, ecol = chain_graph
    backend = PythonUnionFindBackend(db, edge_collection_name=ecol, vertex_collection=vcol)
    assert _clusters(backend) == [("A", "B")]


def test_backends_agree_without_suppression(db_connection):
    """A-B-C with no suppression: both backends return the full {A,B,C}."""
    suffix = uuid.uuid4().hex[:8]
    vcol, ecol = f"itb2_person_{suffix}", f"itb2_similar_{suffix}"
    db = db_connection
    db.create_collection(vcol)
    db.create_collection(ecol, edge=True)
    try:
        db.collection(vcol).insert_many([{"_key": k} for k in ("A", "B", "C")])
        db.collection(ecol).insert_many([
            {"_from": f"{vcol}/A", "_to": f"{vcol}/B", "similarity": 0.9},
            {"_from": f"{vcol}/B", "_to": f"{vcol}/C", "similarity": 0.85},
        ])
        aql_b = AQLGraphBackend(db, edge_collection_name=ecol, vertex_collection=vcol)
        uf_b = PythonUnionFindBackend(db, edge_collection_name=ecol, vertex_collection=vcol)
        assert _clusters(aql_b) == [("A", "B", "C")]
        assert _clusters(uf_b) == [("A", "B", "C")]
    finally:
        for n in (vcol, ecol):
            if db.has_collection(n):
                db.delete_collection(n)
