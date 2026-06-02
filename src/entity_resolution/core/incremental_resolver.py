"""
IncrementalResolver — resolve a single new record against an existing collection.

This is the engine behind the `resolve_entity` MCP tool.  It runs blocking
and similarity for ONE incoming record without re-processing the full
collection, making it suitable for real-time / streaming use cases.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from entity_resolution.utils.validation import (
    validate_collection_name,
    validate_field_names,
)

logger = logging.getLogger(__name__)


class IncrementalResolver:
    """
    Find existing records in *collection* that match a single query record.

    Usage::

        resolver = IncrementalResolver(db, collection="companies", fields=["name", "city"])
        matches  = resolver.resolve({"name": "Acme Corp", "city": "Boston"}, top_k=5)

    Parameters
    ----------
    db:
        An authenticated python-arango ``Database`` handle.
    collection:
        Name of the document collection to search.
    fields:
        Fields to use for blocking key construction and similarity.
    confidence_threshold:
        Minimum weighted Jaro-Winkler score to include in results.
    blocking_strategy:
        ``"prefix"`` (default) — uses the first ``prefix_length`` chars of
        each field value as a blocking key;  ``"full"`` — no blocking,
        compares against all documents (only safe for small collections).
    prefix_length:
        Number of characters used for prefix blocking keys.
    """

    def __init__(
        self,
        db,
        collection: str,
        fields: List[str],
        confidence_threshold: float = 0.80,
        blocking_strategy: str = "prefix",
        prefix_length: int = 3,
    ) -> None:
        # Validate identifiers up front: ``collection`` and ``fields`` are
        # interpolated directly into AQL (the field names cannot be passed as
        # bind variables), so they must be confirmed to be safe identifiers to
        # prevent AQL injection.
        self.db = db
        self.collection = validate_collection_name(collection)
        self.fields = validate_field_names(fields or [])
        self.confidence_threshold = confidence_threshold
        self.blocking_strategy = blocking_strategy
        self.prefix_length = prefix_length

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        record: Dict[str, Any],
        top_k: int = 10,
        exclude_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return up to *top_k* existing records that match *record*.

        Each result contains:
        - ``_key``: document key of the candidate
        - ``score``: weighted similarity score (0–1)
        - ``field_scores``: per-field breakdown
        - ``match``: ``True`` if score ≥ confidence_threshold
        """
        candidates = self._fetch_candidates(record)
        logger.debug("IncrementalResolver: %d raw candidates for blocking", len(candidates))

        scored = []
        for candidate in candidates:
            if exclude_key and candidate.get("_key") == exclude_key:
                continue
            score, field_scores = self._score(record, candidate)
            if score >= self.confidence_threshold:
                scored.append({
                    "_key": candidate.get("_key"),
                    "_id": candidate.get("_id"),
                    "score": round(score, 4),
                    "field_scores": field_scores,
                    "match": True,
                })

        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:top_k]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_candidates(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch candidate documents from ArangoDB using blocking keys."""
        if self.blocking_strategy == "full":
            cursor = self.db.aql.execute(
                "FOR doc IN @@col RETURN doc",
                bind_vars={"@col": self.collection},
            )
            return list(cursor)

        # Prefix blocking: build OR conditions for each field prefix
        conditions = []
        bind_vars: Dict[str, Any] = {"@col": self.collection}
        for i, field in enumerate(self.fields):
            value = record.get(field)
            if not value or not isinstance(value, str):
                continue
            prefix = value[: self.prefix_length].lower()
            param = f"prefix_{i}"
            conditions.append(
                f"LOWER(LEFT(doc.{field}, {self.prefix_length})) == @{param}"
            )
            bind_vars[param] = prefix

        if not conditions:
            # No blocking keys — fall back to full scan (warn for large collections)
            logger.warning(
                "IncrementalResolver: no blocking keys derived for fields %s — "
                "falling back to full collection scan",
                self.fields,
            )
            cursor = self.db.aql.execute(
                "FOR doc IN @@col RETURN doc",
                bind_vars={"@col": self.collection},
            )
            return list(cursor)

        filter_clause = " OR ".join(f"({c})" for c in conditions)
        aql = f"FOR doc IN @@col FILTER {filter_clause} RETURN doc"
        cursor = self.db.aql.execute(aql, bind_vars=bind_vars)
        return list(cursor)

    def _score(
        self,
        record: Dict[str, Any],
        candidate: Dict[str, Any],
    ) -> tuple[float, Dict[str, Any]]:
        """Return (weighted_average_score, per-field breakdown)."""
        import jellyfish

        scores: List[float] = []
        field_scores: Dict[str, Any] = {}

        for field in self.fields:
            val_a = str(record.get(field, "") or "").strip()
            val_b = str(candidate.get(field, "") or "").strip()

            if not val_a and not val_b:
                continue

            if val_a.lower() == val_b.lower():
                s = 1.0
                method = "exact"
            else:
                s = jellyfish.jaro_winkler_similarity(val_a, val_b)
                method = "jaro_winkler"

            scores.append(s)
            field_scores[field] = {"score": round(s, 4), "method": method}

        overall = sum(scores) / len(scores) if scores else 0.0
        return overall, field_scores
