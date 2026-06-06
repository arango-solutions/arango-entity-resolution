"""
ANN (Approximate Nearest Neighbor) Adapter Layer

Vector similarity search backed exclusively by the ArangoDB 3.12+ **native
vector index** (``APPROX_NEAR_COSINE``). There is intentionally **no
brute-force fallback** in this code path: if the deployment is older than 3.12
or no ``vector`` index exists on the embedding field, vector search raises
:class:`VectorSearchUnavailableError` directing the operator to upgrade.

Brute-force cosine is only used as an internal ground-truth baseline inside
``scripts/benchmark_vector_blocking.py`` for recall measurement -- it is not a
supported production path and is not reachable through the public API.
"""

import logging
import math
import re
from typing import List, Dict, Any, Optional, Tuple
from arango.database import StandardDatabase

from ..utils.validation import validate_collection_name, validate_field_name


# Native vector index + APPROX_NEAR_COSINE require ArangoDB 3.12+.
ARANGODB_MIN_VERSION_FOR_VECTOR_INDEX = (3, 12)
DEFAULT_VECTOR_METRIC = "cosine"

METHOD_VECTOR_INDEX = "arango_vector_index"
METHOD_UNAVAILABLE = "unavailable"


class VectorSearchUnavailableError(RuntimeError):
    """Raised when native vector search (ArangoDB 3.12+ index) is unavailable."""


