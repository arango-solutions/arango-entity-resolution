"""Schema versioning and migrations for ER-owned ArangoDB collections.

The migration framework (plan 1.0) lands before Phase 1 introduces its first
system collections (``er_model_params``, ``er_term_frequencies``) and Phase 2
adds ``er_audit_log``, so collection-schema changes are versioned and applied
idempotently rather than created ad hoc.

Public API:
- :class:`Migration` — one numbered, idempotent schema change.
- :class:`MigrationRunner` — applies pending migrations, tracks the applied
  version in the ``er_meta`` collection, and refuses to run against a database
  whose schema is newer than the code.
- :data:`MIGRATIONS` — the ordered registry of known migrations.
- :exc:`SchemaVersionError` — raised when the DB schema is ahead of the code.
"""

from .runner import Migration, MigrationRunner, SchemaVersionError
from .registry import MIGRATIONS

__all__ = ["Migration", "MigrationRunner", "SchemaVersionError", "MIGRATIONS"]
