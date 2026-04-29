"""
BM25-based fuzzy blocking strategy using ArangoSearch.

This strategy uses ArangoDB's BM25 scoring for fast text similarity matching.
Much faster than Levenshtein for initial candidate generation, particularly
effective for name matching and fuzzy text search.
"""

from typing import List, Dict, Any, Optional
from arango.database import StandardDatabase
import time

from .base_strategy import BlockingStrategy
from ..utils.validation import validate_view_name, validate_field_name


class BM25BlockingStrategy(BlockingStrategy):
    """
    BM25-based fuzzy blocking using ArangoSearch.
    
    Uses ArangoDB's BM25 scoring for fast text similarity matching. This is
    particularly effective for:
    - Name matching (company names, person names)
    - Fuzzy text search
    - Initial candidate generation before detailed similarity scoring
    
    Key benefits:
    - 400x faster than Levenshtein for initial filtering
    - Leverages ArangoSearch full-text capabilities
    - Configurable BM25 threshold
    - Optional blocking field for geographic/categorical constraints
    
    Requirements:
    - ArangoSearch view must be created on the collection
    - View must index the search field with appropriate analyzer
    
    Example:
        ```python
        # First create view (one-time setup):
        db.create_view(
            name='companies_search',
            view_type='arangosearch',
            properties={
                'links': {
                    'companies': {
                        'fields': {
                            'name': {'analyzers': ['text_en']}
                        }
                    }
                }
            }
        )
        
        # Then use strategy:
        strategy = BM25BlockingStrategy(
            db=db,
            collection='companies',
            search_view='companies_search',
            search_field='name',
            bm25_threshold=2.0,
            limit_per_entity=20,
            blocking_field='state'
        )
        pairs = strategy.generate_candidates()
        ```
    
    Performance: O(n log n) where n = number of documents
    """
    
    def __init__(
        self,
        db: StandardDatabase,
        collection: str,
        search_view: str,
        search_field: str,
        bm25_threshold: float = 2.0,
        limit_per_entity: int = 20,
        blocking_field: Optional[str] = None,
        filters: Optional[Dict[str, Dict[str, Any]]] = None,
        analyzer: str = "text_en"
    ):
        """
        Initialize BM25-based blocking strategy.
        
        Args:
            db: ArangoDB database connection
            collection: Source collection name
            search_view: ArangoSearch view name (must be created beforehand)
            search_field: Field to perform BM25 search on (e.g., "company_name")
            bm25_threshold: Minimum BM25 score to include. Higher values = stricter
                matching. Typical range: 1.0-5.0. Default 2.0.
            limit_per_entity: Maximum candidates per source entity. Prevents
                explosion with common names. Default 20.
            blocking_field: Optional field to constrain matches (e.g., "state").
                Only matches entities with same value in this field.
            filters: Optional filters per field (see base class for format)
            analyzer: ArangoSearch analyzer to use. Default "text_en".
                Must match analyzer configured in the view.
        
        Raises:
            ValueError: If required parameters are missing or invalid
        """
        super().__init__(db, collection, filters)
        
        # Validate inputs first
        if not search_view:
            raise ValueError("search_view cannot be empty")
        if not search_field:
            raise ValueError("search_field cannot be empty")
        if bm25_threshold <= 0:
            raise ValueError("bm25_threshold must be positive")
        if limit_per_entity <= 0:
            raise ValueError("limit_per_entity must be positive")
        
        # Validate names for security (prevent AQL injection)
        self.search_view = validate_view_name(search_view)
        self.search_field = validate_field_name(search_field)
        self.bm25_threshold = bm25_threshold
        self.limit_per_entity = limit_per_entity
        self.blocking_field = validate_field_name(blocking_field) if blocking_field else None
        self.analyzer = analyzer
    
    def generate_candidates(self) -> List[Dict[str, Any]]:
        """
        Generate candidate pairs using BM25 fuzzy matching.
        
        Process:
        1. Apply filters to source documents
        2. For each document, search for similar documents using BM25
        3. Filter by BM25 threshold
        4. Optionally constrain by blocking field (e.g., same state)
        5. Limit candidates per entity
        6. Return candidate pairs with BM25 scores
        
        Returns:
            List of candidate pairs:
            [
                {
                    "doc1_key": "123",
                    "doc2_key": "456",
                    "bm25_score": 5.2,
                    "search_field": "company_name",
                    "blocking_field_value": "CA",  # If blocking_field specified
                    "method": "bm25_blocking"
                },
                ...
            ]
        
        Performance: O(n log n) - faster than exact matching for fuzzy text
        """
        start_time = time.time()
        
        # Build the AQL query
        query = self._build_bm25_query()
        
        # Execute query with bind variables
        bind_vars = {
            'bm25_threshold': self.bm25_threshold,
            'limit_per_entity': self.limit_per_entity
        }
        
        cursor = self.db.aql.execute(query, bind_vars=bind_vars)
        pairs = list(cursor)
        
        # Normalize pairs
        normalized_pairs = self._normalize_pairs(pairs)
        
        # Update statistics
        execution_time = time.time() - start_time
        self._update_statistics(normalized_pairs, execution_time)
        
        # Add additional stats
        self._stats.update({
            'search_view': self.search_view,
            'search_field': self.search_field,
            'bm25_threshold': self.bm25_threshold,
            'limit_per_entity': self.limit_per_entity,
            'blocking_field': self.blocking_field,
            'avg_bm25_score': self._calculate_avg_bm25_score(normalized_pairs),
            'max_bm25_score': self._calculate_max_bm25_score(normalized_pairs)
        })
        
        return normalized_pairs
    
    def _build_bm25_query(self) -> str:
        """
        Build the AQL query for BM25-based blocking.

        The query uses a per-entity subquery so that ``LIMIT
        @limit_per_entity`` applies *per source document* rather than
        globally. Earlier versions placed ``LIMIT`` at the outer level of
        a nested ``FOR``; in AQL that limits the flattened result stream
        across all (d1, d2) iterations, so the strategy returned exactly
        ``limit_per_entity`` pairs total regardless of collection size
        rather than the intended top-K candidates per source entity.

        Returns:
            AQL query string
        """
        # Outer loop: iterate source documents and apply d1-level filters.
        query_parts = [f"FOR d1 IN {self.collection}"]

        if self.filters:
            search_field_filters = self.filters.get(self.search_field, {})
            if search_field_filters:
                if search_field_filters.get('not_null'):
                    query_parts.append(f"    FILTER d1.{self.search_field} != null")
                if 'min_length' in search_field_filters:
                    min_len = search_field_filters['min_length']
                    query_parts.append(f"    FILTER LENGTH(d1.{self.search_field}) > {min_len}")

            if self.blocking_field and self.blocking_field in self.filters:
                blocking_filters = self.filters[self.blocking_field]
                if blocking_filters.get('not_null'):
                    query_parts.append(f"    FILTER d1.{self.blocking_field} != null")

        # Per-entity subquery: candidates for this specific d1. The
        # `LIMIT @limit_per_entity` lives inside this subquery, so it
        # caps results per source document. `SORT bm25_score DESC` makes
        # the limit pick the highest-scoring matches.
        sub_parts = [
            f"    LET candidates = (",
            f"        FOR d2 IN {self.search_view}",
            f"            SEARCH ANALYZER(",
            f"                PHRASE(d2.{self.search_field}, d1.{self.search_field}, \"{self.analyzer}\"),",
            f"                \"{self.analyzer}\"",
            f"            )",
            f"            LET bm25_score = BM25(d2)",
            f"            FILTER bm25_score > @bm25_threshold",
        ]
        if self.blocking_field:
            sub_parts.append(
                f"            FILTER d2.{self.blocking_field} == d1.{self.blocking_field}"
            )
        sub_parts.extend([
            f"            FILTER d1._key < d2._key",
            f"            SORT bm25_score DESC",
            f"            LIMIT @limit_per_entity",
        ])

        sub_return_fields = [
            "doc2_key: d2._key",
            "bm25_score: bm25_score",
        ]
        if self.blocking_field:
            sub_return_fields.append(f"blocking_field_value: d2.{self.blocking_field}")
        sub_parts.append(
            "            RETURN {\n                "
            + ",\n                ".join(sub_return_fields)
            + "\n            }"
        )
        sub_parts.append("    )")
        query_parts.extend(sub_parts)

        # Outer return: flatten per-entity candidates with d1 metadata.
        query_parts.append("    FOR c IN candidates")
        return_fields = [
            "doc1_key: d1._key",
            "doc2_key: c.doc2_key",
            "bm25_score: c.bm25_score",
            f'search_field: "{self.search_field}"',
            'method: "bm25_blocking"',
        ]
        if self.blocking_field:
            return_fields.append("blocking_field_value: c.blocking_field_value")

        query_parts.append(
            "        RETURN {\n            "
            + ",\n            ".join(return_fields)
            + "\n        }"
        )

        return "\n".join(query_parts)
    
    def _calculate_avg_bm25_score(self, pairs: List[Dict[str, Any]]) -> Optional[float]:
        """
        Calculate average BM25 score from pairs.
        
        Args:
            pairs: List of candidate pairs
        
        Returns:
            Average BM25 score or None if no pairs
        """
        if not pairs:
            return None
        
        scores = [p.get('bm25_score', 0) for p in pairs if 'bm25_score' in p]
        if not scores:
            return None
        
        return round(sum(scores) / len(scores), 2)
    
    def _calculate_max_bm25_score(self, pairs: List[Dict[str, Any]]) -> Optional[float]:
        """
        Calculate maximum BM25 score from pairs.
        
        Args:
            pairs: List of candidate pairs
        
        Returns:
            Maximum BM25 score or None if no pairs
        """
        if not pairs:
            return None
        
        scores = [p.get('bm25_score', 0) for p in pairs if 'bm25_score' in p]
        if not scores:
            return None
        
        return round(max(scores), 2)
    
    def __repr__(self) -> str:
        """String representation of the strategy."""
        return (f"BM25BlockingStrategy("
                f"collection='{self.collection}', "
                f"search_view='{self.search_view}', "
                f"search_field='{self.search_field}', "
                f"threshold={self.bm25_threshold})")

