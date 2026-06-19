"""Estimate and persist EM model parameters from real candidate pairs (plan 1.1).

Ties the pure EM core (:mod:`entity_resolution.learning.em_estimator`) to a live
database: samples candidate pairs from the similarity-edge collection, recomputes
per-field agreement with the configured comparators, runs Fellegi-Sunter EM,
computes per-field term-frequency tables, and persists the learned parameters to
``er_model_params`` (versioned + config-hashed for reproducibility) and the TF
tables to ``er_term_frequencies``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .em_estimator import EMEstimator, EMResult
from ..utils.graph_utils import extract_key_from_vertex_id

logger = logging.getLogger(__name__)

_MODEL_COLLECTION = "er_model_params"
_TF_COLLECTION = "er_term_frequencies"


def config_hash(field_names: Sequence[str], agreement_thresholds: Dict[str, float],
                algorithm: str) -> str:
    """Stable hash identifying an estimation configuration."""
    payload = json.dumps(
        {
            "fields": sorted(field_names),
            "thresholds": {k: agreement_thresholds[k] for k in sorted(agreement_thresholds)},
            "algorithm": algorithm,
        },
        sort_keys=True,
    )
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:16]


class ModelParameterEstimator:
    """Sample → compare → EM → persist, against a live ArangoDB."""

    def __init__(
        self,
        db: Any,
        similarity_service: Any,
        edge_collection: str,
        field_names: Sequence[str],
        *,
        agreement_thresholds: Optional[Dict[str, float]] = None,
        default_threshold: float = 0.85,
        model_collection: str = _MODEL_COLLECTION,
        tf_collection: str = _TF_COLLECTION,
    ) -> None:
        self.db = db
        # A BatchSimilarityService (or anything exposing compute_similarities_detailed).
        self.similarity_service = similarity_service
        self.edge_collection = edge_collection
        self.field_names = list(field_names)
        self.agreement_thresholds = dict(agreement_thresholds or {})
        self.default_threshold = default_threshold
        self.model_collection = model_collection
        self.tf_collection = tf_collection
        self.algorithm = getattr(similarity_service, "algorithm_name", "unknown")

    # ------------------------------------------------------------------
    # Sampling + estimation
    # ------------------------------------------------------------------

    def sample_comparisons(self, sample_size: int) -> List[Dict[str, float]]:
        """Sample non-suppressed candidate pairs and compute per-field scores."""
        cursor = self.db.aql.execute(
            """
            FOR e IN @@edges
                FILTER e.suppressed != true
                SORT RAND()
                LIMIT @n
                RETURN [e._from, e._to]
            """,
            bind_vars={"@edges": self.edge_collection, "n": int(sample_size)},
        )
        pairs: List[Tuple[str, str]] = [
            (extract_key_from_vertex_id(a), extract_key_from_vertex_id(b)) for a, b in cursor
        ]
        if not pairs:
            return []
        detailed = self.similarity_service.compute_similarities_detailed(
            pairs, threshold=0.0
        )
        return [d.get("field_scores", {}) for d in detailed]

    def estimate(
        self,
        sample_size: int = 100_000,
        *,
        max_iterations: int = 50,
        tol: float = 1e-5,
    ) -> EMResult:
        comparisons = self.sample_comparisons(sample_size)
        if not comparisons:
            raise ValueError(
                f"no candidate pairs sampled from '{self.edge_collection}'; "
                "run blocking/edge creation first"
            )
        estimator = EMEstimator(
            field_names=self.field_names,
            agreement_thresholds=self.agreement_thresholds,
            default_threshold=self.default_threshold,
            max_iterations=max_iterations,
            tol=tol,
        )
        return estimator.estimate(comparisons)

    # ------------------------------------------------------------------
    # Term frequencies (Splink's second pillar)
    # ------------------------------------------------------------------

    def compute_term_frequencies(
        self,
        source_collection: str,
        fields: Sequence[str],
        *,
        top_n: int = 100,
    ) -> Dict[str, Any]:
        """Per-field value frequencies via one COLLECT per field.

        Stores the ``top_n`` most common values and the total non-null count per
        field, so the scorer can scale u-probability by relative value frequency
        (a common value agreeing is weaker evidence than a rare one).
        """
        from ..utils.validation import validate_collection_name, validate_field_name

        validate_collection_name(source_collection)
        tables: Dict[str, Any] = {}
        for field in fields:
            validate_field_name(field)
            cursor = self.db.aql.execute(
                f"""
                FOR d IN @@col
                    FILTER d.{field} != null
                    COLLECT value = d.{field} WITH COUNT INTO cnt
                    SORT cnt DESC
                    LIMIT @top_n
                    RETURN {{value: value, count: cnt}}
                """,
                bind_vars={"@col": source_collection, "top_n": int(top_n)},
            )
            rows = list(cursor)
            total_cursor = self.db.aql.execute(
                f"""
                FOR d IN @@col
                    FILTER d.{field} != null
                    COLLECT WITH COUNT INTO cnt
                    RETURN cnt
                """,
                bind_vars={"@col": source_collection},
            )
            total = next(iter(total_cursor), 0)
            tables[field] = {
                "total": total,
                "top_values": [
                    {"value": r["value"], "count": r["count"],
                     "relative_frequency": (r["count"] / total) if total else 0.0}
                    for r in rows
                ],
            }
        return tables

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _ensure(self, name: str) -> None:
        if not self.db.has_collection(name):
            self.db.create_collection(name)

    def _next_version(self, chash: str) -> int:
        self._ensure(self.model_collection)
        cursor = self.db.aql.execute(
            """
            FOR d IN @@col FILTER d.config_hash == @h
                COLLECT AGGREGATE mx = MAX(d.version) RETURN mx
            """,
            bind_vars={"@col": self.model_collection, "h": chash},
        )
        current = next(iter(cursor), None)
        return int(current) + 1 if current else 1

    def persist(self, result: EMResult, *, sample_size: int) -> Dict[str, Any]:
        """Persist an EM result to ``er_model_params`` (versioned, config-hashed)."""
        chash = config_hash(self.field_names, self._effective_thresholds(), self.algorithm)
        version = self._next_version(chash)
        doc = {
            "_key": f"{chash}_v{version}",
            "config_hash": chash,
            "version": version,
            "algorithm": self.algorithm,
            "fields": result.fields,
            "agreement_thresholds": self._effective_thresholds(),
            "m": result.m,
            "u": result.u,
            "lambda": result.lambda_,
            "converged": result.converged,
            "iterations": result.iterations,
            "n_pairs": result.n_pairs,
            "log_likelihood": result.log_likelihood,
            "sample_size": sample_size,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.db.collection(self.model_collection).insert(doc, overwrite=True)
        return doc

    def persist_term_frequencies(self, tables: Dict[str, Any]) -> int:
        """Persist TF tables, one doc per field (overwrite by field key)."""
        self._ensure(self.tf_collection)
        coll = self.db.collection(self.tf_collection)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        count = 0
        for field, table in tables.items():
            coll.insert(
                {"_key": field, "field": field, "updated_at": now, **table},
                overwrite=True,
            )
            count += 1
        return count

    def _effective_thresholds(self) -> Dict[str, float]:
        return {f: self.agreement_thresholds.get(f, self.default_threshold) for f in self.field_names}

    def load_latest(self, chash: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Load the highest-version model parameters (optionally for one config)."""
        if not self.db.has_collection(self.model_collection):
            return None
        filt = "FILTER d.config_hash == @h" if chash else ""
        bind: Dict[str, Any] = {"@col": self.model_collection}
        if chash:
            bind["h"] = chash
        cursor = self.db.aql.execute(
            f"FOR d IN @@col {filt} SORT d.version DESC LIMIT 1 RETURN d",
            bind_vars=bind,
        )
        return next(iter(cursor), None)

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run(
        self,
        source_collection: str,
        *,
        sample_size: int = 100_000,
        with_term_frequencies: bool = True,
        tf_fields: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Estimate, persist, and (optionally) compute/persist term frequencies."""
        result = self.estimate(sample_size)
        model_doc = self.persist(result, sample_size=sample_size)
        out: Dict[str, Any] = {
            "model": result.to_dict(),
            "model_key": model_doc["_key"],
            "version": model_doc["version"],
        }
        if with_term_frequencies:
            fields = list(tf_fields) if tf_fields else self.field_names
            tables = self.compute_term_frequencies(source_collection, fields)
            out["term_frequency_fields"] = self.persist_term_frequencies(tables)
        return out
