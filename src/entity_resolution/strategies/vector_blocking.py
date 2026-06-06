"""
Vector Blocking Strategy for Entity Resolution

Uses vector embeddings and the ArangoDB 3.12+ native vector index
(``APPROX_NEAR_COSINE``) to find candidate pairs by semantic similarity. This
is a Tier 3 blocking strategy that captures fuzzy matches missed by exact
(Tier 1) or text-based (Tier 2) blocking.

Requirements:
- ArangoDB 3.12+ with a native ``vector`` index on the embedding field. There
  is no brute-force fallback: on older versions, or without an index, candidate
  generation raises ``VectorSearchUnavailableError``. Pass
  ``create_vector_index=True`` to build the index automatically.
- Embeddings must already be stored in documents (use ``EmbeddingService``).

Based on research:
- Ebraheem et al. (2018): "Distributed Representations of Tuples for Entity Resolution"
"""

import logging
import time
from typing import List, Dict, Any, Optional
from arango.database import StandardDatabase

from .base_strategy import BlockingStrategy
from ..utils.constants import DEFAULT_SIMILARITY_THRESHOLD
from ..utils.validation import validate_field_name
from ..similarity.ann_adapter import ANNAdapter, VectorSearchUnavailableError


# Constants for vector blocking configuration
DEFAULT_EMBEDDING_FIELD = 'embedding_vector'
DEFAULT_LIMIT_PER_ENTITY = 20


class VectorBlockingStrategy(BlockingStrategy):
    """
    Vector-based blocking using the native ArangoDB vector index.

    Generates candidate pairs by finding documents with similar embeddings via
    ``APPROX_NEAR_COSINE`` (ArangoDB 3.12+). Requires a ``vector`` index on the
    embedding field; there is no brute-force fallback.

    Attributes:
        embedding_field: Field name containing vector embeddings.
        similarity_threshold: Minimum cosine similarity (0-1) to consider a match.
        limit_per_entity: Maximum candidates per document.
        blocking_field: Optional field for additional blocking (e.g., state).
    """

    def __init__(
        self,
        db: StandardDatabase,
        collection: str,
        embedding_field: str = DEFAULT_EMBEDDING_FIELD,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        limit_per_entity: int = DEFAULT_LIMIT_PER_ENTITY,
        blocking_field: Optional[str] = None,
        filters: Optional[Dict[str, Dict[str, Any]]] = None,
        create_vector_index: bool = False,
        vector_index_n_lists: Optional[int] = None,
    ):
        """
        Initialize vector blocking strategy.

        Args:
            db: ArangoDB database connection (3.12+ for vector search).
            collection: Source collection name.
            embedding_field: Field containing embeddings (default 'embedding_vector').
            similarity_threshold: Minimum cosine similarity (default 0.75).
            limit_per_entity: Max candidates per document (default 20).
            blocking_field: Optional field to block on (e.g., 'state').
            filters: Optional filters to apply before blocking.
            create_vector_index: If True, create the native vector index on the
                embedding field before searching (no-op if it already exists).
                Requires ArangoDB 3.12+.
            vector_index_n_lists: Optional nLists (IVF partitions); auto-derived
                from document count when omitted.

        Raises:
            ValueError: If similarity_threshold not in [0, 1] or limit_per_entity < 1.
        """
        super().__init__(db, collection, filters)

        if not 0 <= similarity_threshold <= 1:
            raise ValueError(
                f"similarity_threshold must be in [0, 1], got {similarity_threshold}"
            )
        if limit_per_entity < 1:
            raise ValueError(f"limit_per_entity must be >= 1, got {limit_per_entity}")

        self.embedding_field = validate_field_name(embedding_field)
        self.similarity_threshold = similarity_threshold
        self.limit_per_entity = limit_per_entity
        self.blocking_field = validate_field_name(blocking_field) if blocking_field else None

        self.logger = logging.getLogger(__name__)

        self.ann_adapter = ANNAdapter(
            db=db,
            collection=collection,
            embedding_field=embedding_field,
        )
        if create_vector_index:
            self.ann_adapter.ensure_vector_index(n_lists=vector_index_n_lists)

        self._stats['embedding_field'] = self.embedding_field
        self._stats['similarity_threshold'] = self.similarity_threshold
        self._stats['limit_per_entity'] = self.limit_per_entity
        self._stats['blocking_field'] = self.blocking_field
        self._stats['ann_method'] = self.ann_adapter.method

    def check_embeddings_exist(self) -> Dict[str, Any]:
        """Return statistics about embedding coverage in the collection."""
        query = f"""
            LET total = COUNT(FOR doc IN {self.collection} RETURN 1)
            LET with_embeddings = COUNT(
                FOR doc IN {self.collection}
                FILTER doc.{self.embedding_field} != null
                RETURN 1
            )
            RETURN {{
                total: total,
                with_embeddings: with_embeddings,
                without_embeddings: total - with_embeddings,
                coverage_percent: with_embeddings / total * 100
            }}
        """
        return self.db.aql.execute(query).next()

    def generate_candidates(self) -> List[Dict[str, Any]]:
        """
        Generate candidate pairs via the native vector index (APPROX_NEAR_COSINE).

        Returns:
            List of candidate pairs:
            ``[{'doc1_key', 'doc2_key', 'similarity', 'method'}]``

        Raises:
            RuntimeError: If no embeddings exist in the collection.
            VectorSearchUnavailableError: If ArangoDB < 3.12 or no vector index.
        """
        start_time = time.time()

        embedding_stats = self.check_embeddings_exist()
        if embedding_stats['with_embeddings'] == 0:
            raise RuntimeError(
                f"No embeddings found in collection '{self.collection}'. "
                f"Use EmbeddingService.ensure_embeddings_exist() first."
            )
        if embedding_stats['coverage_percent'] < 100:
            self.logger.warning(
                "Only %.1f%% of documents have embeddings (%s/%s)",
                embedding_stats['coverage_percent'],
                embedding_stats['with_embeddings'], embedding_stats['total'],
            )

        self.logger.info(
            "Generating vector candidates (method=%s, threshold=%s, limit=%s)",
            self.ann_adapter.method, self.similarity_threshold, self.limit_per_entity,
        )

        # Native vector search only -- raises VectorSearchUnavailableError if the
        # deployment is < 3.12 or lacks a vector index (no brute-force fallback).
        pairs = self.ann_adapter.find_all_pairs(
            similarity_threshold=self.similarity_threshold,
            limit_per_entity=self.limit_per_entity,
            blocking_field=self.blocking_field,
            filters=self.filters,
        )
        pairs = self._normalize_pairs(pairs)

        execution_time = time.time() - start_time
        self._update_statistics(pairs, execution_time)
        self._stats['embedding_coverage_percent'] = embedding_stats['coverage_percent']
        self._stats['documents_with_embeddings'] = embedding_stats['with_embeddings']

        self.logger.info("Generated %d candidate pairs in %.2fs", len(pairs), execution_time)
        return pairs

    def ensure_vector_index(
        self,
        dimension: Optional[int] = None,
        n_lists: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create the native vector index on the embedding field (ArangoDB 3.12+)."""
        return self.ann_adapter.ensure_vector_index(dimension=dimension, n_lists=n_lists)

    def __repr__(self) -> str:
        return (
            f"VectorBlockingStrategy(collection='{self.collection}', "
            f"threshold={self.similarity_threshold}, "
            f"limit={self.limit_per_entity})"
        )
