"""
Geographic blocking strategy for location-based entity resolution.

This strategy uses geographic attributes (state, city, ZIP code) to efficiently
block entity pairs. Particularly useful for:
- Businesses in specific regions
- Customer deduplication by location
- Multi-location entity resolution
- ZIP code range filtering

Key features:
- State-based blocking
- City-based blocking
- ZIP code range filtering
- Combined geographic blocking (e.g., city + state)
"""

from typing import List, Dict, Any, Optional, Tuple
from arango.database import StandardDatabase
import time

from .base_strategy import BlockingStrategy
from ..utils.validation import validate_field_names


class GeographicBlockingStrategy(BlockingStrategy):
    """
    Geographic blocking for location-based entity resolution.
    
    This strategy groups entities by geographic attributes like state, city,
    or ZIP code ranges. This dramatically reduces comparisons by ensuring
    only geographically-proximate entities are compared.
    
    Use cases:
    - Multi-state business deduplication
    - City-specific matching
    - ZIP code range filtering (e.g., South Dakota: 570-577)
    - Regional entity resolution
    
    Performance: O(n) where n = entities per geographic region
    
    Example:
        ```python
        # City + State blocking
        strategy = GeographicBlockingStrategy(
            db=db,
            collection="companies",
            blocking_type="city_state",
            geographic_fields={
                "city": "primary_city",
                "state": "primary_state"
            },
            filters={
                "primary_city": {"not_null": True},
                "primary_state": {"not_null": True}
            }
        )
        pairs = strategy.generate_candidates()
        
        # ZIP code range blocking (e.g., South Dakota)
        strategy = GeographicBlockingStrategy(
            db=db,
            collection="registrations",
            blocking_type="zip_range",
            geographic_fields={"zip": "postal_code"},
            zip_ranges=[("570", "577")],  # SD ZIP codes
            filters={"postal_code": {"not_null": True}}
        )
        pairs = strategy.generate_candidates()
        ```
    
    Performance: Reduces comparisons from O(n^2) to O(kxm^2) where k = number
    of regions and m = average entities per region
    """
    
    def __init__(
        self,
        db: StandardDatabase,
        collection: str,
        blocking_type: str = "state",
        geographic_fields: Optional[Dict[str, str]] = None,
        zip_ranges: Optional[List[Tuple[str, str]]] = None,
        filters: Optional[Dict[str, Dict[str, Any]]] = None,
        max_block_size: int = 1000,
        min_block_size: int = 2
    ):
        """
        Initialize geographic blocking strategy.
        
        Args:
            db: ArangoDB database connection
            collection: Source collection name
            blocking_type: Type of geographic blocking:
                - "state": Block by state/province
                - "city": Block by city only
                - "city_state": Block by city AND state
                - "zip_range": Block by ZIP code ranges
                - "zip_prefix": Block by ZIP code prefix (first N digits)
            geographic_fields: Mapping of logical field names to actual field names.
                Required fields depend on blocking_type:
                - state: {"state": "field_name"}
                - city: {"city": "field_name"}
                - city_state: {"city": "field_name", "state": "field_name"}
                - zip_range: {"zip": "field_name"}
                - zip_prefix: {"zip": "field_name"}
                Example: {"city": "NAME_PRIMARY_CITY", "state": "NAME_PRIMARY_STATE"}
            zip_ranges: For zip_range blocking, list of (min, max) tuples.
                Example: [("570", "577"), ("800", "816")]  # SD and CO
                Ranges are inclusive and compared as strings.
            filters: Optional filters per field (see base class for format)
            max_block_size: Skip blocks larger than this (likely bad data).
                Default 1000.
            min_block_size: Skip blocks smaller than this (no pairs to generate).
                Default 2.
        
        Raises:
            ValueError: If configuration is invalid
        """
        super().__init__(db, collection, filters)
        
        # Validate blocking type
        valid_types = ["state", "city", "city_state", "zip_range", "zip_prefix"]
        if blocking_type not in valid_types:
            raise ValueError(f"blocking_type must be one of {valid_types}")
        
        self.blocking_type = blocking_type
        self.geographic_fields = geographic_fields or {}
        self.zip_ranges = zip_ranges or []
        self.max_block_size = max_block_size
        self.min_block_size = min_block_size
        
        # Validate configuration
        self._validate_configuration()
        
        # Validate field names for security
        if self.geographic_fields:
            field_names = list(self.geographic_fields.values())
            validate_field_names(field_names)
    
    def _validate_configuration(self):
        """Validate that required fields are provided for the blocking type."""
        required_fields = {
            "state": ["state"],
            "city": ["city"],
            "city_state": ["city", "state"],
            "zip_range": ["zip"],
            "zip_prefix": ["zip"]
        }
        
        required = required_fields.get(self.blocking_type, [])
        missing = [f for f in required if f not in self.geographic_fields]
        
        if missing:
            raise ValueError(
                f"blocking_type '{self.blocking_type}' requires fields: {required}. "
                f"Missing: {missing}"
            )
        
        # Validate ZIP ranges if specified
        if self.blocking_type == "zip_range" and not self.zip_ranges:
            raise ValueError("zip_range blocking requires zip_ranges parameter")
    
    def generate_candidates(self) -> List[Dict[str, Any]]:
        """
        Generate candidate pairs using geographic blocking.
        
        Process:
        1. Apply filters to documents
        2. Group documents by geographic attributes (state, city, ZIP, etc.)
        3. For each geographic block of reasonable size:
           - Generate all pairs within the block
        4. Return candidate pairs with geographic metadata
        
        Returns:
            List of candidate pairs:
            [
                {
                    "doc1_key": "123",
                    "doc2_key": "456",
                    "blocking_keys": {"city": "SIOUX FALLS", "state": "SD"},
                    "block_size": 15,
                    "method": "geographic_blocking",
                    "blocking_type": "city_state"
                },
                ...
            ]
        
        Performance: O(n) where n = number of documents
        """
        start_time = time.time()
        
        # Build the AQL query based on blocking type
        query = self._build_geographic_query()
        
        # Execute query
        cursor = self.db.aql.execute(query, bind_vars=self._build_bind_vars())
        pairs = list(cursor)
        
        # Normalize pairs
        normalized_pairs = self._normalize_pairs(pairs)
        
        # Update statistics
        execution_time = time.time() - start_time
        self._update_statistics(normalized_pairs, execution_time)
        
        # Add additional stats
        self._stats.update({
            'blocking_type': self.blocking_type,
            'geographic_fields': self.geographic_fields,
            'min_block_size': self.min_block_size,
            'max_block_size': self.max_block_size,
            'blocks_processed': self._estimate_blocks_processed(normalized_pairs)
        })
        
        return normalized_pairs
    
    def _build_geographic_query(self) -> str:
        """
        Build the AQL query for geographic blocking.
        
        Returns:
            AQL query string
        """
        query_parts = [f"FOR d IN {self.collection}"]
        
        # Add filters
        if self.filters:
            conditions, filter_bind_vars = self._build_filter_conditions(self.filters)
            # store for use in _build_bind_vars
            self._filter_bind_vars = filter_bind_vars
            for condition in conditions:
                query_parts.append(f"    FILTER {condition}")
        else:
            self._filter_bind_vars = {}
        
        # Add ZIP range filter if specified
        if self.blocking_type == "zip_range":
            zip_field = self.geographic_fields["zip"]
            zip_conditions = []
            for min_zip, max_zip in self.zip_ranges:
                zip_conditions.append(
                    f'(SUBSTRING(TO_STRING(d.{zip_field}), 0, {len(min_zip)}) >= "{min_zip}" '
                    f'AND SUBSTRING(TO_STRING(d.{zip_field}), 0, {len(max_zip)}) <= "{max_zip}")'
                )
            query_parts.append(f"    FILTER {' OR '.join(zip_conditions)}")
        
        # Build COLLECT clause based on blocking type
        collect_vars = self._build_collect_vars()
        collect_clause = f"    COLLECT {', '.join(collect_vars)}"
        query_parts.append(collect_clause)
        
        # Add INTO clause to keep documents
        query_parts.append("    INTO group")
        query_parts.append("    KEEP d")
        
        # Extract document keys
        query_parts.append("    LET doc_keys = group[*].d._key")
        
        # Filter by block size
        query_parts.append(f"    FILTER LENGTH(doc_keys) >= {self.min_block_size}")
        query_parts.append(f"    FILTER LENGTH(doc_keys) <= {self.max_block_size}")
        
        # Generate pairs within block
        query_parts.append("    FOR i IN 0..LENGTH(doc_keys)-2")
        query_parts.append("        FOR j IN (i+1)..LENGTH(doc_keys)-1")
        
        # Build return object with blocking key values
        blocking_key_obj = self._build_blocking_key_obj()
        
        return_clause = f"""            RETURN {{
                doc1_key: doc_keys[i],
                doc2_key: doc_keys[j],
                blocking_keys: {{{blocking_key_obj}}},
                block_size: LENGTH(doc_keys),
                method: "geographic_blocking",
                blocking_type: "{self.blocking_type}"
            }}"""
        
        query_parts.append(return_clause)
        
        return "\n".join(query_parts)
    
    def _build_collect_vars(self) -> List[str]:
        """Build COLLECT variable assignments based on blocking type."""
        collect_vars = []
        
        if self.blocking_type == "state":
            state_field = self.geographic_fields["state"]
            collect_vars.append(f"state = d.{state_field}")
        
        elif self.blocking_type == "city":
            city_field = self.geographic_fields["city"]
            collect_vars.append(f"city = d.{city_field}")
        
        elif self.blocking_type == "city_state":
            city_field = self.geographic_fields["city"]
            state_field = self.geographic_fields["state"]
            collect_vars.append(f"city = d.{city_field}")
            collect_vars.append(f"state = d.{state_field}")
        
        elif self.blocking_type == "zip_range":
            zip_field = self.geographic_fields["zip"]
            # Use full ZIP for blocking within ranges
            collect_vars.append(f"zip = d.{zip_field}")
        
        elif self.blocking_type == "zip_prefix":
            zip_field = self.geographic_fields["zip"]
            # Use first 3 digits of ZIP for blocking
            collect_vars.append(f"zip_prefix = SUBSTRING(TO_STRING(d.{zip_field}), 0, 3)")
        
        return collect_vars
    
    def _build_blocking_key_obj(self) -> str:
        """Build the blocking keys object for return clause."""
        parts = []
        
        if self.blocking_type == "state":
            parts.append('"state": state')
        elif self.blocking_type == "city":
            parts.append('"city": city')
        elif self.blocking_type == "city_state":
            parts.append('"city": city')
            parts.append('"state": state')
        elif self.blocking_type == "zip_range":
            parts.append('"zip": zip')
        elif self.blocking_type == "zip_prefix":
            parts.append('"zip_prefix": zip_prefix')
        
        return ', '.join(parts)
    
    def _build_bind_vars(self) -> Dict[str, Any]:
        """Build bind variables for the query (includes filter bind vars)."""
        return getattr(self, '_filter_bind_vars', {})
    
    def __repr__(self) -> str:
        """String representation of the strategy."""
        return (
            f"GeographicBlockingStrategy("
            f"collection='{self.collection}', "
            f"blocking_type='{self.blocking_type}', "
            f"block_size={self.min_block_size}-{self.max_block_size})"
        )

