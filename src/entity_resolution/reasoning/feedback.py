"""
Active Learning Feedback Store & Threshold Optimizer.

Every time LLMMatchVerifier makes a decision, that labeled pair is valuable
training data.  This module:

1. **FeedbackStore** — persists LLM verdicts (and human corrections) in an
   ArangoDB collection so nothing is lost between runs.

2. **ThresholdOptimizer** — reads the feedback store and uses isotonic
   regression (or simple percentile analysis when sklearn is unavailable)
   to derive optimal ``low_threshold`` and ``high_threshold`` values that
   minimise LLM call volume while maintaining target precision/recall.

3. **AdaptiveLLMVerifier** — subclass of ``LLMMatchVerifier`` that
   auto-loads updated thresholds from the feedback store at configurable
   intervals.

Usage::

    from entity_resolution.reasoning.feedback import FeedbackStore, AdaptiveLLMVerifier

    store = FeedbackStore(db, collection="er_feedback")
    verifier = AdaptiveLLMVerifier(feedback_store=store)

    result = verifier.verify(rec_a, rec_b, score=0.70, field_scores=fs)
    # verdict auto-saved; thresholds auto-refresh every 100 calls
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_FEEDBACK_COLLECTION = "er_llm_feedback"


# ---------------------------------------------------------------------------
# FeedbackStore
# ---------------------------------------------------------------------------

class FeedbackStore:
    """
    Persist and retrieve LLM match verification verdicts in ArangoDB.

    Each verdict document contains:
    - ``key_a``, ``key_b`` — entity keys (or content hashes for new records)
    - ``score`` — original similarity score
    - ``decision`` — "match" | "no_match"
    - ``confidence`` — LLM self-reported confidence
    - ``source`` — "llm" | "human"
    - ``model`` — LLM model string
    - ``ts`` — unix timestamp
    - ``field_scores`` — per-field breakdown (optional)
    """

    def __init__(self, db, collection: str = _FEEDBACK_COLLECTION) -> None:
        self.db = db
        self.collection = collection
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        if not self.db.has_collection(self.collection):
            self.db.create_collection(self.collection)
            logger.info("FeedbackStore: created collection '%s'", self.collection)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(
        self,
        record_a: Dict[str, Any],
        record_b: Dict[str, Any],
        score: float,
        decision: str,
        confidence: float,
        *,
        source: str = "llm",
        model: Optional[str] = None,
        field_scores: Optional[Dict[str, Any]] = None,
        reviewer: Optional[str] = None,
    ) -> str:
        """Persist a verdict.  Returns the document ``_key``."""
        key_a = record_a.get("_key") or _content_hash(record_a)
        key_b = record_b.get("_key") or _content_hash(record_b)

        # Deterministic key so re-runs don't duplicate
        pair_hash = hashlib.md5(
            f"{min(key_a, key_b)}|{max(key_a, key_b)}".encode()
        ).hexdigest()

        doc = {
            "_key": pair_hash,
            "key_a": key_a,
            "key_b": key_b,
            "score": round(score, 4),
            "decision": decision,
            "confidence": round(confidence, 4),
            "source": source,
            "model": model,
            "reviewer": reviewer,
            "ts": time.time(),
            "field_scores": field_scores or {},
        }

        self.db.collection(self.collection).insert(doc, overwrite=True)
        return pair_hash

    def record_human_correction(
        self,
        key_a: str,
        key_b: str,
        correct_decision: str,
        *,
        score: float = 0.0,
        confidence: float = 1.0,
        reviewer: Optional[str] = None,
    ) -> str:
        """Override a verdict with a human-confirmed label."""
        return self.save(
            {"_key": key_a},
            {"_key": key_b},
            score=score,
            decision=correct_decision,
            confidence=confidence,
            source="human",
            reviewer=reviewer,
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def all_verdicts(self) -> List[Dict[str, Any]]:
        """Return all stored verdicts."""
        cursor = self.db.aql.execute(
            "FOR doc IN @@col RETURN doc",
            bind_vars={"@col": self.collection},
        )
        return list(cursor)

    def verdicts_by_decision(self, decision: str) -> List[Dict[str, Any]]:
        """Return verdicts filtered by decision ("match" or "no_match")."""
        cursor = self.db.aql.execute(
            "FOR doc IN @@col FILTER doc.decision == @d RETURN doc",
            bind_vars={"@col": self.collection, "d": decision},
        )
        return list(cursor)

    def stats(self) -> Dict[str, Any]:
        """Aggregate statistics over stored verdicts."""
        cursor = self.db.aql.execute(
            """
            FOR doc IN @@col
                COLLECT decision = doc.decision
                AGGREGATE cnt = COUNT(1), avg_score = AVG(doc.score), avg_conf = AVG(doc.confidence)
                RETURN {decision, count: cnt, avg_score, avg_confidence: avg_conf}
            """,
            bind_vars={"@col": self.collection},
        )
        return {"by_decision": list(cursor), "total": self.db.collection(self.collection).count()}

    # ------------------------------------------------------------------
    # Extended query API (used by UI backend)
    # ------------------------------------------------------------------

    _SORT_FIELDS = {"score": "doc.score", "created_at": "doc.ts", "confidence": "doc.confidence"}

    def query_verdicts(
        self,
        status: Optional[str] = None,
        score_min: Optional[float] = None,
        score_max: Optional[float] = None,
        source: Optional[str] = None,
        sort_by: str = "score",
        sort_order: str = "asc",
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Paginated, filterable query over the feedback collection.

        Returns ``{"items": [...], "total": int, "limit": int, "offset": int}``.
        """
        filters: List[str] = []
        bind_vars: Dict[str, Any] = {"@col": self.collection}

        if status is not None:
            filters.append("doc.decision == @status")
            bind_vars["status"] = status
        if score_min is not None:
            filters.append("doc.score >= @score_min")
            bind_vars["score_min"] = score_min
        if score_max is not None:
            filters.append("doc.score <= @score_max")
            bind_vars["score_max"] = score_max
        if source is not None:
            filters.append("doc.source == @source")
            bind_vars["source"] = source

        filter_clause = (" FILTER " + " AND ".join(filters)) if filters else ""
        sort_field = self._SORT_FIELDS.get(sort_by, "doc.score")
        direction = "DESC" if sort_order == "desc" else "ASC"

        count_aql = f"FOR doc IN @@col{filter_clause} COLLECT WITH COUNT INTO cnt RETURN cnt"
        total = next(iter(self.db.aql.execute(count_aql, bind_vars=bind_vars)), 0)

        data_aql = (
            f"FOR doc IN @@col{filter_clause}"
            f" SORT {sort_field} {direction}"
            f" LIMIT @off, @lim"
            f" RETURN doc"
        )
        bind_vars_data = {**bind_vars, "off": offset, "lim": limit}
        items = list(self.db.aql.execute(data_aql, bind_vars=bind_vars_data))

        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def count_by_status(self) -> Dict[str, int]:
        """Return verdict counts grouped by decision.

        Returns a dict like ``{"match": 5, "no_match": 3, "uncertain": 1}``.
        """
        cursor = self.db.aql.execute(
            "FOR doc IN @@col COLLECT decision = doc.decision"
            " WITH COUNT INTO cnt RETURN {decision, count: cnt}",
            bind_vars={"@col": self.collection},
        )
        return {row["decision"]: row["count"] for row in cursor}

    def pending_review_count(self) -> int:
        """Return count of LLM verdicts that have no human correction.

        A verdict is *pending review* if ``source == 'llm'`` and there is no
        document with the same ``key_a`` / ``key_b`` pair where
        ``source == 'human'``.
        """
        cursor = self.db.aql.execute(
            """
            LET human_pairs = (
                FOR h IN @@col
                    FILTER h.source == 'human'
                    RETURN CONCAT(h.key_a, '|', h.key_b)
            )
            FOR doc IN @@col
                FILTER doc.source == 'llm'
                FILTER CONCAT(doc.key_a, '|', doc.key_b) NOT IN human_pairs
                COLLECT WITH COUNT INTO cnt
                RETURN cnt
            """,
            bind_vars={"@col": self.collection},
        )
        return next(iter(cursor), 0)


