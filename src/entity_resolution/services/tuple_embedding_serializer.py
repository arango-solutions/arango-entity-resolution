"""
Tuple Embedding Serialization Pipeline

Provides deterministic serialization of database records for embedding generation.
Ensures consistent field ordering and weighting for reproducible embeddings.

Key Features:
- Deterministic field ordering (alphabetical by default, configurable)
- Field weighting support for importance-based serialization
- Optional structured embedding paths (nested field access)
- Backward compatible with existing EmbeddingService

Based on research:
- Ebraheem et al. (2018): "Distributed Representations of Tuples for Entity Resolution"
"""

import logging
from typing import Dict, List, Any, Optional, Union, Tuple
from collections import OrderedDict
import json
import hashlib


class TupleEmbeddingSerializer:
    """
    Deterministic serialization of database records for tuple embeddings.
    
    Ensures that the same record always produces the same serialized representation,
    enabling reproducible embeddings and consistent A/B evaluations.
    
    Attributes:
        field_order: Ordered list of field names (determines serialization order)
        field_weights: Dictionary mapping field names to weights (0.0-1.0)
        structured_paths: Optional nested field paths (e.g., ["address", "city"])
        separator: String separator between fields (default: " | ")
        normalize_weights: Whether to normalize weights to sum to 1.0
    
    Example:
        >>> serializer = TupleEmbeddingSerializer(
        ...     field_order=["name", "company", "email"],
        ...     field_weights={"name": 0.5, "company": 0.3, "email": 0.2}
        ... )
        >>> record = {"name": "John Smith", "company": "Acme", "email": "john@acme.com"}
        >>> serialized = serializer.serialize(record)
        >>> print(serialized)  # "John Smith | Acme | john@acme.com"
    """
    
    def __init__(
        self,
        field_order: Optional[List[str]] = None,
        field_weights: Optional[Dict[str, float]] = None,
        structured_paths: Optional[Dict[str, List[str]]] = None,
        separator: str = " | ",
        normalize_weights: bool = True,
        include_missing_fields: bool = False,
        apply_weights: bool = False
    ):
        """
        Initialize tuple embedding serializer.
        
        Args:
            field_order: Ordered list of field names for deterministic ordering.
                If None, uses alphabetical order of all fields in records.
            field_weights: Dictionary mapping field names to weights (0.0-1.0).
                Weights are used for weighted concatenation if needed.
                If None, all fields have equal weight.
            structured_paths: Optional dictionary mapping field names to nested paths.
                Example: {"address": ["address", "street"]} to access record["address"]["street"]
                If None, uses direct field access.
            separator: String separator between fields in serialization.
                Default: " | " (space-pipe-space).
            normalize_weights: Whether to normalize weights to sum to 1.0.
                Default: True.
            include_missing_fields: Whether to include fields with None/missing values.
                Default: False (excludes missing fields).
            apply_weights: Default for serialize()/serialize_batch(). When True,
                field values are repeated proportionally to their weight so that
                higher-weighted fields contribute more to the embedding text.
                Default: False (weights stored but not applied). Note: changing
                this changes serialized output, so embeddings generated with a
                different setting are not comparable.

        Raises:
            ValueError: If field_order contains duplicates or invalid field names
            ValueError: If field_weights contains invalid weights (<0 or >1)
        """
        self.logger = logging.getLogger(__name__)
        
        # Validate field_order
        if field_order is not None:
            if len(field_order) != len(set(field_order)):
                raise ValueError("field_order contains duplicate field names")
            self.field_order = field_order
        else:
            self.field_order = None  # Will be determined dynamically
        
        # Validate and normalize field_weights
        if field_weights is not None:
            for field, weight in field_weights.items():
                if not (0.0 <= weight <= 1.0):
                    raise ValueError(
                        f"Field weight for '{field}' must be between 0.0 and 1.0, got {weight}"
                    )
            
            if normalize_weights:
                total_weight = sum(field_weights.values())
                if total_weight > 0:
                    self.field_weights = {
                        field: weight / total_weight
                        for field, weight in field_weights.items()
                    }
                else:
                    self.field_weights = field_weights
            else:
                self.field_weights = field_weights
        else:
            self.field_weights = None
        
        self.structured_paths = structured_paths or {}
        self.separator = separator
        self.normalize_weights = normalize_weights
        self.include_missing_fields = include_missing_fields
        self.apply_weights = apply_weights

        if self.field_weights and not self.apply_weights:
            self.logger.warning(
                "field_weights configured but apply_weights=False: weights will NOT "
                "affect serialization. Pass apply_weights=True to the constructor "
                "(or serialize()) to weight fields by repetition."
            )

        self.logger.debug(
            f"Initialized TupleEmbeddingSerializer: "
            f"field_order={self.field_order}, "
            f"field_weights={self.field_weights is not None}, "
            f"structured_paths={len(self.structured_paths)} paths"
        )
    
    def _get_field_value(
        self,
        record: Dict[str, Any],
        field_name: str
    ) -> Optional[str]:
        """
        Extract field value from record, supporting structured paths.
        
        Args:
            record: Database record dictionary
            field_name: Field name to extract
        
        Returns:
            Field value as string, or None if missing/invalid
        """
        # Check if field has a structured path
        if field_name in self.structured_paths:
            path = self.structured_paths[field_name]
            value = record
            try:
                for key in path:
                    if isinstance(value, dict):
                        value = value.get(key)
                    else:
                        return None
                    if value is None:
                        return None
            except (KeyError, TypeError):
                return None
        else:
            # Direct field access
            value = record.get(field_name)
        
        # Convert to string if not None
        if value is None:
            return None
        
        # Convert various types to string
        if isinstance(value, str):
            return value.strip() if value.strip() else None
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, bool):
            return str(value).lower()
        elif isinstance(value, list):
            # Join list elements with comma
            return ", ".join(str(v) for v in value if v is not None)
        elif isinstance(value, dict):
            # Serialize dict as JSON string for consistency
            return json.dumps(value, sort_keys=True)
        else:
            return str(value)
    
    def _determine_field_order(self, record: Dict[str, Any]) -> List[str]:
        """
        Determine field order for a record.
        
        If field_order was specified, uses that. Otherwise, uses alphabetical order
        of all fields in the record (excluding metadata fields).
        
        Args:
            record: Database record dictionary
        
        Returns:
            Ordered list of field names
        """
        if self.field_order is not None:
            return self.field_order
        
        # Use alphabetical order of all fields (excluding metadata)
        all_fields = [
            k for k in record.keys()
            if not k.startswith('_') and k not in ['embedding_vector', 'embedding_metadata']
        ]
        return sorted(all_fields)
    
    # Cap on how many times a field value may be repeated when weighting is on.
    MAX_WEIGHT_REPETITIONS = 5

    def serialize(
        self,
        record: Dict[str, Any],
        apply_weights: Optional[bool] = None
    ) -> str:
        """
        Serialize a database record to a deterministic string representation.

        Args:
            record: Database record dictionary
            apply_weights: Whether to apply field weights in serialization.
                If True, field values are repeated proportionally to their weight
                relative to the smallest configured weight (capped at
                MAX_WEIGHT_REPETITIONS) so heavier fields contribute more tokens.
                If None (default), uses the constructor-level setting.

        Returns:
            Deterministic string representation of the record

        Example:
            >>> serializer = TupleEmbeddingSerializer(
            ...     field_order=["name", "company"],
            ...     field_weights={"name": 0.7, "company": 0.3}
            ... )
            >>> serializer.serialize({"name": "John", "company": "Acme"})
            'John | Acme'
            >>> serializer.serialize({"name": "John", "company": "Acme"}, apply_weights=True)
            'John | John | Acme'
        """
        if apply_weights is None:
            apply_weights = self.apply_weights
        field_order = self._determine_field_order(record)

        # Extract field values
        field_values = []
        for field_name in field_order:
            value = self._get_field_value(record, field_name)

            if value is None or value == "":
                if self.include_missing_fields:
                    field_values.append("")
                continue

            repetitions = 1
            if apply_weights and self.field_weights:
                repetitions = self._weight_repetitions(field_name)
            field_values.extend([value] * repetitions)

        # Join with separator
        serialized = self.separator.join(field_values)

        return serialized

    def _weight_repetitions(self, field_name: str) -> int:
        """
        Number of times a field value is repeated under weighted serialization.

        Scaled relative to the smallest configured positive weight: the lightest
        field appears once, a field with twice its weight appears twice, capped
        at MAX_WEIGHT_REPETITIONS. Fields without a configured weight get 1.
        """
        weight = self.field_weights.get(field_name)
        if weight is None or weight <= 0:
            return 1
        min_weight = min(w for w in self.field_weights.values() if w > 0)
        return max(1, min(self.MAX_WEIGHT_REPETITIONS, round(weight / min_weight)))
    
    def serialize_batch(
        self,
        records: List[Dict[str, Any]],
        apply_weights: Optional[bool] = None
    ) -> List[str]:
        """
        Serialize a batch of records.
        
        Args:
            records: List of database record dictionaries
            apply_weights: Whether to apply field weights
        
        Returns:
            List of serialized strings (one per record)
        """
        return [self.serialize(record, apply_weights) for record in records]
    
    def get_serialization_hash(
        self,
        record: Dict[str, Any]
    ) -> str:
        """
        Get deterministic hash of serialized record.
        
        Useful for detecting duplicate serializations or ensuring consistency.
        
        Args:
            record: Database record dictionary
        
        Returns:
            MD5 hash of serialized representation (hex string)
        """
        serialized = self.serialize(record)
        return hashlib.md5(serialized.encode('utf-8')).hexdigest()
    
    def get_config_hash(self) -> str:
        """
        Get hash of serializer configuration.
        
        Useful for ensuring consistent configuration across runs.
        
        Returns:
            MD5 hash of configuration (hex string)
        """
        config = {
            'field_order': self.field_order,
            'field_weights': self.field_weights,
            'structured_paths': self.structured_paths,
            'separator': self.separator,
            'normalize_weights': self.normalize_weights,
            'include_missing_fields': self.include_missing_fields
        }
        # Only included when enabled so hashes of existing (default) configs
        # remain stable across versions.
        if self.apply_weights:
            config['apply_weights'] = True
        config_str = json.dumps(config, sort_keys=True)
        return hashlib.md5(config_str.encode('utf-8')).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Export serializer configuration as dictionary.
        
        Returns:
            Dictionary representation of serializer configuration
        """
        return {
            'field_order': self.field_order,
            'field_weights': self.field_weights,
            'structured_paths': self.structured_paths,
            'separator': self.separator,
            'normalize_weights': self.normalize_weights,
            'include_missing_fields': self.include_missing_fields,
            'apply_weights': self.apply_weights
        }
    
    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'TupleEmbeddingSerializer':
        """
        Create serializer from configuration dictionary.
        
        Args:
            config: Dictionary with serializer configuration
        
        Returns:
            TupleEmbeddingSerializer instance
        """
        return cls(**config)
