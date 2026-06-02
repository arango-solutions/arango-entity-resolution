"""
Cross-collection entity matching service.

This service matches entities between two different collections using configurable
blocking strategies, similarity computation, and confidence scoring. Perfect for:
- Linking registrations to parent companies
- Matching customers across systems
- Deduplicating entities from different sources

Key features:
- Match entities between any two collections
- Configurable blocking strategies (state, city, ZIP, custom fields)
- Hybrid BM25 + Levenshtein scoring
- Detailed confidence metrics with per-field scores
- Batch processing with offset-based pagination
- Resume capability for long-running jobs
- Inferred edge tracking
"""

from typing import List, Dict, Any, Optional, Callable
from arango.database import StandardDatabase
from arango.collection import EdgeCollection
import time
from datetime import datetime
import logging

from ..utils.validation import validate_collection_name, validate_view_name, validate_field_name


class CrossCollectionMatchingService:
    """
    Match entities between two different collections.
    
    This service enables entity resolution across collection boundaries,
    such as matching registrations to companies, customers to accounts,
    or products across catalogs.
    
    Features:
    - Flexible blocking strategies (state, city, ZIP, custom AQL)
    - Hybrid scoring (BM25 for speed, Levenshtein for accuracy)
    - Configurable field weights and similarity thresholds
    - Batch processing with resume capability
    - Detailed match metadata (confidence, per-field scores)
    - Inferred edge marking for tracking provenance
    
    Example:
        ```python
        service = CrossCollectionMatchingService(
            db=db,
            source_collection="registrations",
            target_collection="companies",
            edge_collection="hasCompany",
            search_view="companies_search"
        )
        
        # Configure matching
        service.configure_matching(
            source_fields={
                "name": "company_name",
                "address": "address_line1",
                "city": "city"
            },
            target_fields={
                "name": "legal_name",
                "address": "street_address",
                "city": "location_city"
            },
            field_weights={
                "name": 0.6,
                "address": 0.3,
                "city": 0.1
            },
            blocking_fields=["state"]
        )
        
        # Run matching
        results = service.match_entities(
            threshold=0.85,
            batch_size=100,
            limit=None  # Process all
        )
        
        print(f"Created {results['edges_created']} matches")
        ```
    """
    
    def __init__(
        self,
        db: StandardDatabase,
        source_collection: str,
        target_collection: str,
        edge_collection: str,
        search_view: Optional[str] = None,
        auto_create_edge_collection: bool = True
    ):
        """
        Initialize cross-collection matching service.
        
        Args:
            db: ArangoDB database connection
            source_collection: Source collection name (e.g., "registrations")
            target_collection: Target collection name (e.g., "companies")
            edge_collection: Edge collection to store matches (e.g., "hasCompany")
            search_view: Optional ArangoSearch view for BM25 fuzzy matching.
                If None, will use only Levenshtein distance (slower but accurate).
            auto_create_edge_collection: Create edge collection if it doesn't exist.
                Default True.
        """
        self.db = db
        self.source_collection_name = validate_collection_name(source_collection)
        self.target_collection_name = validate_collection_name(target_collection)
        self.edge_collection_name = validate_collection_name(edge_collection)
        self.search_view = validate_view_name(search_view) if search_view is not None else None
        
        # Initialize logger
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Get collections
        self.source_collection = db.collection(self.source_collection_name)
        self.target_collection = db.collection(self.target_collection_name)
        
        # Get or create edge collection
        if auto_create_edge_collection and not db.has_collection(self.edge_collection_name):
            self.edge_collection: EdgeCollection = db.create_collection(self.edge_collection_name, edge=True)
        else:
            self.edge_collection = db.collection(self.edge_collection_name)
        
        # Configuration
        self.source_fields = {}
        self.target_fields = {}
        self.field_weights = {}
        self.blocking_fields = []
        self.blocking_strategy = None
        self.custom_filters = {}
        
        # Statistics
        self._stats = {
            'edges_created': 0,
            'candidates_evaluated': 0,
            'batches_processed': 0,
            'source_records_processed': 0,
            'execution_time_seconds': 0.0,
            'timestamp': None
        }
    
    def configure_matching(
        self,
        source_fields: Dict[str, str],
        target_fields: Dict[str, str],
        field_weights: Dict[str, float],
        blocking_fields: Optional[List[str]] = None,
        blocking_strategy: Optional[str] = None,
        custom_filters: Optional[Dict[str, Any]] = None
    ):
        """
        Configure field mappings and matching strategy.
        
        Args:
            source_fields: Mapping of logical field names to source collection fields.
                Example: {"name": "BR_Name", "address": "ADDRESS_LINE_1"}
            target_fields: Mapping of logical field names to target collection fields.
                Example: {"name": "DUNS_NAME", "address": "ADDR_PRIMARY_STREET"}
            field_weights: Weights for each logical field in similarity computation.
                Example: {"name": 0.6, "address": 0.3, "city": 0.1}
                Weights will be normalized to sum to 1.0.
            blocking_fields: Fields to use for blocking (reduces comparisons).
                Example: ["state"] or ["city", "state"]
                These should be logical field names (will look up in source/target_fields).
            blocking_strategy: Strategy for blocking:
                - "exact": Exact match on blocking fields (fast)
                - "city": City-based blocking (geographic)
                - "state": State-based blocking (geographic)
                - "zip_range": ZIP code range blocking
                - None: No blocking (compares all pairs - slow!)
            custom_filters: Optional custom filters for source/target records.
                Example: {
                    "source": {"state": {"not_null": True}},
                    "target": {"state": {"equals": "SD"}}
                }
        """
        self.source_fields = source_fields
        self.target_fields = target_fields
        self.field_weights = self._normalize_weights(field_weights)
        self.blocking_fields = blocking_fields or []
        self.blocking_strategy = blocking_strategy or "exact"
        self.custom_filters = custom_filters or {}
        
        # Validate any identifiers that will be interpolated into AQL.
        for logical_field, source_field in self.source_fields.items():
            validate_field_name(logical_field, allow_nested=False)
            validate_field_name(source_field, allow_nested=True)
        for logical_field, target_field in self.target_fields.items():
            validate_field_name(logical_field, allow_nested=False)
            validate_field_name(target_field, allow_nested=True)
        for logical_field in self.field_weights.keys():
            validate_field_name(logical_field, allow_nested=False)
        for logical_field in self.blocking_fields:
            validate_field_name(logical_field, allow_nested=False)

        # Validate configuration
        if set(source_fields.keys()) != set(target_fields.keys()):
            raise ValueError("source_fields and target_fields must have same logical field names")
        
        if set(field_weights.keys()) != set(source_fields.keys()):
            raise ValueError("field_weights must cover all fields in source_fields")
    
    def match_entities(
        self,
        threshold: float = 0.85,
        batch_size: int = 100,
        limit: Optional[int] = None,
        offset: int = 0,
        use_bm25: bool = True,
        bm25_weight: float = 0.2,
        mark_as_inferred: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        max_runtime_seconds: float = 300.0,
        deterministic_tiebreak: bool = True,
    ) -> Dict[str, Any]:
        """
        Match entities between source and target collections.
        
        Args:
            threshold: Minimum similarity score to create edge (0.0-1.0). Default 0.85.
            batch_size: Source records to process per batch. Default 100.
            limit: Maximum source records to process (for testing). None = all.
            offset: Starting offset for resuming interrupted jobs. Default 0.
            use_bm25: Use BM25 for initial candidate ranking if search_view available.
                Default True. Falls back to Levenshtein if no view.
            bm25_weight: Weight for BM25 score in hybrid scoring (0.0-1.0).
                Default 0.2 (80% Levenshtein, 20% BM25).
            mark_as_inferred: Mark edges with "inferred: true" to distinguish from
                direct/explicit edges. Default True.
            progress_callback: Optional callback(current, total) for progress updates.
            max_runtime_seconds: Max runtime allowed per batch AQL query.
            deterministic_tiebreak: Add deterministic secondary sort key for stable
                winner selection when scores tie.
        
        Returns:
            Results dictionary:
            {
                "edges_created": 1234,
                "candidates_evaluated": 5678,
                "batches_processed": 57,
                "source_records_processed": 5700,
                "execution_time_seconds": 123.45,
                "timestamp": "2025-12-02T10:30:00"
            }
        """
        if not self.source_fields or not self.target_fields:
            raise ValueError("Must call configure_matching() before match_entities()")
        
        start_time = time.time()
        edges_created = 0
        candidates_evaluated = 0
        batches_processed = 0
        source_records_processed = 0
        
        # Count total source records (for progress tracking)
        total_query = self._build_count_query()
        cursor = self.db.aql.execute(
            total_query, bind_vars=self._collection_bind_vars()
        )
        result = list(cursor)
        total_records = result[0] if result else 0
        
        self.logger.info(f"Starting cross-collection matching: {total_records:,} source records to process")
        
        # Process in batches
        current_offset = offset
        
        while True:
            # Check limit
            if limit and source_records_processed >= limit:
                self.logger.info(f"Reached limit of {limit} records")
                break
            
            # Build and execute matching query for this batch
            batch_query = self._build_matching_query(
                batch_size=batch_size,
                offset=current_offset,
                threshold=threshold,
                use_bm25=use_bm25 and self.search_view is not None,
                    bm25_weight=bm25_weight,
                    deterministic_tiebreak=deterministic_tiebreak,
            )
            
            try:
                bind_vars = self._build_bind_vars(threshold, batch_size, current_offset)
                cursor = self.db.aql.execute(
                    batch_query,
                    bind_vars=bind_vars,
                    max_runtime=max(1.0, float(max_runtime_seconds)),
                )
                batch_results = list(cursor)
                
                if not batch_results:
                    self.logger.info(f"No more results at offset {current_offset}")
                    break
                
                # Create edges for matches
                batch_edges_created = self._create_edges_from_matches(
                    batch_results,
                    mark_as_inferred=mark_as_inferred
                )
                
                edges_created += batch_edges_created
                candidates_evaluated += len(batch_results)
                source_records_processed += min(batch_size, total_records - current_offset)
                batches_processed += 1
                current_offset += batch_size
                
                # Progress callback
                if progress_callback:
                    progress_callback(source_records_processed, total_records)
                
                # Log progress
                if batches_processed % 10 == 0:
                    self.logger.info(
                        f"Batch {batches_processed}: processed {source_records_processed:,}/{total_records:,} "
                        f"records, created {edges_created:,} edges"
                    )
                
            except Exception as e:
                self.logger.error(f"Error processing batch at offset {current_offset}: {e}", exc_info=True)
                break
        
        # Final progress callback
        if progress_callback:
            progress_callback(source_records_processed, total_records)
        
        # Update statistics
        execution_time = time.time() - start_time
        self._stats.update({
            'edges_created': edges_created,
            'candidates_evaluated': candidates_evaluated,
            'batches_processed': batches_processed,
            'source_records_processed': source_records_processed,
            'execution_time_seconds': round(execution_time, 2),
            'timestamp': datetime.now().isoformat()
        })
        
        self.logger.info(
            f"Matching complete: {edges_created:,} edges created from {source_records_processed:,} "
            f"source records in {execution_time:.2f}s"
        )
        
        return self._stats.copy()
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get matching statistics.
        
        Returns:
            Statistics dictionary with counts and timing
        """
        return self._stats.copy()
    
    def clear_inferred_edges(self, older_than: Optional[str] = None) -> int:
        """
        Clear inferred edges created by this service.
        
        Useful for re-running matching with different parameters.
        
        Args:
            older_than: Only clear edges older than this ISO timestamp.
                If None, clears all inferred edges.
        
        Returns:
            Number of edges removed
        """
        query_parts = ["FOR e IN @@edge_collection"]
        query_parts.append("    FILTER e.inferred == true")
        bind_vars: Dict[str, Any] = {"@edge_collection": self.edge_collection_name}
        
        if older_than:
            query_parts.append("    FILTER e.created_at < @older_than")
            bind_vars["older_than"] = older_than
        
        query_parts.append("    REMOVE e IN @@edge_collection")
        query_parts.append("    RETURN OLD")
        
        query = "\n".join(query_parts)
        
        cursor = self.db.aql.execute(
            query,
            bind_vars=bind_vars,
        )
        removed = list(cursor)
        
        self.logger.info(f"Removed {len(removed)} inferred edges")
        
        return len(removed)
    
    def _build_count_query(self) -> str:
        """Build query to count source records to process."""
        query_parts = ["FOR s IN @@source_collection"]
        
        # Add filters
        if 'source' in self.custom_filters:
            for condition in self._build_filter_conditions('s', self.custom_filters['source']):
                query_parts.append(f"    FILTER {condition}")
        
        # Check if already has edge
        query_parts.append("""    FILTER s._id NOT IN (
            FOR e IN @@edge_collection
            FILTER e._to == s._id
            LIMIT 1
            RETURN e._to
        )""")
        
        query_parts.append("    COLLECT WITH COUNT INTO cnt")
        query_parts.append("    RETURN cnt")
        
        return "\n".join(query_parts)
    
    def _build_matching_query(
        self,
        batch_size: int,
        offset: int,
        threshold: float,
        use_bm25: bool,
        bm25_weight: float,
        deterministic_tiebreak: bool = True,
    ) -> str:
        """
        Build AQL query for matching entities in a batch.
        
        The query structure:
        1. Get batch of unmatched source records
        2. For each source record, find candidate targets (using blocking)
        3. Compute similarity scores (BM25 + Levenshtein)
        4. Return matches above threshold
        """
        query_parts = ["FOR s IN @@source_collection"]
        
        # Add source filters
        if 'source' in self.custom_filters:
            for condition in self._build_filter_conditions('s', self.custom_filters['source']):
                query_parts.append(f"    FILTER {condition}")
        
        # Check if already has edge (skip already matched)
        query_parts.append("""    FILTER s._id NOT IN (
            FOR e IN @@edge_collection
            FILTER e._to == s._id
            LIMIT 1
            RETURN e._to
        )""")
        
        query_parts.append("    LIMIT @offset, @batch_size")
        
        # Candidate generation with blocking
        if use_bm25 and self.search_view:
            query_parts.extend(self._build_bm25_candidates(deterministic_tiebreak=deterministic_tiebreak))
        else:
            query_parts.extend(self._build_levenshtein_candidates(deterministic_tiebreak=deterministic_tiebreak))
        
        return "\n".join(query_parts)
    
    def _build_bm25_candidates(self, deterministic_tiebreak: bool = True) -> List[str]:
        """Build candidate generation using BM25 + Levenshtein verification."""
        lines = []
        lines.append("    LET candidates = (")
        lines.append("        FOR t IN @@search_view")
        lines.append("            SEARCH")
        
        # Add blocking conditions
        blocking_conditions = []
        for blocking_field in self.blocking_fields:
            if blocking_field in self.source_fields:
                source_field = self.source_fields[blocking_field]
                target_field = self.target_fields[blocking_field]
                blocking_conditions.append(
                    f'ANALYZER(t.{target_field} == s.{source_field}, "identity")'
                )
        
        if blocking_conditions:
            lines.append("                " + "\n                AND ".join(blocking_conditions))
        
        # BM25 scoring
        lines.append("            LET bm25_score = BM25(t)")
        
        # Levenshtein verification
        lines.extend(self._build_similarity_computation('s', 't'))
        
        lines.append("            FILTER lev_score >= @threshold")
        if deterministic_tiebreak:
            lines.append("            SORT total_score DESC, t._key ASC")
        else:
            lines.append("            SORT total_score DESC")
        lines.append("            LIMIT 1")
        lines.append("            RETURN {")
        lines.append("                target: t,")
        lines.append("                score: lev_score,")
        lines.append("                bm25_score: bm25_score,")
        lines.append("                field_scores: field_scores")
        lines.append("            }")
        lines.append("    )")
        
        # Return best match
        lines.append("    LET best_match = LENGTH(candidates) > 0 ? candidates[0] : null")
        lines.append("    FILTER best_match != null")
        lines.append("    RETURN {")
        lines.append("        source_key: s._key,")
        lines.append("        target_key: best_match.target._key,")
        lines.append("        confidence: best_match.score,")
        lines.append("        bm25_score: best_match.bm25_score,")
        lines.append("        field_scores: best_match.field_scores")
        lines.append("    }")
        
        return lines
    
    def _build_levenshtein_candidates(self, deterministic_tiebreak: bool = True) -> List[str]:
        """Build candidate generation using only Levenshtein distance."""
        lines = []
        lines.append("    LET candidates = (")
        lines.append("        FOR t IN @@target_collection")
        
        # Add target filters
        if 'target' in self.custom_filters:
            for condition in self._build_filter_conditions('t', self.custom_filters['target']):
                lines.append(f"            FILTER {condition}")
        
        # Add blocking conditions
        for blocking_field in self.blocking_fields:
            if blocking_field in self.source_fields:
                source_field = self.source_fields[blocking_field]
                target_field = self.target_fields[blocking_field]
                lines.append(f"            FILTER t.{target_field} == s.{source_field}")
        
        # Similarity computation
        lines.extend(self._build_similarity_computation('s', 't', indent=12))
        
        lines.append("            FILTER lev_score >= @threshold")
        if deterministic_tiebreak:
            lines.append("            SORT lev_score DESC, t._key ASC")
        else:
            lines.append("            SORT lev_score DESC")
        lines.append("            LIMIT 1")
        lines.append("            RETURN {")
        lines.append("                target: t,")
        lines.append("                score: lev_score,")
        lines.append("                field_scores: field_scores")
        lines.append("            }")
        lines.append("    )")
        
        # Return best match
        lines.append("    LET best_match = LENGTH(candidates) > 0 ? candidates[0] : null")
        lines.append("    FILTER best_match != null")
        lines.append("    RETURN {")
        lines.append("        source_key: s._key,")
        lines.append("        target_key: best_match.target._key,")
        lines.append("        confidence: best_match.score,")
        lines.append("        field_scores: best_match.field_scores")
        lines.append("    }")
        
        return lines
    
    def _build_similarity_computation(
        self,
        source_var: str,
        target_var: str,
        indent: int = 12
    ) -> List[str]:
        """Build AQL code for computing field-level similarities."""
        lines = []
        indent_str = " " * indent
        
        # Compute similarity for each field
        field_scores = []
        weighted_sum_parts = []
        
        for logical_field, weight in self.field_weights.items():
            source_field = self.source_fields[logical_field]
            target_field = self.target_fields[logical_field]
            
            field_var = f"{logical_field}_score"
            field_scores.append(field_var)
            
            lines.append(f"{indent_str}LET val_{logical_field}_s = UPPER(TRIM({source_var}.{source_field} || \"\"))")
            lines.append(f"{indent_str}LET val_{logical_field}_t = UPPER(TRIM({target_var}.{target_field} || \"\"))")
            lines.append(
                f"{indent_str}LET {logical_field}_lev = "
                f"LEVENSHTEIN_DISTANCE(val_{logical_field}_s, val_{logical_field}_t)"
            )
            lines.append(
                f"{indent_str}LET {logical_field}_max_len = "
                f"MAX([LENGTH(val_{logical_field}_s), LENGTH(val_{logical_field}_t)])"
            )
            lines.append(
                f"{indent_str}LET {field_var} = "
                f"{logical_field}_max_len > 0 ? (1.0 - {logical_field}_lev / {logical_field}_max_len) : 0"
            )
            
            weighted_sum_parts.append(f"({field_var} * {weight})")
        
        # Compute weighted average
        lines.append(f"{indent_str}LET lev_score = {' + '.join(weighted_sum_parts)}")
        
        # Build field_scores object
        field_scores_obj = ", ".join([f'"{f}": {f}_score' for f in self.field_weights.keys()])
        lines.append(f"{indent_str}LET field_scores = {{{field_scores_obj}}}")
        
        # Combined score (if BM25 available, it will be added later)
        lines.append(f"{indent_str}LET total_score = lev_score")
        
        return lines
    
    def _build_filter_conditions(self, var_name: str, filters: Dict[str, Any]) -> List[str]:
        """Build AQL filter conditions from filter specification."""
        conditions = []
        
        for field, filter_spec in filters.items():
            if not isinstance(filter_spec, dict):
                continue
            
            safe_field = validate_field_name(field, allow_nested=True)
            field_ref = f"{var_name}.{safe_field}"
            
            if filter_spec.get('not_null'):
                conditions.append(f"{field_ref} != null")
            
            if 'equals' in filter_spec:
                value = filter_spec['equals']
                if isinstance(value, str):
                    conditions.append(f'{field_ref} == "{value}"')
                else:
                    conditions.append(f'{field_ref} == {value}')
            
            if 'not_equal' in filter_spec:
                values = filter_spec['not_equal']
                if not isinstance(values, list):
                    values = [values]
                for value in values:
                    if isinstance(value, str):
                        conditions.append(f'{field_ref} != "{value}"')
                    else:
                        conditions.append(f'{field_ref} != {value}')
            
            if 'min_length' in filter_spec:
                conditions.append(f"LENGTH({field_ref}) >= {filter_spec['min_length']}")
        
        return conditions
    
    def _collection_bind_vars(self) -> Dict[str, Any]:
        """Build collection bind variables shared across queries."""
        bv: Dict[str, Any] = {
            "@source_collection": self.source_collection_name,
            "@edge_collection": self.edge_collection_name,
        }
        if self.target_collection_name:
            bv["@target_collection"] = self.target_collection_name
        if self.search_view:
            bv["@search_view"] = self.search_view
        return bv

    def _build_bind_vars(self, threshold: float, batch_size: int, offset: int) -> Dict[str, Any]:
        """Build bind variables for the query."""
        bv = self._collection_bind_vars()
        bv.update({
            'threshold': threshold,
            'batch_size': batch_size,
            'offset': offset,
        })
        return bv
    
    def _create_edges_from_matches(
        self,
        matches: List[Dict[str, Any]],
        mark_as_inferred: bool
    ) -> int:
        """Create edges from match results."""
        if not matches:
            return 0
        
        edges = []
        
        for match in matches:
            edge = {
                '_from': f"{self.target_collection_name}/{match['target_key']}",
                '_to': f"{self.source_collection_name}/{match['source_key']}",
                'confidence': round(match['confidence'], 4),
                'match_details': {
                    'field_scores': match.get('field_scores', {}),
                    'method': 'cross_collection_matching',
                    'bm25_score': match.get('bm25_score')
                },
                'created_at': datetime.now().isoformat()
            }
            
            if mark_as_inferred:
                edge['inferred'] = True
            
            edges.append(edge)
        
        # Insert edges in batches
        if edges:
            try:
                self.edge_collection.insert_many(edges)
                return len(edges)
            except Exception as e:
                self.logger.error(f"Failed to insert edges: {e}", exc_info=True)
                return 0
        
        return 0
    
    def _normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Normalize weights to sum to 1.0."""
        total = sum(weights.values())
        if total == 0:
            raise ValueError("Field weights cannot all be zero")
        
        return {field: weight / total for field, weight in weights.items()}
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"CrossCollectionMatchingService("
            f"source='{self.source_collection_name}', "
            f"target='{self.target_collection_name}', "
            f"edges='{self.edge_collection_name}')"
        )