# ---------------------------------------------------------------------------
# ThresholdOptimizer
# ---------------------------------------------------------------------------

class ThresholdOptimizer:
    """
    Derive optimal ``low_threshold`` and ``high_threshold`` from feedback.

    Uses isotonic regression when ``scikit-learn`` is available, otherwise
    falls back to percentile-based analysis.

    Parameters
    ----------
    target_precision:
        Minimum acceptable precision for the "match" class (default 0.95).
    min_samples:
        Minimum number of labeled pairs required before optimization runs.
    """

    def __init__(
        self,
        feedback_store: FeedbackStore,
        target_precision: float = 0.95,
        min_samples: int = 20,
    ) -> None:
        self.store = feedback_store
        self.target_precision = target_precision
        self.min_samples = min_samples

    def optimize(self) -> Dict[str, Any]:
        """
        Compute recommended thresholds from stored feedback.

        Returns a dict with ``low_threshold``, ``high_threshold``, and
        ``sample_count``.  If there aren't enough samples yet, returns
        the defaults.
        """
        verdicts = self.store.all_verdicts()
        if len(verdicts) < self.min_samples:
            logger.info(
                "ThresholdOptimizer: only %d samples (need %d) — using defaults",
                len(verdicts),
                self.min_samples,
            )
            return {
                "low_threshold": 0.55,
                "high_threshold": 0.80,
                "sample_count": len(verdicts),
                "optimized": False,
                "reason": f"Need {self.min_samples} samples, have {len(verdicts)}",
            }

        scores = [v["score"] for v in verdicts]
        labels = [1 if v["decision"] == "match" else 0 for v in verdicts]

        try:
            return self._optimize_sklearn(scores, labels, len(verdicts))
        except ImportError:
            return self._optimize_percentile(scores, labels, len(verdicts))

    def _optimize_sklearn(
        self, scores: List[float], labels: List[int], n: int
    ) -> Dict[str, Any]:
        from sklearn.isotonic import IsotonicRegression
        import numpy as np

        scores_arr = np.array(scores)
        labels_arr = np.array(labels)
        order = np.argsort(scores_arr)
        scores_sorted = scores_arr[order]
        labels_sorted = labels_arr[order]

        ir = IsotonicRegression(out_of_bounds="clip")
        calibrated = ir.fit_transform(scores_sorted, labels_sorted)

        # high_threshold: lowest score where calibrated P(match) >= target_precision
        high_idx = np.searchsorted(calibrated, self.target_precision)
        high_threshold = float(scores_sorted[min(high_idx, len(scores_sorted) - 1)])

        # low_threshold: highest score where calibrated P(match) <= (1 - target_precision)
        low_idx = np.searchsorted(calibrated, 1.0 - self.target_precision)
        low_threshold = float(scores_sorted[min(low_idx, len(scores_sorted) - 1)])

        low_threshold = round(max(0.30, min(low_threshold, high_threshold - 0.10)), 3)
        high_threshold = round(min(0.95, max(high_threshold, low_threshold + 0.10)), 3)

        return {
            "low_threshold": low_threshold,
            "high_threshold": high_threshold,
            "sample_count": n,
            "optimized": True,
            "method": "isotonic_regression",
        }

    def _optimize_percentile(
        self, scores: List[float], labels: List[int], n: int
    ) -> Dict[str, Any]:
        """Simple percentile fallback when sklearn is unavailable."""
        match_scores = sorted([s for s, l in zip(scores, labels) if l == 1])
        no_match_scores = sorted([s for s, l in zip(scores, labels) if l == 0])

        if not match_scores or not no_match_scores:
            return {
                "low_threshold": 0.55,
                "high_threshold": 0.80,
                "sample_count": n,
                "optimized": False,
                "reason": "Not enough positive and negative examples",
            }

        # low = 10th percentile of match scores
        low_idx = max(0, int(len(match_scores) * 0.10) - 1)
        low_threshold = round(match_scores[low_idx], 3)

        # high = 90th percentile of no-match scores (upper boundary)
        high_idx = min(len(no_match_scores) - 1, int(len(no_match_scores) * 0.90))
        high_threshold = round(no_match_scores[high_idx] + 0.05, 3)
        high_threshold = round(min(0.95, max(high_threshold, low_threshold + 0.10)), 3)

        return {
            "low_threshold": low_threshold,
            "high_threshold": high_threshold,
            "sample_count": n,
            "optimized": True,
            "method": "percentile",
        }


