"""
Hybrid blocking strategy combining BM25 and Levenshtein distance.

This strategy uses ArangoSearch BM25 for fast initial candidate generation,
then verifies with Levenshtein distance for accuracy. Best of both worlds:
- BM25: Fast fuzzy text search (400x faster than Levenshtein alone)
- Levenshtein: Accurate similarity verification

Use cases:
- Name matching with high accuracy requirements
- Large datasets where pure Levenshtein is too slow
- Text fields with typos or variations
- Company name deduplication
"""

from typing import List, Dict, Any, Optional
from arango.database import StandardDatabase
import time

from .base_strategy import BlockingStrategy
from ..utils.validation import validate_view_name, validate_field_name


class HybridBlockingStrategy(BlockingStrategy):
    """
    Hybrid BM25 + Levenshtein blocking strategy.
    
    This strategy combines the speed of BM25 with the accuracy of Levenshtein:
    1. Use BM25 for fast initial candidate ranking (fuzzy text matching)
    2. Apply Levenshtein distance for accurate similarity verification
    3. Return only pairs above threshold with detailed scores
    
    Performance: ~400x faster than Levenshtein-only for initial filtering
    Accuracy: Levenshtein threshold ensures high-quality matches
    
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
                            'name': {'analyzers': ['text_en']},
                            'address': {'analyzers': ['text_en']}
                        }
                    }
                }
            }
        )
        
        # Then use strategy:
        strategy = HybridBlockingStrategy(
            db=db,
            collection='companies',
            search_view='companies_search',
            search_fields={
                'name': 0.6,
                'address': 0.4
            },
            levenshtein_threshold=0.85,
            bm25_threshold=2.0,
            bm25_weight=0.2
        )
        pairs = strategy.generate_candidates()
        ```
    
    Performance: O(n log n) with BM25, then O(n) Levenshtein verification
    """
    
    def __init__(
        self,
        db: StandardDatabase,
        collection: str,
        search_view: str,
        search_fields: Dict[str, float],
        levenshtein_threshold: float = 0.85,
        bm25_threshold: float = 2.0,
        bm25_weight: float = 0.2,
        limit_per_entity: int = 20,
        blocking_field: Optional[str] = None,
        filters: Optional[Dict[str, Dict[str, Any]]] = None,
        analyzer: str = "text_en"
    ):
        """
        Initialize hybrid blocking strategy.
        
        Args:
            db: ArangoDB database connection
            collection: Source collection name
            search_view: ArangoSearch view name (must be created beforehand)
            search_fields: Fields to search with their weights in similarity computation.
                Example: {"company_name": 0.6, "address": 0.4}
                Weights will be normalized to sum to 1.0.
            levenshtein_threshold: Minimum Levenshtein similarity to include (0.0-1.0).
                Default 0.85 (strict). This is the FINAL quality gate.
            bm25_threshold: Minimum BM25 score to include. Higher values = stricter.
                Typical range: 1.0-5.0. Default 2.0.
            bm25_weight: Weight for BM25 in combined score (0.0-1.0).
                Default 0.2 (20% BM25, 80% Levenshtein).
                BM25 used for ranking, Levenshtein for quality.
            limit_per_entity: Maximum candidates per source entity.
                Prevents explosion with common names. Default 20.
            blocking_field: Optional field to constrain matches (e.g., "state").
                Only matches entities with same value in this field.
            filters: Optional filters per field (see base class for format)
            analyzer: ArangoSearch analyzer to use. Default "text_en".
                Must match analyzer configured in the view.
        
        Raises:
            ValueError: If required parameters are missing or invalid
        """
        super().__init__(db, collection, filters)
        
        # Validate inputs
        if not search_view:
            raise ValueError("search_view cannot be empty")
        if not search_fields:
            raise ValueError("search_fields cannot be empty")
        if not (0.0 <= levenshtein_threshold <= 1.0):
            raise ValueError("levenshtein_threshold must be between 0.0 and 1.0")
        if bm25_threshold <= 0:
            raise ValueError("bm25_threshold must be positive")
        if not (0.0 <= bm25_weight <= 1.0):
            raise ValueError("bm25_weight must be between 0.0 and 1.0")
        if limit_per_entity <= 0:
            raise ValueError("limit_per_entity must be positive")
        
        # Validate names for security (prevent AQL injection)
        self.search_view = validate_view_name(search_view)
        self.search_fields = {
            validate_field_name(field): weight
            for field, weight in search_fields.items()
        }
        self.search_fields = self._normalize_weights(self.search_fields)
        
        self.levenshtein_threshold = levenshtein_threshold
        self.bm25_threshold = bm25_threshold
        self.bm25_weight = bm25_weight
        self.levenshtein_weight = 1.0 - bm25_weight
        self.limit_per_entity = limit_per_entity
        self.blocking_field = validate_field_name(blocking_field) if blocking_field else None
        self.analyzer = analyzer
    
    def generate_candidates(self) -> List[Dict[str, Any]]:
        """
        Generate candidate pairs using hybrid BM25 + Levenshtein matching.
        
        Process:
        1. Apply filters to source documents
        2. For each document, search using BM25 on ArangoSearch
        3. Compute detailed Levenshtein similarity for each field
        4. Combine BM25 (for ranking) with Levenshtein (for quality)
        5. Filter by Levenshtein threshold (final quality gate)
        6. Optionally constrain by blocking field (e.g., same state)
        7. Limit candidates per entity
        8. Return candidate pairs with detailed scores
        
        Returns:
            List of candidate pairs:
            [
                {
                    "doc1_key": "123",
                    "doc2_key": "456",
                    "levenshtein_score": 0.92,
                    "bm25_score": 5.2,
                    "combined_score": 4.89,
                    "field_scores": {
                        "company_name": 0.95,
                        "address": 0.87
                    },
                    "search_fields": ["company_name", "address"],
                    "blocking_field_value": "CA",  # If blocking_field specified
                    "method": "hybrid_blocking"
                },
                ...
            ]
        
        Performance: O(n log n) - faster than pure Levenshtein, accurate with verification
        """
        start_time = time.time()
        
        # Build the AQL query
        query = self._build_hybrid_query()
        
        # Execute query with bind variables
        bind_vars = {
            'bm25_threshold': self.bm25_threshold,
            'levenshtein_threshold': self.levenshtein_threshold,
            'limit_per_entity': self.limit_per_entity,
            'bm25_weight': self.bm25_weight,
            'levenshtein_weight': self.levenshtein_weight
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
            'search_fields': list(self.search_fields.keys()),
            'levenshtein_threshold': self.levenshtein_threshold,
            'bm25_threshold': self.bm25_threshold,
            'bm25_weight': self.bm25_weight,
            'limit_per_entity': self.limit_per_entity,
            'blocking_field': self.blocking_field,
            'avg_levenshtein_score': self._calculate_avg_score(normalized_pairs, 'levenshtein_score'),
            'avg_bm25_score': self._calculate_avg_score(normalized_pairs, 'bm25_score'),
            'avg_combined_score': self._calculate_avg_score(normalized_pairs, 'combined_score')
        })
        
        return normalized_pairs
    
    def _build_hybrid_query(self) -> str:
        """
        Build the AQL query for hybrid BM25 + Levenshtein blocking.

        The query uses a per-entity subquery so that
        ``SORT combined_score DESC`` and ``LIMIT @limit_per_entity``
        apply *per source document* rather than globally. Earlier
        versions placed the SORT and LIMIT at the outer level of a
        nested ``FOR``; in AQL that ordered/capped the flattened result
        stream across all (d1, d2) iterations, so the strategy returned
        only the global top-K combined-score pairs rather than the
        intended top-K per source entity.

        Returns:
            AQL query string
        """
        query_parts = [f"FOR d1 IN {self.collection}"]

        if self.filters:
            for field_name, field_filters in self.filters.items():
                if field_name in self.search_fields:
                    if field_filters.get('not_null'):
                        query_parts.append(f"    FILTER d1.{field_name} != null")
                    if 'min_length' in field_filters:
                        min_len = field_filters['min_length']
                        query_parts.append(f"    FILTER LENGTH(d1.{field_name}) > {min_len}")

            if self.blocking_field and self.blocking_field in self.filters:
                blocking_filters = self.filters[self.blocking_field]
                if blocking_filters.get('not_null'):
                    query_parts.append(f"    FILTER d1.{self.blocking_field} != null")

        primary_field = list(self.search_fields.keys())[0]

        # Per-entity subquery: candidates for this specific d1.
        sub_parts = [
            f"    LET candidates = (",
            f"        FOR d2 IN {self.search_view}",
            f"            SEARCH ANALYZER(",
            f"                PHRASE(d2.{primary_field}, d1.{primary_field}, \"{self.analyzer}\"),",
            f"                \"{self.analyzer}\"",
            f"            )",
            f"            LET bm25_score = BM25(d2)",
            f"            FILTER bm25_score > @bm25_threshold",
        ]
        if self.blocking_field:
            sub_parts.append(
                f"            FILTER d2.{self.blocking_field} == d1.{self.blocking_field}"
            )
        sub_parts.append("            FILTER d1._key < d2._key")

        levenshtein_parts = []
        field_scores_parts = []
        for field, weight in self.search_fields.items():
            sub_parts.append(f"            LET val1_{field} = UPPER(TRIM(d1.{field} || \"\"))")
            sub_parts.append(f"            LET val2_{field} = UPPER(TRIM(d2.{field} || \"\"))")
            sub_parts.append(
                f"            LET lev_{field} = LEVENSHTEIN_DISTANCE(val1_{field}, val2_{field})"
            )
            sub_parts.append(
                f"            LET max_len_{field} = MAX([LENGTH(val1_{field}), LENGTH(val2_{field})])"
            )
            sub_parts.append(
                f"            LET score_{field} = max_len_{field} > 0 ? "
                f"(1.0 - lev_{field} / max_len_{field}) : 0"
            )
            levenshtein_parts.append(f"(score_{field} * {weight})")
            field_scores_parts.append(f'"{field}": score_{field}')

        sub_parts.append(
            f"            LET levenshtein_score = {' + '.join(levenshtein_parts)}"
        )
        sub_parts.append(
            "            LET combined_score = (bm25_score * @bm25_weight) "
            "+ (levenshtein_score * @levenshtein_weight)"
        )
        sub_parts.append(
            f"            LET field_scores = {{{', '.join(field_scores_parts)}}}"
        )
        sub_parts.append("            FILTER levenshtein_score >= @levenshtein_threshold")
        sub_parts.append("            SORT combined_score DESC")
        sub_parts.append("            LIMIT @limit_per_entity")

        sub_return_fields = [
            "doc2_key: d2._key",
            "levenshtein_score: levenshtein_score",
            "bm25_score: bm25_score",
            "combined_score: combined_score",
            "field_scores: field_scores",
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
            "levenshtein_score: c.levenshtein_score",
            "bm25_score: c.bm25_score",
            "combined_score: c.combined_score",
            "field_scores: c.field_scores",
            f"search_fields: {list(self.search_fields.keys())}",
            'method: "hybrid_blocking"',
        ]
        if self.blocking_field:
            return_fields.append("blocking_field_value: c.blocking_field_value")

        query_parts.append(
            "        RETURN {\n            "
            + ",\n            ".join(return_fields)
            + "\n        }"
        )

        return "\n".join(query_parts)
    
    def _calculate_avg_score(self, pairs: List[Dict[str, Any]], score_field: str) -> Optional[float]:
        """
        Calculate average score for a given field from pairs.
        
        Args:
            pairs: List of candidate pairs
            score_field: Field name to average (e.g., 'levenshtein_score')
        
        Returns:
            Average score or None if no pairs
        """
        if not pairs:
            return None
        
        scores = [p.get(score_field, 0) for p in pairs if score_field in p]
        if not scores:
            return None
        
        return round(sum(scores) / len(scores), 4)
    
    def _normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """
        Normalize weights to sum to 1.0.
        
        Args:
            weights: Original weights
        
        Returns:
            Normalized weights
        """
        total = sum(weights.values())
        if total == 0:
            raise ValueError("Field weights cannot all be zero")
        
        return {field: weight / total for field, weight in weights.items()}
    
    def __repr__(self) -> str:
        """String representation of the strategy."""
        fields_str = ', '.join(self.search_fields.keys())
        return (
            f"HybridBlockingStrategy("
            f"collection='{self.collection}', "
            f"search_view='{self.search_view}', "
            f"fields=[{fields_str}], "
            f"lev_threshold={self.levenshtein_threshold}, "
            f"bm25_threshold={self.bm25_threshold})"
        )

