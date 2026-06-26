"""
Curation audit service (plan 2.0).

Records steward curation actions (cluster edits, golden-record applies, review
verdicts) to the ``er_audit_log`` collection and exposes per-entity history.

The audit log captures *attribution*, not access control: ``actor`` is the
resolved reviewer name and is not an authenticated identity (see the Phase 2/3
plan, Decision #1).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from ..utils.validation import validate_collection_name

_AUDIT_COLLECTION = "er_audit_log"


class CurationService:
    """Append-only audit trail for curation actions."""

    def __init__(self, db: Any, audit_collection: str = _AUDIT_COLLECTION) -> None:
        self.db = db
        self.audit_collection = audit_collection
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        # Normally created by migration #5; create defensively for direct use.
        if not self.db.has_collection(self.audit_collection):
            self.db.create_collection(self.audit_collection)

    def record(
        self,
        actor: str,
        action: str,
        collection: str,
        *,
        entity_key: Optional[str] = None,
        before: Any = None,
        after: Any = None,
    ) -> str:
        """Append an audit entry. Returns the new document ``_key``.

        Args:
            actor: Resolved reviewer name (attribution only).
            action: Short verb, e.g. ``"verdict"``, ``"remove_member"``, ``"merge"``.
            collection: The entity collection the action applies to.
            entity_key: Cluster/entity/pair key the action targets (enables history).
            before / after: Optional JSON-serializable snapshots of the change.
        """
        doc: Dict[str, Any] = {
            "actor": actor,
            "action": action,
            "collection": collection,
            "entity_key": entity_key,
            "before": before,
            "after": after,
            "ts": time.time(),
        }
        meta = self.db.collection(self.audit_collection).insert(doc)
        return meta["_key"]

    def history(
        self,
        collection: str,
        entity_key: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return audit entries for an entity/cluster key, newest first."""
        validate_collection_name(collection)
        if not self.db.has_collection(self.audit_collection):
            return []
        cursor = self.db.aql.execute(
            """
            FOR a IN @@coll
                FILTER a.collection == @collection AND a.entity_key == @entity_key
                SORT a.ts DESC
                LIMIT @limit
                RETURN a
            """,
            bind_vars={
                "@coll": self.audit_collection,
                "collection": collection,
                "entity_key": entity_key,
                "limit": int(limit),
            },
        )
        return list(cursor)
