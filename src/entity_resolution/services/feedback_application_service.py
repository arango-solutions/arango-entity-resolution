"""
Feedback application service — closes the human/LLM review loop.

Verdicts collected by the review UI / LLM verifier are persisted in a
``FeedbackStore`` but, on their own, never change the resolved data. This
service applies a verdict to the similarity graph and re-clusters only the
affected connected component:

- ``no_match`` -> mark the similarity edge ``suppressed`` (never hard-deleted,
  so there is an audit trail and re-runs cannot resurrect it).
- ``match``    -> mark/insert a ``confirmed`` edge (keeping its computed score;
  no fabricated ``1.0`` that would distort score-distribution consumers).

Edge writes use AQL ``UPSERT`` with merge semantics so verdict flags and
computed scores coexist and survive pipeline re-runs (the bulk edge writer
uses ``overwrite_mode='ignore'`` and would otherwise never update an existing
edge).

After applying a verdict, ``recluster_component`` recomputes connected
components for just the affected subgraph (excluding suppressed edges,
including confirmed edges) via in-process union-find, and rewrites only the
cluster documents that contained the affected vertices.

Concurrency: ``apply_and_recluster`` serializes per-component work with a
short-lived lock document (TTL-indexed ``_er_locks``) so two verdicts on the
same component — or a verdict landing mid-pipeline — cannot interleave their
re-cluster writes.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..utils.graph_utils import extract_key_from_vertex_id, format_vertex_id

logger = logging.getLogger(__name__)

_LOCK_COLLECTION = "_er_locks"
_LOCK_TTL_SECONDS = 60


class FeedbackApplicationError(RuntimeError):
    """Raised when a verdict cannot be applied (e.g. lock contention)."""


class FeedbackApplicationService:
    """Apply human/LLM verdicts to the similarity graph and re-cluster.

    Parameters
    ----------
    db:
        ArangoDB database connection.
    edge_collection:
        Similarity edge collection (same one the pipeline writes).
    vertex_collection:
        Collection the resolved entities live in (for ``key`` -> ``_id``).
    cluster_collection:
        Cluster output collection (docs with ``member_keys``).
    """

    def __init__(
        self,
        db: Any,
        edge_collection: str,
        vertex_collection: str,
        cluster_collection: str,
        golden_collection: Optional[str] = None,
    ) -> None:
        self.db = db
        self.edge_collection = edge_collection
        self.vertex_collection = vertex_collection
        self.cluster_collection = cluster_collection
        # When set, golden records whose source cluster changed are flagged
        # stale (or regenerated when auto_refresh is on).
        self.golden_collection = golden_collection

    # ------------------------------------------------------------------
    # Edge keying (must match SimilarityEdgeService deterministic keys)
    # ------------------------------------------------------------------

    def _vid(self, key: str) -> str:
        return format_vertex_id(key, self.vertex_collection)

    @staticmethod
    def _edge_key(from_id: str, to_id: str) -> str:
        """Order-independent MD5 key — matches SimilarityEdgeService."""
        a, b = (from_id, to_id) if from_id < to_id else (to_id, from_id)
        return hashlib.md5(f"{a}->{b}".encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Verdict application
    # ------------------------------------------------------------------

    def apply_verdict(
        self,
        key_a: str,
        key_b: str,
        decision: str,
        *,
        actor: str = "human",
        score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Apply a single verdict to the edge between two entities.

        Returns a summary ``{action, edge_key, decision}``. Does NOT re-cluster
        — use :meth:`apply_and_recluster` for the full loop.
        """
        if decision not in ("match", "no_match"):
            raise ValueError("decision must be 'match' or 'no_match'")

        from_id = self._vid(key_a)
        to_id = self._vid(key_b)
        edge_key = self._edge_key(from_id, to_id)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        if decision == "no_match":
            patch = {"suppressed": True, "suppressed_by": actor, "suppressed_at": now,
                     "confirmed": False}
        else:
            # Keep the computed score; the verdict lives in the flag, not a
            # fabricated 1.0 (which would poison histograms / EM samples).
            patch = {"confirmed": True, "confirmed_by": actor, "confirmed_at": now,
                     "suppressed": False}

        # Canonical (sorted) endpoints so the insert matches the deterministic key.
        c_from, c_to = (from_id, to_id) if from_id < to_id else (to_id, from_id)
        insert_doc = {"_key": edge_key, "_from": c_from, "_to": c_to, **patch}
        if score is not None:
            insert_doc["similarity"] = round(score, 4)

        # UPSERT: update merges the patch onto the existing edge (preserving its
        # computed similarity and other attributes); insert creates a confirmed
        # edge for a below-threshold "match" that has no edge yet.
        self.db.aql.execute(
            """
            UPSERT { _key: @key }
            INSERT @insert
            UPDATE @patch
            IN @@edges
            """,
            bind_vars={
                "key": edge_key,
                "insert": insert_doc,
                "patch": patch,
                "@edges": self.edge_collection,
            },
        )

        return {"action": decision, "edge_key": edge_key, "decision": decision}

    # ------------------------------------------------------------------
    # Scoped re-clustering
    # ------------------------------------------------------------------

    def _fetch_component_edges(self, start_vid: str) -> List[Tuple[str, str]]:
        """Edges of the connected component containing ``start_vid``.

        Excludes suppressed edges; includes confirmed edges regardless of
        score. Uses a path-filtered ANY traversal so suppressed edges do not
        bridge components.
        """
        cursor = self.db.aql.execute(
            """
            FOR v, e, p IN 0..999999 ANY @start @@edges
                OPTIONS { uniqueEdges: "global", bfs: true }
                FILTER e != null
                FILTER p.edges[*].suppressed ALL != true
                RETURN DISTINCT { from: e._from, to: e._to }
            """,
            bind_vars={"start": start_vid, "@edges": self.edge_collection},
        )
        return [(row["from"], row["to"]) for row in cursor]

    @staticmethod
    def _connected_components(
        edges: List[Tuple[str, str]], seed: str
    ) -> List[List[str]]:
        """Union-find over an edge list; returns components as key lists."""
        parent: Dict[str, str] = {}

        def find(x: str) -> str:
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for a, b in edges:
            union(a, b)

        # The seed vertex may have become isolated (all its edges suppressed).
        find(seed)

        groups: Dict[str, List[str]] = defaultdict(list)
        for vid in parent:
            key = extract_key_from_vertex_id(vid)
            if key:
                groups[find(vid)].append(key)
        return [sorted(members) for members in groups.values()]

    @staticmethod
    def _cluster_key(member_keys: List[str]) -> str:
        """Stable, content-addressed cluster key (order-independent)."""
        joined = "|".join(sorted(member_keys))
        return "c_" + hashlib.md5(joined.encode("utf-8")).hexdigest()[:24]

    def recluster_component(self, member_key: str, *, auto_refresh: bool = False) -> Dict[str, Any]:
        """Recompute clusters for the component containing ``member_key``.

        Rewrites only the cluster documents that referenced any vertex in the
        affected component; all other clusters are left untouched. When a
        ``golden_collection`` is configured, golden records whose source cluster
        no longer exists are flagged stale (and deleted when ``auto_refresh``).
        """
        start_vid = self._vid(member_key)
        edges = self._fetch_component_edges(start_vid)
        components = self._connected_components(edges, start_vid)

        # Every entity key now touched by the recompute.
        touched_keys = {k for comp in components for k in comp}
        touched_keys.add(member_key)

        # Find existing cluster docs that referenced any touched key; we replace
        # exactly those, keyed by content hash so re-runs are idempotent.
        old_docs = list(self.db.aql.execute(
            """
            FOR c IN @@clusters
                FILTER LENGTH(INTERSECTION(c.member_keys, @touched)) > 0
                RETURN c
            """,
            bind_vars={"@clusters": self.cluster_collection, "touched": list(touched_keys)},
        ))
        old_keys = {d["_key"] for d in old_docs}

        # Singletons (entities whose every edge was suppressed) are not stored
        # as clusters — they drop out, matching the pipeline's min_cluster_size.
        new_docs = []
        for comp in components:
            if len(comp) < 2:
                continue
            ck = self._cluster_key(comp)
            new_docs.append({
                "_key": ck,
                "cluster_id": ck,
                "size": len(comp),
                "members": [self._vid(k) for k in comp],
                "member_keys": comp,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "method": "feedback_recluster",
            })
        new_keys = {d["_key"] for d in new_docs}

        coll = self.db.collection(self.cluster_collection)
        # Delete old cluster docs that are not being re-created with identical content.
        for key in old_keys - new_keys:
            try:
                coll.delete(key)
            except Exception:  # already gone
                pass
        if new_docs:
            coll.insert_many(new_docs, overwrite_mode="replace")

        result = {
            "component_size": len(touched_keys),
            "clusters_before": len(old_docs),
            "clusters_after": len(new_docs),
            "cluster_keys": sorted(new_keys),
        }

        if self.golden_collection and self.db.has_collection(self.golden_collection):
            surviving = {frozenset(d["member_keys"]) for d in new_docs}
            result["golden"] = self._handle_golden_staleness(
                touched_keys, surviving, auto_refresh=auto_refresh
            )

        return result

    def _handle_golden_staleness(
        self, touched_keys, surviving_member_sets, *, auto_refresh: bool
    ) -> Dict[str, Any]:
        """Flag (or delete) golden records whose source cluster changed.

        A golden record is still valid only if its exact member set matches a
        surviving cluster; otherwise it was built from a cluster that no longer
        exists and is flagged ``stale`` (deleted when ``auto_refresh``). Full
        regeneration of the new clusters happens on the next persistence run.
        """
        coll = self.db.collection(self.golden_collection)
        affected = list(self.db.aql.execute(
            """
            FOR g IN @@golden
                FILTER LENGTH(INTERSECTION(g.memberKeys, @touched)) > 0
                RETURN g
            """,
            bind_vars={"@golden": self.golden_collection, "touched": list(touched_keys)},
        ))

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        stale, deleted = 0, 0
        for g in affected:
            if frozenset(g.get("memberKeys", [])) in surviving_member_sets:
                continue  # still matches a live cluster
            if auto_refresh:
                try:
                    coll.delete(g["_key"])
                    deleted += 1
                except Exception:
                    pass
            else:
                coll.update({
                    "_key": g["_key"],
                    "stale": True,
                    "staleReason": "source cluster changed by feedback verdict",
                    "staleAt": now,
                })
                stale += 1

        return {"flagged_stale": stale, "deleted": deleted}

    # ------------------------------------------------------------------
    # Locking + full loop
    # ------------------------------------------------------------------

    def _ensure_lock_collection(self) -> None:
        if not self.db.has_collection(_LOCK_COLLECTION):
            self.db.create_collection(_LOCK_COLLECTION)
        try:
            # TTL index so a crashed holder's lock self-expires.
            self.db.collection(_LOCK_COLLECTION).add_index(
                {"type": "ttl", "fields": ["created_at"], "expiryTime": _LOCK_TTL_SECONDS}
            )
        except Exception:
            # Index already exists (or backend without TTL support in tests).
            pass

    def _component_lock_key(self, member_key: str) -> str:
        return "lock_" + hashlib.md5(member_key.encode("utf-8")).hexdigest()[:24]

    def _acquire_lock(self, member_key: str) -> Optional[str]:
        self._ensure_lock_collection()
        lock_key = self._component_lock_key(member_key)
        try:
            self.db.collection(_LOCK_COLLECTION).insert(
                {"_key": lock_key, "created_at": int(time.time())}
            )
            return lock_key
        except Exception:
            return None  # already locked

    def _release_lock(self, lock_key: str) -> None:
        try:
            self.db.collection(_LOCK_COLLECTION).delete(lock_key)
        except Exception:
            pass

    def apply_and_recluster(
        self,
        key_a: str,
        key_b: str,
        decision: str,
        *,
        actor: str = "human",
        score: Optional[float] = None,
        auto_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Apply a verdict and re-cluster the affected component, under a lock.

        Both ``key_a`` and ``key_b`` belong to the same component (they share an
        edge), so a single lock keyed on one endpoint serializes the work.
        """
        lock_key = self._acquire_lock(key_a)
        if lock_key is None:
            raise FeedbackApplicationError(
                f"component for '{key_a}' is locked by a concurrent verdict; retry"
            )
        try:
            verdict = self.apply_verdict(key_a, key_b, decision, actor=actor, score=score)
            recluster = self.recluster_component(key_a, auto_refresh=auto_refresh)
            return {"verdict": verdict, "recluster": recluster}
        finally:
            self._release_lock(lock_key)
