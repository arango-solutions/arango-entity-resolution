"""
Golden record persistence service.

Persists GoldenRecord documents and resolvedTo edges from cluster outputs.

Design goals:
- Generic (no domain-specific schema assumptions)
- Deterministic / idempotent reruns (safe to run multiple times)
- Works on ArangoDB single server and cluster/managed (AMP)
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from arango.database import StandardDatabase

from ..utils.graph_utils import extract_key_from_vertex_id, format_vertex_id


SYSTEM_FIELDS = {"_key", "_id", "_rev", "_from", "_to"}

MERGE_STRATEGIES = ("field_voting", "most_complete", "most_recent", "source_priority")


class GoldenRecordPersistenceService:
    """
    Persist GoldenRecord vertices + resolvedTo edges from clusters.

    Inputs:
    - `source_collection`: the entity collection being resolved (e.g. Person)
    - `cluster_collection`: output of WCCClusteringService (docs with `members` / `member_keys`)

    Outputs:
    - `golden_collection`: golden record vertices (default "golden_records")
    - `resolved_edge_collection`: edges from source -> golden (default "resolvedTo")

    Survivorship: `merge_strategy` selects how conflicting field values are
    resolved, with optional per-field overrides via `field_strategies`:
    - "field_voting" (default): most frequent value, tie-break longest string
    - "most_complete": longest / most informative value
    - "most_recent": value from the member doc with the latest `recency_field`
    - "source_priority": value from the doc whose `source_field` value ranks
      earliest in `source_priority`
    """

    def __init__(
        self,
        db: StandardDatabase,
        source_collection: str,
        cluster_collection: str,
        golden_collection: str = "golden_records",
        resolved_edge_collection: str = "resolvedTo",
        include_fields: Optional[Sequence[str]] = None,
        include_provenance: bool = False,
        merge_strategy: str = "field_voting",
        field_strategies: Optional[Dict[str, str]] = None,
        recency_field: Optional[str] = None,
        source_field: Optional[str] = None,
        source_priority: Optional[Sequence[str]] = None,
    ):
        self.db = db
        self.source_collection_name = source_collection
        self.cluster_collection_name = cluster_collection
        self.golden_collection_name = golden_collection
        self.resolved_edge_collection_name = resolved_edge_collection
        self.include_fields = list(include_fields) if include_fields else None
        self.include_provenance = include_provenance

        self.merge_strategy = merge_strategy
        self.field_strategies = dict(field_strategies) if field_strategies else {}
        self.recency_field = recency_field
        self.source_field = source_field
        self.source_priority = list(source_priority) if source_priority else []

        used_strategies = {self.merge_strategy, *self.field_strategies.values()}
        unknown = used_strategies - set(MERGE_STRATEGIES)
        if unknown:
            raise ValueError(
                f"Unknown merge strategy {sorted(unknown)}; "
                f"valid strategies: {', '.join(MERGE_STRATEGIES)}"
            )
        if "most_recent" in used_strategies and not self.recency_field:
            raise ValueError("merge_strategy 'most_recent' requires recency_field")
        if "source_priority" in used_strategies and not (
            self.source_field and self.source_priority
        ):
            raise ValueError(
                "merge_strategy 'source_priority' requires source_field and source_priority"
            )

        if not self.db.has_collection(self.golden_collection_name):
            self.db.create_collection(self.golden_collection_name, edge=False)
        if not self.db.has_collection(self.resolved_edge_collection_name):
            self.db.create_collection(self.resolved_edge_collection_name, edge=True)

        self.source_collection = self.db.collection(self.source_collection_name)
        self.cluster_collection = self.db.collection(self.cluster_collection_name)
        self.golden_collection = self.db.collection(self.golden_collection_name)
        self.resolved_edge_collection = self.db.collection(self.resolved_edge_collection_name)

    def run(
        self,
        run_id: Optional[str] = None,
        min_cluster_size: int = 2,
        method: str = "golden_record_persistence",
    ) -> Dict[str, Any]:
        """
        Create/update GoldenRecords and resolvedTo edges.

        Returns summary counts only (safe for logs).
        """
        rid = run_id or datetime.now(timezone.utc).isoformat(timespec="seconds")

        clusters_processed = 0
        golden_upserted = 0
        edges_upserted = 0

        golden_docs: List[Dict[str, Any]] = []
        resolved_edges: List[Dict[str, Any]] = []

        for cluster in self.cluster_collection:
            member_ids = self._get_cluster_member_ids(cluster)
            if len(member_ids) < min_cluster_size:
                continue

            clusters_processed += 1
            member_docs = self._fetch_member_docs(member_ids)
            if not member_docs:
                continue

            golden_key = self._golden_key(member_ids)
            golden_id = f"{self.golden_collection_name}/{golden_key}"

            consolidated, provenance = self._consolidate(member_docs)

            member_keys = [extract_key_from_vertex_id(mid) for mid in member_ids]
            golden_doc: Dict[str, Any] = {
                "_key": golden_key,
                "clusterId": cluster.get("cluster_id", cluster.get("_key")),
                "clusterSize": len(member_ids),
                "memberIds": list(member_ids),
                "memberKeys": member_keys,
                # Content hash of the source cluster's members. When the cluster
                # later changes, this no longer matches any live cluster and the
                # record can be detected as stale (see FeedbackApplicationService).
                "sourceClusterHash": self.cluster_hash(member_keys),
                "stale": False,
                "runId": rid,
                "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "method": method,
                "mergeStrategy": self.merge_strategy,
                **consolidated,
            }
            if self.include_provenance:
                golden_doc["fieldProvenance"] = provenance

            golden_docs.append(golden_doc)

            for mid in member_ids:
                resolved_edges.append(
                    {
                        "_key": self._edge_key(mid, golden_id),
                        "_from": mid,
                        "_to": golden_id,
                        "runId": rid,
                        "method": method,
                        "inferred": True,
                        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    }
                )

        if golden_docs:
            # Update semantics => safe reruns (refresh metadata, no duplicates).
            self.golden_collection.insert_many(golden_docs, overwrite_mode="update")
            golden_upserted = len(golden_docs)

        if resolved_edges:
            # Deterministic keys + ignore => idempotent edge creation.
            self.resolved_edge_collection.insert_many(resolved_edges, overwrite_mode="ignore")
            edges_upserted = len(resolved_edges)

        return {
            "clusters_processed": clusters_processed,
            "golden_records_upserted": golden_upserted,
            "resolved_edges_upserted": edges_upserted,
        }

    def _get_cluster_member_ids(self, cluster: Dict[str, Any]) -> List[str]:
        """
        Extract member vertex IDs from a cluster doc.

        Supports:
        - `members`: list of vertex ids (preferred, produced by WCCClusteringService)
        - `member_keys`: list of keys (will be formatted into vertex ids)
        """
        members = cluster.get("members")
        if isinstance(members, list) and members:
            out: List[str] = []
            for m in members:
                s = str(m)
                out.append(s if "/" in s else format_vertex_id(s, self.source_collection_name))
            return out

        member_keys = cluster.get("member_keys")
        if isinstance(member_keys, list) and member_keys:
            return [format_vertex_id(str(k), self.source_collection_name) for k in member_keys]

        return []

    def _fetch_member_docs(self, member_ids: Sequence[str]) -> List[Dict[str, Any]]:
        docs: List[Dict[str, Any]] = []
        for vid in member_ids:
            key = extract_key_from_vertex_id(vid)
            try:
                d = self.source_collection.get(key)
            except Exception:
                d = None
            if d:
                d.setdefault("_id", format_vertex_id(key, self.source_collection_name))
                docs.append(d)
        return docs

    def _golden_key(self, member_ids: Sequence[str]) -> str:
        # Deterministic: hash of sorted member vertex ids.
        s = "|".join(sorted(member_ids))
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    @staticmethod
    def cluster_hash(member_keys: Sequence[str]) -> str:
        """Order-independent content hash of a cluster's member keys.

        Stamped on each golden record and recomputed by the feedback service
        to detect when a golden record's source cluster has changed.
        """
        return hashlib.md5("|".join(sorted(member_keys)).encode("utf-8")).hexdigest()

    def _edge_key(self, from_id: str, to_id: str) -> str:
        # Deterministic, order-independent.
        a, b = (from_id, to_id) if from_id < to_id else (to_id, from_id)
        return hashlib.md5(f"{a}->{b}".encode("utf-8")).hexdigest()

    def _consolidate(self, member_docs: Sequence[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Per-field consolidation using the configured survivorship strategy
        (with per-field overrides), with optional provenance.
        """
        all_fields = set()
        for d in member_docs:
            all_fields.update(d.keys())

        fields = [f for f in all_fields if f not in SYSTEM_FIELDS and not f.startswith("_")]
        if self.include_fields:
            allowed = set(self.include_fields)
            fields = [f for f in fields if f in allowed]

        consolidated: Dict[str, Any] = {}
        provenance: Dict[str, Any] = {}

        for field in fields:
            # (value, source_id, owning_doc) for every doc that has the field
            vals: List[Tuple[Any, str, Dict[str, Any]]] = []
            for d in member_docs:
                v = d.get(field)
                if v is None:
                    continue
                if isinstance(v, str) and not v.strip():
                    continue
                vals.append((v, d.get("_id") or d.get("_key") or "unknown", d))

            if not vals:
                continue

            strategy = self.field_strategies.get(field, self.merge_strategy)
            chosen, chosen_from = self._apply_strategy(strategy, vals)
            consolidated[field] = chosen

            if self.include_provenance:
                distinct = len(set(repr(v) for v, _, _ in vals))
                provenance[field] = {
                    "distinctValues": distinct,
                    "sources": len({src for _, src, _ in vals}),
                    "chosenFrom": chosen_from,
                    "strategy": strategy,
                }

        return consolidated, provenance

    def _apply_strategy(
        self, strategy: str, vals: List[Tuple[Any, str, Dict[str, Any]]]
    ) -> Tuple[Any, str]:
        """Resolve one field's conflicting values; returns (value, source_id)."""
        if strategy == "most_complete":
            v, src, _ = max(vals, key=lambda t: len(str(t[0])))
            return v, src

        if strategy == "most_recent":
            with_ts = [t for t in vals if t[2].get(self.recency_field) is not None]
            if with_ts:
                # ISO-8601 strings and numeric epochs both order correctly via str()
                v, src, _ = max(with_ts, key=lambda t: str(t[2][self.recency_field]))
                return v, src
            return self._field_voting(vals)

        if strategy == "source_priority":
            rank = {s: i for i, s in enumerate(self.source_priority)}
            ranked = [t for t in vals if t[2].get(self.source_field) in rank]
            if ranked:
                v, src, _ = min(ranked, key=lambda t: rank[t[2][self.source_field]])
                return v, src
            return self._field_voting(vals)

        return self._field_voting(vals)

    @staticmethod
    def _field_voting(vals: List[Tuple[Any, str, Dict[str, Any]]]) -> Tuple[Any, str]:
        """Most frequent value (by repr), tie-break by longest string."""
        counts: Dict[str, int] = {}
        for v, _, _ in vals:
            counts[repr(v)] = counts.get(repr(v), 0) + 1
        max_count = max(counts.values())
        top = [v for v, _, _ in vals if counts.get(repr(v), 0) == max_count]

        chosen = top[0]
        if isinstance(chosen, str) and len(top) > 1:
            chosen = max(top, key=lambda x: len(x))

        chosen_from = next((src for v, src, _ in vals if v == chosen), "unknown")
        return chosen, chosen_from