class ANNAdapter:
    """
    Native-only vector search using ``APPROX_NEAR_COSINE`` (ArangoDB 3.12+).

    Requires a ``vector`` index on the embedding field. Use
    :meth:`ensure_vector_index` to create one. If native vector search is not
    available, search methods raise :class:`VectorSearchUnavailableError`.
    """

    def __init__(
        self,
        db: StandardDatabase,
        collection: str,
        embedding_field: str = 'embedding_vector',
        metric: str = DEFAULT_VECTOR_METRIC,
    ):
        self.db = db
        self.collection = validate_collection_name(collection)
        self.embedding_field = validate_field_name(embedding_field)
        self.metric = metric

        self.logger = logging.getLogger(__name__)

        self._arango_version: Optional[Tuple[int, int, int]] = None
        self._has_vector_index = False
        self._detect_capabilities()

    # ------------------------------------------------------------------
    # Capability detection
    # ------------------------------------------------------------------

    def _detect_capabilities(self) -> None:
        try:
            version_str = self._server_version()
            match = re.match(r'(\d+)\.(\d+)\.(\d+)', version_str or "")
            if match:
                self._arango_version = tuple(int(x) for x in match.groups())  # type: ignore[assignment]
            self._has_vector_index = self._version_ok() and self._vector_index_exists()
            if self._has_vector_index:
                self.logger.info(
                    "Native vector index available (APPROX_NEAR_COSINE), version %s",
                    version_str,
                )
            else:
                self.logger.info(
                    "Native vector search unavailable (version %s, index present=%s)",
                    version_str or "unknown", self._vector_index_exists_safe(),
                )
        except Exception as e:
            self.logger.warning("Failed to detect vector-search capabilities: %s", e)
            self._has_vector_index = False

    def _server_version(self) -> str:
        """Return the ArangoDB server version string (e.g. '3.12.9-1').

        Uses the server endpoint (``db.version()``); ``db.properties()`` returns
        database metadata that does not include the server version. Falls back to
        ``properties()`` for compatibility with simple fakes/mocks.
        """
        try:
            version = self.db.version()
            if isinstance(version, dict):
                return version.get("version", "") or ""
            return str(version or "")
        except Exception:
            try:
                return self.db.properties().get("version", "") or ""
            except Exception:
                return ""

    def _version_ok(self) -> bool:
        return (
            self._arango_version is not None
            and self._arango_version[:2] >= ARANGODB_MIN_VERSION_FOR_VECTOR_INDEX
        )

    def _vector_index_exists(self) -> bool:
        for index in self.db.collection(self.collection).indexes():
            if index.get("type") == "vector" and self.embedding_field in (
                index.get("fields") or []
            ):
                return True
        return False

    def _vector_index_exists_safe(self) -> bool:
        try:
            return self._vector_index_exists()
        except Exception:
            return False

    @property
    def native_available(self) -> bool:
        return self._has_vector_index

    @property
    def method(self) -> str:
        return METHOD_VECTOR_INDEX if self._has_vector_index else METHOD_UNAVAILABLE

    @property
    def arango_version(self) -> Optional[Tuple[int, int, int]]:
        return self._arango_version

    def _require_native(self) -> None:
        if self._has_vector_index:
            return
        version = (
            ".".join(str(p) for p in self._arango_version)
            if self._arango_version else "unknown"
        )
        raise VectorSearchUnavailableError(
            "Vector search requires ArangoDB 3.12+ with a native vector index on "
            f"'{self.collection}.{self.embedding_field}' (detected version "
            f"{version}, vector index present={self._vector_index_exists_safe()}). "
            "Upgrade to ArangoDB 3.12+ and create the index "
            "(VectorBlockingStrategy(create_vector_index=True) or "
            "ANNAdapter.ensure_vector_index()). Brute-force vector search is not "
            "supported."
        )

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def ensure_vector_index(
        self,
        dimension: Optional[int] = None,
        n_lists: Optional[int] = None,
        metric: Optional[str] = None,
        training_iterations: int = 25,
        default_n_probe: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create a ``vector`` index on the embedding field if absent.

        Requires ArangoDB 3.12+. Auto-detects ``dimension`` from a sample
        document and derives ``n_lists`` (clamped to [1, n_docs]) when omitted.

        The index params mirror ArangoDB's IVF vector index:
        ``metric``, ``dimension``, ``nLists``, ``trainingIterations`` (IVF
        training passes), and ``defaultNProbe`` (lists probed at query time;
        defaults to ``min(nLists, 64)``). Omitting ``trainingIterations`` /
        ``defaultNProbe`` can cause index creation to stall on some builds, so
        they are always set.
        """
        if self._vector_index_exists_safe():
            self._has_vector_index = True
            return {"created": False, "reason": "index already exists", "method": self.method}

        if not self._version_ok():
            version = (
                ".".join(str(p) for p in self._arango_version)
                if self._arango_version else "unknown"
            )
            raise VectorSearchUnavailableError(
                f"Vector index requires ArangoDB 3.12+ (detected {version})."
            )

        coll = self.db.collection(self.collection)
        n_docs = coll.count()
        if n_docs == 0:
            raise RuntimeError(
                f"Cannot build a vector index on empty collection '{self.collection}'."
            )

        if dimension is None:
            dimension = self._detect_dimension()
        if not dimension or dimension <= 0:
            raise RuntimeError(
                f"Could not determine embedding dimension for "
                f"'{self.collection}.{self.embedding_field}'."
            )

        if n_lists is None:
            n_lists = max(1, int(math.sqrt(n_docs)))
        n_lists = max(1, min(n_lists, n_docs))

        if default_n_probe is None:
            default_n_probe = min(n_lists, 64)
        default_n_probe = max(1, min(default_n_probe, n_lists))

        definition = {
            "type": "vector",
            "fields": [self.embedding_field],
            "params": {
                "metric": metric or self.metric,
                "dimension": int(dimension),
                "nLists": int(n_lists),
                "trainingIterations": int(training_iterations),
                "defaultNProbe": int(default_n_probe),
            },
        }
        try:
            result = coll.add_index(definition)
        except Exception as exc:
            msg = str(exc).lower()
            if "experimental-vector-index" in msg or "vector index feature is not enabled" in msg:
                raise VectorSearchUnavailableError(
                    "ArangoDB vector index feature is not enabled. Start the server "
                    "with `--experimental-vector-index` to use native vector search."
                ) from exc
            raise
        self._has_vector_index = True
        self.logger.info(
            "Created vector index on %s.%s (dim=%s, nLists=%s, metric=%s, "
            "trainingIterations=%s, defaultNProbe=%s)",
            self.collection, self.embedding_field, dimension, n_lists,
            metric or self.metric, training_iterations, default_n_probe,
        )
        return {
            "created": True,
            "method": self.method,
            "dimension": int(dimension),
            "n_lists": int(n_lists),
            "metric": metric or self.metric,
            "training_iterations": int(training_iterations),
            "default_n_probe": int(default_n_probe),
            "index": result,
        }

    def _detect_dimension(self) -> Optional[int]:
        cursor = self.db.aql.execute(
            f"""
            FOR doc IN @@col
                FILTER doc.{self.embedding_field} != null
                LIMIT 1
                RETURN LENGTH(doc.{self.embedding_field})
            """,
            bind_vars={"@col": self.collection},
        )
        rows = list(cursor)
        return int(rows[0]) if rows and rows[0] else None

    # ------------------------------------------------------------------
    # Search (native only)
    # ------------------------------------------------------------------

    @staticmethod
    def _post_filter_conditions(
        var: str,
        blocking_field: Optional[str],
        blocking_value: Optional[Any],
        filters: Optional[Dict[str, Dict[str, Any]]],
        bind_vars: Dict[str, Any],
    ) -> List[str]:
        conditions: List[str] = []
        if blocking_field and blocking_value is not None:
            conditions.append(f"{var}.{validate_field_name(blocking_field)} == @blocking_value")
            bind_vars["blocking_value"] = blocking_value
        if filters:
            for field, condition in filters.items():
                safe = validate_field_name(field)
                if "equals" in condition:
                    conditions.append(f"{var}.{safe} == @filter_{safe}")
                    bind_vars[f"filter_{safe}"] = condition["equals"]
                elif "in" in condition:
                    conditions.append(f"{var}.{safe} IN @filter_{safe}")
                    bind_vars[f"filter_{safe}"] = condition["in"]
        return conditions

    def find_similar_vectors(
        self,
        query_vector: Optional[List[float]] = None,
        query_doc_key: Optional[str] = None,
        similarity_threshold: float = 0.7,
        limit: int = 20,
        blocking_field: Optional[str] = None,
        blocking_value: Optional[Any] = None,
        filters: Optional[Dict[str, Dict[str, Any]]] = None,
        exclude_self: bool = True,
    ) -> List[Dict[str, Any]]:
        """Single-query ANN search via APPROX_NEAR_COSINE (native only)."""
        if query_vector is None and query_doc_key is None:
            raise ValueError("Either query_vector or query_doc_key must be provided")
        self._require_native()

        if query_vector is None and query_doc_key:
            doc = self.db.collection(self.collection).get(query_doc_key)
            if not doc or self.embedding_field not in doc:
                return []
            query_vector = doc[self.embedding_field]
        if query_vector is None:
            return []

        bind_vars: Dict[str, Any] = {"@col": self.collection, "query_vector": query_vector}
        post = self._post_filter_conditions("doc", blocking_field, blocking_value, filters, bind_vars)
        if exclude_self and query_doc_key:
            post.append("doc._key != @exclude_key")
            bind_vars["exclude_key"] = query_doc_key

        over_fetch = limit * (4 if post else 1) + (1 if exclude_self else 0)
        bind_vars.update({"over_k": over_fetch, "limit": limit, "threshold": similarity_threshold})
        post_clause = ("\n                FILTER " + " AND ".join(post)) if post else ""

        query = f"""
            FOR doc IN @@col
                LET score = APPROX_NEAR_COSINE(doc.{self.embedding_field}, @query_vector)
                SORT score DESC
                LIMIT @over_k{post_clause}
                FILTER score >= @threshold
                LIMIT @limit
                RETURN {{
                    doc_key: doc._key,
                    similarity: score,
                    method: "{METHOD_VECTOR_INDEX}"
                }}
        """
        return list(self.db.aql.execute(query, bind_vars=bind_vars))

    def find_all_pairs(
        self,
        similarity_threshold: float = 0.7,
        limit_per_entity: int = 20,
        blocking_field: Optional[str] = None,
        filters: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Per-source APPROX_NEAR_COSINE top-k search over the whole collection
        (O(n*k)). Pairs are de-duplicated by the caller
        (``BlockingStrategy._normalize_pairs``). Native only.
        """
        self._require_native()

        bind_vars: Dict[str, Any] = {
            "@col": self.collection,
            "threshold": similarity_threshold,
            "limit": limit_per_entity,
        }
        outer = self._post_filter_conditions("doc1", None, None, filters, bind_vars)
        outer_clause = ("\n                FILTER " + " AND ".join(outer)) if outer else ""

        inner = ["doc2._key != doc1._key"]
        if blocking_field:
            safe = validate_field_name(blocking_field)
            inner.append(f"doc2.{safe} == doc1.{safe}")
        inner_clause = " AND ".join(inner)

        bind_vars["over_k"] = limit_per_entity * (4 if blocking_field else 1) + 1

        query = f"""
            FOR doc1 IN @@col
                FILTER doc1.{self.embedding_field} != null{outer_clause}
                FOR doc2 IN @@col
                    LET score = APPROX_NEAR_COSINE(doc2.{self.embedding_field}, doc1.{self.embedding_field})
                    SORT score DESC
                    LIMIT @over_k
                    FILTER {inner_clause}
                    FILTER score >= @threshold
                    LIMIT @limit
                    RETURN {{
                        doc1_key: doc1._key,
                        doc2_key: doc2._key,
                        similarity: score,
                        method: "{METHOD_VECTOR_INDEX}"
                    }}
        """
        return list(self.db.aql.execute(query, bind_vars=bind_vars))