# ---------------------------------------------------------------------------
# AdaptiveLLMVerifier
# ---------------------------------------------------------------------------

class AdaptiveLLMVerifier:
    """
    ``LLMMatchVerifier`` that automatically saves verdicts to ``FeedbackStore``
    and refreshes its thresholds every ``refresh_every`` calls.

    Parameters
    ----------
    feedback_store:
        A ``FeedbackStore`` instance.
    refresh_every:
        Number of verify() calls between threshold refreshes (default 100).
    kwargs:
        Forwarded to ``LLMMatchVerifier.__init__``.
    """

    def __init__(
        self,
        feedback_store: FeedbackStore,
        refresh_every: int = 100,
        optimizer_target_precision: float = 0.95,
        optimizer_min_samples: int = 20,
        **kwargs,
    ) -> None:
        from entity_resolution.reasoning.llm_verifier import LLMMatchVerifier

        self.store = feedback_store
        self.refresh_every = refresh_every
        self._call_count = 0
        self._optimizer = ThresholdOptimizer(
            feedback_store,
            target_precision=optimizer_target_precision,
            min_samples=optimizer_min_samples,
        )
        self.verifier = LLMMatchVerifier(**kwargs)

    # ------------------------------------------------------------------
    # Public API (mirrors LLMMatchVerifier)
    # ------------------------------------------------------------------

    def verify(
        self,
        record_a: Dict[str, Any],
        record_b: Dict[str, Any],
        score: float,
        field_scores: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Verify, save verdict, auto-refresh thresholds."""
        self._maybe_refresh_thresholds()
        result = self.verifier.verify(record_a, record_b, score, field_scores)

        # Only persist decisive labels; "error"/"pending_review" outcomes are
        # not training data and must not reach the ThresholdOptimizer.
        if result.get("llm_called") and result.get("decision") in ("match", "no_match"):
            self.store.save(
                record_a, record_b,
                score=score,
                decision=result["decision"],
                confidence=result["confidence"],
                source="llm",
                model=result.get("model"),
                field_scores=field_scores,
            )

        self._call_count += 1
        return result

    def verify_batch(
        self,
        pairs: List[Tuple[Dict[str, Any], Dict[str, Any], float]],
        field_scores_list: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        return [
            self.verify(a, b, s, (field_scores_list or [None] * len(pairs))[i])
            for i, (a, b, s) in enumerate(pairs)
        ]

    def record_human_correction(self, key_a: str, key_b: str, correct_decision: str) -> None:
        """Record a human override for a previous LLM decision."""
        self.store.record_human_correction(key_a, key_b, correct_decision)

    def current_thresholds(self) -> Dict[str, float]:
        return {
            "low_threshold": self.verifier.low_threshold,
            "high_threshold": self.verifier.high_threshold,
        }

    def optimize_thresholds(self) -> Dict[str, Any]:
        """Force a threshold optimization run and apply results."""
        result = self._optimizer.optimize()
        if result.get("optimized"):
            self.verifier.low_threshold = result["low_threshold"]
            self.verifier.high_threshold = result["high_threshold"]
            logger.info(
                "AdaptiveLLMVerifier: updated thresholds low=%.3f high=%.3f (%d samples)",
                result["low_threshold"],
                result["high_threshold"],
                result["sample_count"],
            )
        return result

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _maybe_refresh_thresholds(self) -> None:
        if self._call_count > 0 and self._call_count % self.refresh_every == 0:
            self.optimize_thresholds()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _content_hash(record: Dict[str, Any]) -> str:
    """Stable hash of record content for records without a _key."""
    clean = {k: v for k, v in sorted(record.items()) if not k.startswith("_")}
    return hashlib.md5(json.dumps(clean, default=str, sort_keys=True).encode()).hexdigest()[:16]
