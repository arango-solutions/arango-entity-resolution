"""
Batch similarity computation service.

This service efficiently computes similarity scores for candidate pairs by:
1. Batch fetching all required documents (reduces queries from 100K+ to ~10-15)
2. Computing similarities in-memory using fast algorithms
3. Supporting multiple similarity algorithms (Jaro-Winkler, Levenshtein, etc.)
4. Providing progress tracking for long-running operations

Performance: ~100K+ pairs/second for Jaro-Winkler
"""

import logging
from typing import List, Dict, Any, Optional, Tuple, Callable, Union
from arango.database import StandardDatabase
import time
from datetime import datetime

logger = logging.getLogger(__name__)

from ..similarity.weighted_field_similarity import WeightedFieldSimilarity
from ..utils.validation import validate_collection_name, validate_field_name
from ..utils.constants import DEFAULT_SIMILARITY_THRESHOLD, DEFAULT_BATCH_SIZE


class BatchSimilarityService:
    """
    Batch similarity computation with optimized document fetching.
    
    Fetches all required documents in batches, then computes similarities
    in-memory. This dramatically reduces network overhead compared to
    per-pair queries.
    
    Supported algorithms:
    - jaro_winkler: Best for names and addresses (jellyfish)
    - levenshtein: Edit distance (python-Levenshtein)
    - jaccard: Set-based similarity
    - custom: Provide your own callable
    
    Performance: ~100K+ pairs/second for Jaro-Winkler
    
    Example:
        ```python
        service = BatchSimilarityService(
            db=db,
            collection="companies",
            field_weights={
                "company_name": 0.4,
                "ceo_name": 0.3,
                "address": 0.2,
                "city": 0.1
            },
            similarity_algorithm="jaro_winkler"
        )
        
        matches = service.compute_similarities(
            candidate_pairs=[(\"123\", \"456\"), (\"789\", \"012\")],
            threshold=0.75
        )
        ```
    """
    
    def __init__(
        self,
        db: StandardDatabase,
        collection: str,
        field_weights: Dict[str, float],
        similarity_algorithm: Union[str, Callable[[str, str], float]] = "jaro_winkler",
        batch_size: int = DEFAULT_BATCH_SIZE,
        normalization_config: Optional[Dict[str, Any]] = None,
        field_transformers: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        scoring_method: str = "weighted_heuristic",
        fs_scorer: Optional[Any] = None,
    ):
        """
        Initialize batch similarity service.
        
        Args:
            db: ArangoDB database connection
            collection: Source collection name
            field_weights: Field names and their weights in similarity calculation.
                Example: {"name": 0.4, "address": 0.3, "city": 0.3}
                Weights should sum to 1.0 but will be normalized if not.
            similarity_algorithm: Algorithm name or callable:
                - "jaro_winkler" (default, requires jellyfish)
                - "levenshtein" (requires python-Levenshtein)
                - "jaccard" (built-in)
                - Custom callable: (str1, str2) -> float (0.0-1.0)
            batch_size: Documents to fetch per query. Default DEFAULT_BATCH_SIZE (5000).
            normalization_config: Field normalization options:
                {
                    "strip": True,           # Remove leading/trailing whitespace
                    "case": "upper",         # "upper", "lower", or None
                    "remove_punctuation": False,
                    "remove_extra_whitespace": True
                }
                Default: {"strip": True, "case": "upper", "remove_extra_whitespace": True}
            field_transformers: Optional per-field transformer chains applied before
                normalization_config.
            progress_callback: Optional callback(current, total) for progress updates
        
        Raises:
            ValueError: If configuration is invalid
            ImportError: If required algorithm library not available
        """
        self.db = db
        # Validate collection name to prevent AQL injection
        self.collection = validate_collection_name(collection)
        # Validate all field names to prevent AQL injection
        for field in field_weights.keys():
            validate_field_name(field)
        # Store original weights for reference, but use normalized for computation
        self.field_weights = self._normalize_weights(field_weights)
        self.batch_size = batch_size
        self.progress_callback = progress_callback
        self.field_transformers = field_transformers or {}
        
        # Set default normalization
        default_norm = {
            "strip": True,
            "case": "upper",
            "remove_extra_whitespace": True,
            "remove_punctuation": False
        }
        self.normalization_config = {**default_norm, **(normalization_config or {})}
        
        # Create WeightedFieldSimilarity instance for similarity computation
        # Note: We normalize weights here, so pass normalize=False to WeightedFieldSimilarity
        normalized_weights = self._normalize_weights(field_weights)
        self.similarity_computer = WeightedFieldSimilarity(
            field_weights=normalized_weights,
            algorithm=similarity_algorithm,
            normalize=False,  # Already normalized above
            handle_nulls='skip',
            normalization_config=self.normalization_config,
            field_transformers=self.field_transformers,
        )
        self.algorithm_name = similarity_algorithm if isinstance(similarity_algorithm, str) else "custom"

        # Scoring method: "weighted_heuristic" (default, weighted 0-1 average) or
        # "fellegi_sunter" (calibrated posterior from learned m/u via fs_scorer).
        if scoring_method not in ("weighted_heuristic", "fellegi_sunter"):
            raise ValueError(
                f"scoring_method must be 'weighted_heuristic' or 'fellegi_sunter', got {scoring_method!r}"
            )
        if scoring_method == "fellegi_sunter" and fs_scorer is None:
            raise ValueError("scoring_method='fellegi_sunter' requires an fs_scorer")
        self.scoring_method = scoring_method
        self.fs_scorer = fs_scorer

        # Statistics tracking
        self._stats = {
            'pairs_processed': 0,
            'pairs_above_threshold': 0,
            'documents_cached': 0,
            'batch_count': 0,
            'execution_time_seconds': 0.0,
            'pairs_per_second': 0,
            'timestamp': None
        }
    
    def compute_similarities(
        self,
        candidate_pairs: List[Tuple[str, str]],
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        return_all: bool = False
    ) -> List[Tuple[str, str, float]]:
        """
        Compute similarities for candidate pairs.
        
        Args:
            candidate_pairs: List of (doc1_key, doc2_key) tuples
            threshold: Minimum similarity to include in results (0.0-1.0). 
                Default DEFAULT_SIMILARITY_THRESHOLD (0.75).
            return_all: If True, return all pairs even below threshold
        
        Returns:
            List of (doc1_key, doc2_key, similarity_score) tuples
            Sorted by similarity score descending
        
        Performance: ~100K+ pairs/second for Jaro-Winkler
        """
        if not candidate_pairs:
            return []
        
        start_time = time.time()
        
        # Step 1: Extract all unique document keys
        all_keys = set()
        for doc1_key, doc2_key in candidate_pairs:
            all_keys.add(doc1_key)
            all_keys.add(doc2_key)
        
        # Step 2: Batch fetch ALL documents
        doc_cache = self.batch_fetch_documents(list(all_keys))
        
        # Step 3: Compute similarities in-memory
        matches = []
        processed = 0
        total = len(candidate_pairs)
        
        for doc1_key, doc2_key in candidate_pairs:
            processed += 1
            
            # Progress callback
            if self.progress_callback and processed % 10000 == 0:
                self.progress_callback(processed, total)
            
            doc1 = doc_cache.get(doc1_key)
            doc2 = doc_cache.get(doc2_key)
            
            if not doc1 or not doc2:
                continue

            # Compute the pair score under the configured method.
            score = self._score_pair(doc1, doc2)

            if return_all or score >= threshold:
                matches.append((doc1_key, doc2_key, score))
        
        # Final progress callback
        if self.progress_callback:
            self.progress_callback(total, total)
        
        # Sort by score descending
        matches.sort(key=lambda x: x[2], reverse=True)
        
        # Update statistics
        execution_time = time.time() - start_time
        self._update_statistics(len(candidate_pairs), len(matches), len(doc_cache), execution_time)
        
        return matches
    
    def compute_similarities_detailed(
        self,
        candidate_pairs: List[Tuple[str, str]],
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    ) -> List[Dict[str, Any]]:
        """
        Compute similarities with detailed per-field scores.
        
        Args:
            candidate_pairs: List of (doc1_key, doc2_key) tuples
            threshold: Minimum similarity to include in results (0.0-1.0). 
                Default DEFAULT_SIMILARITY_THRESHOLD (0.75).
        
        Returns:
            List of detailed similarity results:
            [
                {
                    "doc1_key": "123",
                    "doc2_key": "456",
                    "overall_score": 0.87,
                    "field_scores": {
                        "company_name": 0.95,
                        "ceo_name": 0.82,
                        "address": 0.78,
                        "city": 0.92
                    },
                    "weighted_score": 0.87
                },
                ...
            ]
        """
        if not candidate_pairs:
            return []
        
        start_time = time.time()
        
        # Batch fetch documents
        all_keys = set()
        for doc1_key, doc2_key in candidate_pairs:
            all_keys.add(doc1_key)
            all_keys.add(doc2_key)
        
        doc_cache = self.batch_fetch_documents(list(all_keys))
        
        # Compute detailed similarities
        detailed_matches = []
        processed = 0
        total = len(candidate_pairs)
        
        for doc1_key, doc2_key in candidate_pairs:
            processed += 1
            
            if self.progress_callback and processed % 10000 == 0:
                self.progress_callback(processed, total)
            
            doc1 = doc_cache.get(doc1_key)
            doc2 = doc_cache.get(doc2_key)
            
            if not doc1 or not doc2:
                continue
            
            # Compute detailed scores
            field_scores, weighted_score = self._compute_detailed_similarity(doc1, doc2)
            
            if weighted_score >= threshold:
                detailed_matches.append({
                    'doc1_key': doc1_key,
                    'doc2_key': doc2_key,
                    'overall_score': weighted_score,
                    'field_scores': field_scores,
                    'weighted_score': weighted_score
                })
        
        # Final progress callback
        if self.progress_callback:
            self.progress_callback(total, total)
        
        # Sort by weighted score descending
        detailed_matches.sort(key=lambda x: x['weighted_score'], reverse=True)
        
        # Update statistics
        execution_time = time.time() - start_time
        self._update_statistics(len(candidate_pairs), len(detailed_matches), len(doc_cache), execution_time)
        
        return detailed_matches
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get computation statistics.
        
        Returns:
            Statistics dictionary with performance metrics
        """
        return self._stats.copy()
    
    def batch_fetch_documents(self, keys: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch documents in batches for efficient retrieval.
        
        Args:
            keys: List of document keys to fetch
        
        Returns:
            Dictionary mapping document keys to document data
        """
        doc_cache = {}
        batch_count = 0
        
        # Fetch in batches
        for i in range(0, len(keys), self.batch_size):
            batch = keys[i:i + self.batch_size]
            batch_count += 1
            
            # Build query to fetch only needed fields
            fields = list(self.field_weights.keys())
            fields_str = ', '.join([f'"{f}": doc.{f} || ""' for f in fields])
            
            query = f"""
            FOR doc IN @@collection
                FILTER doc._key IN @keys
                RETURN {{
                    _key: doc._key,
                    {fields_str}
                }}
            """
            
            try:
                cursor = self.db.aql.execute(query, bind_vars={
                    '@collection': self.collection,
                    'keys': batch,
                })
                for doc in cursor:
                    doc_cache[doc['_key']] = doc
            except Exception as e:
                # Fallback to individual fetches for this batch
                for key in batch:
                    try:
                        doc = self.db.collection(self.collection).get(key)
                        if doc:
                            doc_cache[key] = doc
                    except Exception as e:
                        logger.warning("Failed to fetch document %s from %s: %s", key, self.collection, e)
        
        self._stats['batch_count'] = batch_count
        
        return doc_cache
    
    def _score_pair(self, doc1: Dict[str, Any], doc2: Dict[str, Any]) -> float:
        """Score a pair under the configured method.

        ``weighted_heuristic`` returns the weighted 0-1 average; ``fellegi_sunter``
        returns the calibrated posterior from learned m/u over per-field scores.
        """
        if self.scoring_method == "fellegi_sunter":
            field_scores, _ = self._compute_detailed_similarity(doc1, doc2)
            return self.fs_scorer.score(field_scores)
        return self._compute_weighted_similarity(doc1, doc2)

    def _compute_weighted_similarity(self, doc1: Dict[str, Any], doc2: Dict[str, Any]) -> float:
        """
        Compute weighted similarity between two documents.
        
        Uses WeightedFieldSimilarity internally for consistency and maintainability.
        
        Args:
            doc1: First document
            doc2: Second document
        
        Returns:
            Weighted similarity score (0.0-1.0)
        """
        return self.similarity_computer.compute(doc1, doc2)
    
    def _compute_detailed_similarity(
        self,
        doc1: Dict[str, Any],
        doc2: Dict[str, Any]
    ) -> Tuple[Dict[str, float], float]:
        """
        Compute detailed per-field similarities.
        
        Uses WeightedFieldSimilarity internally for consistency.
        
        Args:
            doc1: First document
            doc2: Second document
        
        Returns:
            Tuple of (field_scores dict, weighted_score)
        """
        detailed = self.similarity_computer.compute_detailed(doc1, doc2)
        # Convert None values to 0.0 for backward compatibility
        field_scores = {
            k: (v if v is not None else 0.0)
            for k, v in detailed['field_scores'].items()
        }
        return field_scores, detailed['weighted_score']
    
    
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
    
    def _update_statistics(
        self,
        pairs_processed: int,
        pairs_above_threshold: int,
        documents_cached: int,
        execution_time: float
    ):
        """Update internal statistics."""
        self._stats.update({
            'pairs_processed': pairs_processed,
            'pairs_above_threshold': pairs_above_threshold,
            'documents_cached': documents_cached,
            'execution_time_seconds': round(execution_time, 2),
            'pairs_per_second': int(pairs_processed / execution_time) if execution_time > 0 else 0,
            'timestamp': datetime.now().isoformat(),
            'algorithm': self.algorithm_name
        })
    
    def __repr__(self) -> str:
        """String representation."""
        fields_str = ', '.join(self.field_weights.keys())
        return (f"BatchSimilarityService("
                f"collection='{self.collection}', "
                f"algorithm='{self.algorithm_name}', "
                f"fields=[{fields_str}])")

