"""Cluster repair: flag low-coherence clusters and split bridge-joined ones (plan 1.3).

Consumes the unsupervised cluster-quality signals from
:mod:`entity_resolution.services.evaluation_service` to find clusters that WCC
transitive closure over-merged (the classic precision killer): a single weak
"bridge" edge stitching two otherwise-dense subclusters.

For each flagged cluster the pure analysis (:func:`analyze_cluster`) decides:

- ``ok``     — coherent, leave it.
- ``split``  — removing the weakest non-confirmed edge disconnects the cluster
  into two halves, each denser than the original → safe to auto-split.
- ``queue``  — flagged but no safe single-edge split → hand off for human review.

Auto-splits are applied through :class:`FeedbackApplicationService` (the 0.1
machinery): the bridge edge is suppressed (``actor='cluster_repair'``) and the
component re-clustered, so confirmed/suppressed edges are honored and the audit
trail is consistent. Confirmed edges are never chosen as split points.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .evaluation_service import canonical_pair_id

logger = logging.getLogger(__name__)

_REPAIR_QUEUE = "er_repair_queue"


def _components(members: Sequence[str], edges: Set[str]) -> List[List[str]]:
    """Connected components of ``members`` given canonical-id ``edges`` present."""
    parent: Dict[str, str] = {m: m for m in members}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    member_set = set(members)
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            if canonical_pair_id(members[i], members[j]) in edges:
                union(members[i], members[j])

    groups: Dict[str, List[str]] = defaultdict(list)
    for m in members:
        groups[find(m)].append(m)
    return [sorted(g) for g in groups.values()]


def _density(members: Sequence[str], intra_scores: Dict[str, float]) -> float:
    n = len(members)
    if n < 2:
        return 1.0  # a singleton/empty half is trivially coherent
    possible = n * (n - 1) // 2
    present = 0
    for i in range(n):
        for j in range(i + 1, n):
            if canonical_pair_id(members[i], members[j]) in intra_scores:
                present += 1
    return present / possible if possible else 1.0


def analyze_cluster(
    members: Sequence[str],
    intra_scores: Dict[str, float],
    confirmed_pairs: Set[str],
    *,
    min_coherence: float = 0.5,
) -> Dict[str, Any]:
    """Decide whether a cluster is ok, should split, or should be queued.

    ``intra_scores`` maps ``canonical_pair_id`` of within-cluster member pairs to
    the (non-suppressed) edge score. ``confirmed_pairs`` are human/LLM-confirmed
    edges that must never be chosen as a split point.
    """
    members = sorted(members)
    scores = list(intra_scores.values())
    if not scores:
        return {"status": "queue", "reason": "no_intra_edges", "members": members}

    mean_score = sum(scores) / len(scores)
    min_score = min(scores)
    density = _density(members, intra_scores)
    is_bridge = min_score < 0.5 * mean_score and density < 1.0
    healthy = mean_score >= min_coherence and not is_bridge
    if healthy:
        return {"status": "ok", "members": members,
                "mean_edge_score": mean_score, "density": density}

    # Try splitting by removing a weak non-confirmed edge. Only edges weaker than
    # min_coherence are eligible — never cut a strong edge just to isolate a node.
    present_edges = set(intra_scores)
    candidates = sorted(
        (
            (pid, s) for pid, s in intra_scores.items()
            if pid not in confirmed_pairs and s < min_coherence
        ),
        key=lambda kv: kv[1],
    )
    for pid, score in candidates:
        remaining = present_edges - {pid}
        comps = _components(members, remaining)
        if len(comps) == 2:
            d0, d1 = _density(comps[0], intra_scores), _density(comps[1], intra_scores)
            if d0 > density and d1 > density:
                return {
                    "status": "split",
                    "members": members,
                    "split_edge": pid,
                    "split_score": score,
                    "halves": comps,
                    "original_density": density,
                    "half_densities": [d0, d1],
                    "mean_edge_score": mean_score,
                }
    return {
        "status": "queue",
        "members": members,
        "reason": "low_coherence" if mean_score < min_coherence else "bridge_no_clean_split",
        "mean_edge_score": mean_score,
        "min_edge_score": min_score,
        "density": density,
    }


class ClusterRepairService:
    """Analyze stored clusters and (optionally) auto-split bridge-joined ones."""

    def __init__(
        self,
        db: Any,
        edge_collection: str,
        vertex_collection: str,
        cluster_collection: str,
        *,
        min_coherence: float = 0.5,
        repair_queue_collection: str = _REPAIR_QUEUE,
    ) -> None:
        self.db = db
        self.edge_collection = edge_collection
        self.vertex_collection = vertex_collection
        self.cluster_collection = cluster_collection
        self.min_coherence = min_coherence
        self.repair_queue_collection = repair_queue_collection

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _active_edges(self) -> Tuple[Dict[str, float], Set[str]]:
        """Return (canonical_id -> score, set of confirmed canonical ids)."""
        cursor = self.db.aql.execute(
            """
            FOR e IN @@edges
                FILTER e.suppressed != true
                RETURN {from: e._from, to: e._to, score: e.similarity, confirmed: e.confirmed}
            """,
            bind_vars={"@edges": self.edge_collection},
        )
        scores: Dict[str, float] = {}
        confirmed: Set[str] = set()
        for row in cursor:
            pid = canonical_pair_id(row["from"], row["to"])
            scores[pid] = row.get("score") if row.get("score") is not None else 0.0
            if row.get("confirmed"):
                confirmed.add(pid)
        return scores, confirmed

    def _clusters(self) -> List[Dict[str, Any]]:
        out = []
        for doc in self.db.collection(self.cluster_collection):
            members = doc.get("members") or doc.get("member_keys") or []
            out.append({"_key": doc["_key"], "members": [str(m) for m in members]})
        return out

    # ------------------------------------------------------------------
    # Analysis + repair
    # ------------------------------------------------------------------

    def analyze(self) -> List[Dict[str, Any]]:
        """Return a repair proposal per non-ok cluster."""
        all_scores, confirmed = self._active_edges()
        proposals = []
        for cluster in self._clusters():
            members = cluster["members"]
            if len(members) < 2:
                continue
            intra = {
                pid: all_scores[pid]
                for i in range(len(members))
                for j in range(i + 1, len(members))
                if (pid := canonical_pair_id(members[i], members[j])) in all_scores
            }
            result = analyze_cluster(members, intra, confirmed, min_coherence=self.min_coherence)
            if result["status"] != "ok":
                result["cluster_key"] = cluster["_key"]
                proposals.append(result)
        return proposals

    def repair(self, *, auto_split: bool = False) -> Dict[str, Any]:
        """Analyze and act: auto-split where safe (if enabled), queue the rest."""
        from .feedback_application_service import FeedbackApplicationService
        from ..utils.graph_utils import extract_key_from_vertex_id

        proposals = self.analyze()
        applier = FeedbackApplicationService(
            db=self.db,
            edge_collection=self.edge_collection,
            vertex_collection=self.vertex_collection,
            cluster_collection=self.cluster_collection,
        )

        split, queued = [], []
        for p in proposals:
            if p["status"] == "split" and auto_split:
                # split_edge is a canonical "from|to" of vertex ids; recover keys.
                a_vid, b_vid = p["split_edge"].split("|", 1)
                key_a = extract_key_from_vertex_id(a_vid)
                key_b = extract_key_from_vertex_id(b_vid)
                applier.apply_and_recluster(key_a, key_b, "no_match", actor="cluster_repair")
                split.append({"cluster_key": p["cluster_key"], "split_edge": p["split_edge"],
                              "halves": p["halves"]})
            else:
                queued.append(p)

        if queued:
            self._persist_queue(queued)

        return {
            "analyzed": len(proposals),
            "split": split,
            "queued": [q["cluster_key"] for q in queued],
        }

    def _persist_queue(self, queued: List[Dict[str, Any]]) -> None:
        if not self.db.has_collection(self.repair_queue_collection):
            self.db.create_collection(self.repair_queue_collection)
        coll = self.db.collection(self.repair_queue_collection)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for q in queued:
            coll.insert(
                {
                    "_key": q["cluster_key"],
                    "cluster_key": q["cluster_key"],
                    "reason": q.get("reason", "flagged"),
                    "mean_edge_score": q.get("mean_edge_score"),
                    "members": q["members"],
                    "flagged_at": now,
                    "status": "pending",
                },
                overwrite=True,
            )
