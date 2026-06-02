"""
Security regression tests for AQL injection prevention (PR1).

These tests assert that user/config-controlled identifiers and expressions are
either validated (rejected) or passed as bind variables before reaching AQL,
covering the entry points hardened in the comprehensive-review remediation
plan (Workstream 1A).
"""

import logging

import pytest

from entity_resolution.utils.validation import (
    validate_computed_field_expression,
)
from entity_resolution.core.incremental_resolver import IncrementalResolver
from entity_resolution.config.er_config import BlockingConfig
from entity_resolution.services.similarity_edge_service import SimilarityEdgeService
from entity_resolution.services.cross_collection_matching_service import (
    CrossCollectionMatchingService,
)


class _RecordingAQL:
    """Captures the last AQL query + bind_vars and returns an empty result."""

    def __init__(self):
        self.last_query = None
        self.last_bind_vars = None

    def execute(self, query, bind_vars=None, **kwargs):
        self.last_query = query
        self.last_bind_vars = bind_vars or {}
        return iter([])


class _FakeDB:
    def __init__(self):
        self.aql = _RecordingAQL()


# ---------------------------------------------------------------------------
# validate_computed_field_expression
# ---------------------------------------------------------------------------

SAFE_EXPRESSIONS = [
    "CONCAT(d.first_name, d.last_name)",
    "LOWER(d.name)",
    "SUBSTRING(d.code, 0, 3)",
    "d.first_name",
]


@pytest.mark.parametrize("expr", SAFE_EXPRESSIONS)
def test_safe_computed_expressions_pass(expr):
    assert validate_computed_field_expression(expr) == expr.strip()


MALICIOUS_EXPRESSIONS = [
    "d.x) REMOVE d IN companies //",
    "d.x) INSERT {evil: 1} INTO companies RETURN (",
    "(FOR v IN secrets RETURN v)",
    "d.x UPDATE d WITH {a: 1} IN companies",
    "d.name /* comment */",
    "d.name ; DROP",
]


@pytest.mark.parametrize("expr", MALICIOUS_EXPRESSIONS)
def test_malicious_computed_expressions_rejected(expr):
    with pytest.raises(ValueError):
        validate_computed_field_expression(expr)


def test_empty_computed_expression_rejected():
    with pytest.raises(ValueError):
        validate_computed_field_expression("   ")


# ---------------------------------------------------------------------------
# IncrementalResolver identifier validation
# ---------------------------------------------------------------------------

def test_incremental_resolver_rejects_malicious_collection():
    with pytest.raises(ValueError):
        IncrementalResolver(db=_FakeDB(), collection="x RETURN doc; //", fields=["name"])


def test_incremental_resolver_rejects_malicious_field():
    with pytest.raises(ValueError):
        IncrementalResolver(db=_FakeDB(), collection="companies", fields=["name) REMOVE doc IN companies //"])


def test_incremental_resolver_accepts_valid_identifiers():
    resolver = IncrementalResolver(db=_FakeDB(), collection="companies", fields=["name", "address.city"])
    assert resolver.collection == "companies"
    assert resolver.fields == ["name", "address.city"]


# ---------------------------------------------------------------------------
# BlockingConfig computed-field validation wiring
# ---------------------------------------------------------------------------

def test_blocking_config_rejects_malicious_expression_by_default():
    cfg = BlockingConfig(
        strategy="collect",
        fields=[{"name": "evil", "expression": "d.x) REMOVE d IN companies //"}],
    )
    with pytest.raises(ValueError):
        cfg.parse_fields()


def test_blocking_config_allows_safe_expression():
    cfg = BlockingConfig(
        strategy="collect",
        fields=[{"name": "full", "expression": "CONCAT(d.first_name, d.last_name)"}],
    )
    names, computed = cfg.parse_fields()
    assert names == ["full"]
    assert computed["full"] == "CONCAT(d.first_name, d.last_name)"


def test_blocking_config_opt_in_bypasses_validation():
    cfg = BlockingConfig(
        strategy="collect",
        fields=[{"name": "raw", "expression": "(FOR v IN x RETURN v)"}],
        allow_unsafe_expressions=True,
    )
    names, computed = cfg.parse_fields()
    assert computed["raw"] == "(FOR v IN x RETURN v)"


# ---------------------------------------------------------------------------
# Edge-clear paths use bind variables (no value interpolation)
# ---------------------------------------------------------------------------

def test_similarity_edge_clear_uses_bind_vars():
    svc = SimilarityEdgeService.__new__(SimilarityEdgeService)
    svc.db = _FakeDB()
    svc.edge_collection_name = "similarTo"

    svc.clear_edges(method="phone_blocking", older_than="2025-01-01T00:00:00")

    query = svc.db.aql.last_query
    bind_vars = svc.db.aql.last_bind_vars
    assert "@method" in query and "@older_than" in query
    assert "phone_blocking" not in query
    assert "2025-01-01T00:00:00" not in query
    assert bind_vars.get("method") == "phone_blocking"
    assert bind_vars.get("older_than") == "2025-01-01T00:00:00"


def test_cross_collection_clear_inferred_uses_bind_vars():
    svc = CrossCollectionMatchingService.__new__(CrossCollectionMatchingService)
    svc.db = _FakeDB()
    svc.edge_collection_name = "inferredEdges"
    svc.logger = logging.getLogger("test")

    svc.clear_inferred_edges(older_than="2025-01-01T00:00:00")

    query = svc.db.aql.last_query
    bind_vars = svc.db.aql.last_bind_vars
    assert "@older_than" in query
    assert "2025-01-01T00:00:00" not in query
    assert bind_vars.get("older_than") == "2025-01-01T00:00:00"
