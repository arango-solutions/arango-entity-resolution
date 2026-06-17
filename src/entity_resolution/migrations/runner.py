"""Idempotent schema migration runner backed by an ``er_meta`` collection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)

# Singleton key of the schema-state document in the meta collection.
_META_KEY = "schema"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Migration:
    """A single, numbered, idempotent schema change.

    ``apply`` receives the ArangoDB database handle and must be safe to run more
    than once (check-then-create), since a crash mid-run can re-invoke it.
    """

    id: int
    name: str
    description: str
    apply: Callable[[Any], None]


class SchemaVersionError(RuntimeError):
    """Raised when the database schema version is newer than the code knows."""


class MigrationRunner:
    """Apply pending schema migrations and track the applied version.

    The applied state lives in a singleton document of the ``er_meta``
    collection: ``{_key: "schema", version: int, applied: [{id, name, at}, ...]}``.
    """

    def __init__(
        self,
        db: Any,
        migrations: Optional[List[Migration]] = None,
        meta_collection: str = "er_meta",
    ) -> None:
        self.db = db
        self.meta_collection = meta_collection
        if migrations is None:
            from .registry import MIGRATIONS
            migrations = MIGRATIONS
        self.migrations = sorted(migrations, key=lambda m: m.id)
        self._validate_registry()

    def _validate_registry(self) -> None:
        ids = [m.id for m in self.migrations]
        if any(i <= 0 for i in ids):
            raise ValueError("migration ids must be positive integers")
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate migration ids in registry: {ids}")

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def _ensure_meta(self) -> None:
        if not self.db.has_collection(self.meta_collection):
            self.db.create_collection(self.meta_collection)

    def _meta_doc(self) -> Optional[dict]:
        self._ensure_meta()
        return self.db.collection(self.meta_collection).get(_META_KEY)

    def current_version(self) -> int:
        """Highest migration id applied to this database (0 if none)."""
        doc = self._meta_doc()
        return int(doc["version"]) if doc and "version" in doc else 0

    def code_version(self) -> int:
        """Highest migration id known to the code (0 if registry empty)."""
        return max((m.id for m in self.migrations), default=0)

    def pending(self) -> List[Migration]:
        cur = self.current_version()
        return [m for m in self.migrations if m.id > cur]

    def status(self) -> dict:
        cur = self.current_version()
        return {
            "current_version": cur,
            "code_version": self.code_version(),
            "pending": [{"id": m.id, "name": m.name} for m in self.pending()],
            "up_to_date": cur >= self.code_version(),
        }

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def migrate(self, target: Optional[int] = None) -> dict:
        """Apply pending migrations up to ``target`` (default: latest code version).

        Each migration is applied in id order and the meta document is persisted
        after each one, so an interrupted run resumes cleanly. Raises
        :exc:`SchemaVersionError` if the database is newer than the code.
        """
        cur = self.current_version()
        code = self.code_version()
        if cur > code:
            raise SchemaVersionError(
                f"database schema v{cur} is newer than code (max v{code}); "
                "upgrade the entity_resolution package before running migrations"
            )

        target = code if target is None else target
        coll = self.db.collection(self.meta_collection)
        meta = self._meta_doc() or {"_key": _META_KEY, "version": 0, "applied": []}
        applied: List[int] = []

        for m in self.migrations:
            if not (cur < m.id <= target):
                continue
            logger.info("Applying migration %03d (%s): %s", m.id, m.name, m.description)
            m.apply(self.db)
            meta["version"] = m.id
            meta["applied"] = list(meta.get("applied", [])) + [
                {"id": m.id, "name": m.name, "at": _now()}
            ]
            coll.insert(meta, overwrite=True)  # persist progress after each step
            applied.append(m.id)

        return {
            "from_version": cur,
            "to_version": self.current_version(),
            "applied": applied,
        }
