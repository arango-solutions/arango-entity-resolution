"""Evaluation harness for scoring quality and cluster quality (plan 1.2).

Two complementary capabilities:

1. **Labeled threshold sweep** — given scored candidate pairs and a ground-truth
   set of matching pairs, compute precision/recall/F1 across the *full* range of
   thresholds (the curve, not a single point), plus the best-F1 operating point.
   This is exactly what the Phase 2 threshold tuner renders, and the number that
   proves whether EM-learned parameters (1.1) beat hand-tuned defaults.

2. **Unsupervised cluster quality** — when labels don't exist (the common case
   in production), per-cluster coherence metrics and bridge-edge detection over
   the similarity graph, so low-quality clusters can be surfaced for review.

The metric math (:func:`threshold_sweep`, :func:`confusion_at`) is pure and
dependency-free for unit testing; :class:`EvaluationService` wires it to
ArangoDB collections.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger(__name__)

ScoredPair = Tuple[str, str, float]


def canonical_pair_id(id_a: str, id_b: str) -> str:
    """Order-independent pair id so (a,b) and (b,a) collapse."""
    return f"{id_a}|{id_b}" if id_a <= id_b else f"{id_b}|{id_a}"


def _dedupe_max(scored_pairs: Iterable[ScoredPair]) -> Dict[str, float]:
    """Collapse duplicate pairs to their max score, keyed by canonical id."""
    best: Dict[str, float] = {}
    for a, b, score in scored_pairs:
        pid = canonical_pair_id(a, b)
        if pid not in best or score > best[pid]:
            best[pid] = float(score)
    return best


def _prf(tp: int, fp: int, n_true: int) -> Tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / n_true if n_true > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def confusion_at(
    scored_pairs: Iterable[ScoredPair],
    truth_pairs: Set[str],
    threshold: float,
) -> Dict[str, Any]:
    """Confusion counts + P/R/F1 at a single threshold (predict match if score >= t).

    Recall is measured against *all* truth pairs (including any the blocker never
    produced), so it is the honest end-to-end recall; ``candidate_recall`` is
    measured only against truth pairs present in the scored set.
    """
    scores = _dedupe_max(scored_pairs)
    n_true_total = len(truth_pairs)
    truth_in_candidates = sum(1 for pid in scores if pid in truth_pairs)

    tp = fp = 0
    for pid, score in scores.items():
        if score >= threshold:
            if pid in truth_pairs:
                tp += 1
            else:
                fp += 1
    fn = n_true_total - tp
    precision, recall, f1 = _prf(tp, fp, n_true_total)
    candidate_recall = (tp / truth_in_candidates) if truth_in_candidates > 0 else 0.0
    return {
        "threshold": threshold,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "candidate_recall": candidate_recall,
        "f1": f1,
        "n_true_total": n_true_total,
        "n_true_in_candidates": truth_in_candidates,
        "n_scored": len(scores),
    }


def threshold_sweep(
    scored_pairs: Iterable[ScoredPair],
    truth_pairs: Set[str],
    thresholds: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    """Precision/recall/F1 across thresholds, plus the best-F1 operating point.

    With ``thresholds=None`` the sweep uses every distinct score as a candidate
    threshold (the exact curve). Recall is against all truth pairs.
    """
    scores = _dedupe_max(scored_pairs)
    n_true_total = len(truth_pairs)
    truth_in_candidates = sum(1 for pid in scores if pid in truth_pairs)

    # (score, is_true) sorted by score descending.
    items = sorted(
        ((s, pid in truth_pairs) for pid, s in scores.items()),
        key=lambda x: x[0],
        reverse=True,
    )

    points: List[Dict[str, Any]] = []

    def _emit(threshold: float, tp: int, fp: int) -> None:
        precision, recall, f1 = _prf(tp, fp, n_true_total)
        points.append({
            "threshold": round(float(threshold), 6),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": n_true_total - tp,
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
        })

    if thresholds is not None:
        for t in thresholds:
            tp = fp = 0
            for s, is_true in items:
                if s >= t:
                    tp += is_true
                    fp += not is_true
                else:
                    break  # items sorted desc
            _emit(t, tp, fp)
    else:
        # Walk distinct scores high→low, accumulating predicted positives.
        tp = fp = 0
        i = 0
        n = len(items)
        while i < n:
            s = items[i][0]
            while i < n and items[i][0] == s:
                if items[i][1]:
                    tp += 1
                else:
                    fp += 1
                i += 1
            _emit(s, tp, fp)

    best = max(points, key=lambda p: p["f1"], default=None)
    return {
        "points": points,
        "best_f1": best,
        "n_true_total": n_true_total,
        "n_true_in_candidates": truth_in_candidates,
        "n_scored": len(scores),
    }


def cluster_quality_summary(
    clusters: Sequence[Sequence[str]],
    edge_scores: Dict[str, float],
    *,
    min_coherence: float = 0.5,
) -> Dict[str, Any]:
    """Unsupervised per-cluster coherence + corpus-level summary.

    ``edge_scores`` maps ``canonical_pair_id(member_i, member_j)`` to the edge
    similarity. For each cluster of size >= 2 it computes intra-cluster edge
    density, mean/min edge score, and flags a bridge edge (a single low-score
    edge whose removal would disconnect the cluster is approximated by a min
    score well below the mean). Clusters below ``min_coherence`` mean score are
    surfaced for review.
    """
    per_cluster: List[Dict[str, Any]] = []
    sizes: List[int] = []
    low_coherence = 0

    for members in clusters:
        members = list(members)
        size = len(members)
        sizes.append(size)
        if size < 2:
            continue
        present_scores: List[float] = []
        possible = size * (size - 1) // 2
        for i in range(size):
            for j in range(i + 1, size):
                pid = canonical_pair_id(members[i], members[j])
                if pid in edge_scores:
                    present_scores.append(edge_scores[pid])
        if not present_scores:
            continue
        mean_score = sum(present_scores) / len(present_scores)
        min_score = min(present_scores)
        density = len(present_scores) / possible if possible else 0.0
        is_low = mean_score < min_coherence
        if is_low:
            low_coherence += 1
        per_cluster.append({
            "members": members,
            "size": size,
            "edge_count": len(present_scores),
            "density": round(density, 4),
            "mean_edge_score": round(mean_score, 4),
            "min_edge_score": round(min_score, 4),
            # Heuristic bridge flag: a weak edge dragging an otherwise tight cluster.
            "possible_bridge": bool(min_score < 0.5 * mean_score and density < 1.0),
            "low_coherence": is_low,
        })

    sizes_ge2 = [s for s in sizes if s >= 2]
    return {
        "n_clusters": len(sizes_ge2),
        "n_singletons": sum(1 for s in sizes if s < 2),
        "low_coherence_clusters": low_coherence,
        "size_distribution": _size_histogram(sizes_ge2),
        "clusters": per_cluster,
    }


def _size_histogram(sizes: Sequence[int]) -> Dict[str, int]:
    buckets = {"2": 0, "3-5": 0, "6-10": 0, "11-50": 0, "51+": 0}
    for s in sizes:
        if s == 2:
            buckets["2"] += 1
        elif s <= 5:
            buckets["3-5"] += 1
        elif s <= 10:
            buckets["6-10"] += 1
        elif s <= 50:
            buckets["11-50"] += 1
        else:
            buckets["51+"] += 1
    return buckets


class EvaluationService:
    """Wires the pure metric functions to ArangoDB collections.

    Parameters
    ----------
    db:
        ArangoDB database handle.
    edge_collection:
        Similarity edge collection (scored pairs). Suppressed edges are excluded.
    score_field:
        Edge attribute holding the score (default ``similarity``).
    """

    def __init__(self, db: Any, edge_collection: str, score_field: str = "similarity") -> None:
        self.db = db
        self.edge_collection = edge_collection
        self.score_field = score_field

    def _load_scored_pairs(self) -> List[ScoredPair]:
        cursor = self.db.aql.execute(
            f"""
            FOR e IN @@edges
                FILTER e.suppressed != true AND e.{self.score_field} != null
                RETURN [e._from, e._to, e.{self.score_field}]
            """,
            bind_vars={"@edges": self.edge_collection},
        )
        return [(row[0], row[1], float(row[2])) for row in cursor]

    def _load_truth(self, truth_collection: str) -> Set[str]:
        """Load ground-truth matching pairs.

        Accepts docs with either ``_from``/``_to`` or ``id_a``/``id_b`` keys.
        """
        cursor = self.db.aql.execute(
            """
            FOR d IN @@truth
                RETURN [d._from != null ? d._from : d.id_a,
                        d._to != null ? d._to : d.id_b]
            """,
            bind_vars={"@truth": truth_collection},
        )
        truth: Set[str] = set()
        for a, b in cursor:
            if a is not None and b is not None:
                truth.add(canonical_pair_id(str(a), str(b)))
        return truth

    def threshold_sweep(
        self,
        truth_collection: str,
        thresholds: Optional[Sequence[float]] = None,
    ) -> Dict[str, Any]:
        """Compute the labeled threshold sweep from stored edges + truth collection."""
        scored = self._load_scored_pairs()
        truth = self._load_truth(truth_collection)
        return threshold_sweep(scored, truth, thresholds=thresholds)

    def cluster_quality(
        self,
        cluster_collection: str,
        *,
        min_coherence: float = 0.5,
    ) -> Dict[str, Any]:
        """Compute unsupervised cluster-quality metrics from stored clusters + edges."""
        scored = self._load_scored_pairs()
        edge_scores: Dict[str, float] = {}
        for a, b, s in scored:
            edge_scores[canonical_pair_id(a, b)] = s

        clusters: List[List[str]] = []
        for doc in self.db.collection(cluster_collection):
            members = doc.get("members") or doc.get("member_keys") or []
            clusters.append([str(m) for m in members])
        return cluster_quality_summary(clusters, edge_scores, min_coherence=min_coherence)
