"""Ordered registry of schema migrations.

Add new migrations here with the next integer id and an idempotent ``apply``.
Migrations operate on collections the ER system owns (versioned schema), not on
user data — one-off data repairs that need deployment-specific collection names
(e.g. the GraphRAG self-loop edge fix in
``scripts/migrations/001_fix_graphrag_self_loop_edges.py``) stay as standalone,
parameterized scripts rather than auto-run migrations.
"""

from __future__ import annotations

from typing import Any, List

from .runner import Migration


def _baseline(db: Any) -> None:
    """v3.6 baseline — no schema objects yet; establishes the version anchor.

    Phase 0 added only schemaless document fields (verdict flags on edges,
    staleness fields on golden records) and the runtime-created ``er_locks``
    collection, so there is nothing to create here. Later migrations
    (er_model_params, er_term_frequencies, er_audit_log) build on this anchor.
    """
    return None


MIGRATIONS: List[Migration] = [
    Migration(
        id=1,
        name="baseline_v3_6",
        description="Establish schema-version baseline (no schema objects to create).",
        apply=_baseline,
    ),
]
