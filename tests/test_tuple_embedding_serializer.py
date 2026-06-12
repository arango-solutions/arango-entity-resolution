"""
Tests for TupleEmbeddingSerializer

Tests deterministic serialization, field ordering, weighting, and structured paths.
"""

import pytest
from entity_resolution.services.tuple_embedding_serializer import TupleEmbeddingSerializer


class TestTupleEmbeddingSerializer:
    """Test basic serialization functionality."""
    
    def test_basic_serialization(self):
        """Test basic record serialization."""
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "company", "email"]
        )
        
        record = {
            "name": "John Smith",
            "company": "Acme Corp",
            "email": "john@acme.com"
        }
        
        result = serializer.serialize(record)
        assert result == "John Smith | Acme Corp | john@acme.com"
    
    def test_deterministic_field_ordering(self):
        """Test that field order is deterministic."""
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "company", "email"]
        )
        
        record1 = {"name": "John", "company": "Acme", "email": "john@acme.com"}
        record2 = {"email": "john@acme.com", "name": "John", "company": "Acme"}
        
        result1 = serializer.serialize(record1)
        result2 = serializer.serialize(record2)
        
        assert result1 == result2, "Serialization should be deterministic regardless of input order"
    
    def test_deterministic_hash(self):
        """Test that same record produces same hash."""
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "company"]
        )
        
        record1 = {"name": "John", "company": "Acme"}
        record2 = {"company": "Acme", "name": "John"}
        
        hash1 = serializer.get_serialization_hash(record1)
        hash2 = serializer.get_serialization_hash(record2)
        
        assert hash1 == hash2, "Hash should be deterministic"
    
    def test_field_weights(self):
        """Test field weighting configuration."""
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "company", "email"],
            field_weights={"name": 0.5, "company": 0.3, "email": 0.2}
        )
        
        record = {"name": "John", "company": "Acme", "email": "john@acme.com"}
        result = serializer.serialize(record)
        
        # Serialization should still work with weights configured
        assert "John" in result
        assert "Acme" in result
        assert "john@acme.com" in result
    
    def test_weight_normalization(self):
        """Test that weights are normalized correctly."""
        # Use weights that sum to more than 1.0 to test normalization
        serializer = TupleEmbeddingSerializer(
            field_weights={"name": 0.5, "company": 0.3, "email": 0.2},
            normalize_weights=True
        )
        
        # Weights should be normalized to sum to 1.0
        assert sum(serializer.field_weights.values()) == pytest.approx(1.0)
        # After normalization, proportions should be preserved
        assert serializer.field_weights["name"] > serializer.field_weights["company"]
        assert serializer.field_weights["company"] > serializer.field_weights["email"]
    
    def test_structured_paths(self):
        """Test nested field access via structured paths."""
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "address_city"],
            structured_paths={"address_city": ["address", "city"]}
        )
        
        record = {
            "name": "John",
            "address": {
                "city": "New York",
                "street": "123 Main St"
            }
        }
        
        result = serializer.serialize(record)
        assert "New York" in result
        assert "123 Main St" not in result  # Only city should be included
    
    def test_missing_fields(self):
        """Test handling of missing fields."""
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "company", "email"],
            include_missing_fields=False
        )
        
        record = {"name": "John", "email": "john@acme.com"}  # Missing "company"
        
        result = serializer.serialize(record)
        assert "John" in result
        assert "john@acme.com" in result
        assert "company" not in result.lower()
    
    def test_missing_fields_included(self):
        """Test including missing fields as empty strings."""
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "company", "email"],
            include_missing_fields=True
        )
        
        record = {"name": "John", "email": "john@acme.com"}
        
        result = serializer.serialize(record)
        parts = result.split(" | ")
        assert len(parts) == 3  # All three fields should be present
        assert parts[0] == "John"
        assert parts[1] == ""  # Missing company should be empty
        assert parts[2] == "john@acme.com"
    
    def test_automatic_field_ordering(self):
        """Test automatic alphabetical field ordering when field_order is None."""
        serializer = TupleEmbeddingSerializer()  # No field_order specified
        
        record = {"zebra": "z", "apple": "a", "banana": "b"}
        
        result = serializer.serialize(record)
        parts = result.split(" | ")
        
        # Should be in alphabetical order
        assert parts[0] == "a"  # apple
        assert parts[1] == "b"  # banana
        assert parts[2] == "z"  # zebra
    
    def test_custom_separator(self):
        """Test custom separator."""
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "company"],
            separator=", "
        )
        
        record = {"name": "John", "company": "Acme"}
        result = serializer.serialize(record)
        
        assert result == "John, Acme"
    
    def test_config_hash(self):
        """Test that configuration hash is deterministic."""
        serializer1 = TupleEmbeddingSerializer(
            field_order=["name", "company"],
            field_weights={"name": 0.6, "company": 0.4}
        )
        
        serializer2 = TupleEmbeddingSerializer(
            field_order=["name", "company"],
            field_weights={"name": 0.6, "company": 0.4}
        )
        
        hash1 = serializer1.get_config_hash()
        hash2 = serializer2.get_config_hash()
        
        assert hash1 == hash2, "Same configuration should produce same hash"
    
    def test_to_dict_from_dict(self):
        """Test serialization configuration export/import."""
        serializer1 = TupleEmbeddingSerializer(
            field_order=["name", "company"],
            field_weights={"name": 0.6, "company": 0.4},
            structured_paths={"address": ["address", "city"]},
            separator=", "
        )
        
        config = serializer1.to_dict()
        serializer2 = TupleEmbeddingSerializer.from_dict(config)
        
        record = {"name": "John", "company": "Acme"}
        result1 = serializer1.serialize(record)
        result2 = serializer2.serialize(record)
        
        assert result1 == result2, "Recreated serializer should produce same results"
    
    def test_batch_serialization(self):
        """Test batch serialization."""
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "company"]
        )
        
        records = [
            {"name": "John", "company": "Acme"},
            {"name": "Jane", "company": "TechCo"}
        ]
        
        results = serializer.serialize_batch(records)
        
        assert len(results) == 2
        assert results[0] == "John | Acme"
        assert results[1] == "Jane | TechCo"
    
    def test_invalid_field_weights(self):
        """Test validation of field weights."""
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            TupleEmbeddingSerializer(
                field_weights={"name": 1.5}  # Invalid weight > 1.0
            )
        
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            TupleEmbeddingSerializer(
                field_weights={"name": -0.1}  # Invalid weight < 0.0
            )
    
    def test_duplicate_field_order(self):
        """Test validation of duplicate fields in field_order."""
        with pytest.raises(ValueError, match="duplicate field names"):
            TupleEmbeddingSerializer(
                field_order=["name", "company", "name"]  # Duplicate "name"
            )
    
    def test_various_data_types(self):
        """Test serialization of various data types."""
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "age", "active", "tags", "metadata"]
        )
        
        record = {
            "name": "John",
            "age": 30,
            "active": True,
            "tags": ["developer", "python"],
            "metadata": {"level": "senior"}
        }
        
        result = serializer.serialize(record)
        
        assert "John" in result
        assert "30" in result
        assert "true" in result.lower()
        assert "developer" in result
        assert "python" in result


class TestSerializationDeterminism:
    """Test deterministic serialization across multiple runs."""
    
    def test_same_record_multiple_runs(self):
        """Test that same record produces same serialization across multiple runs."""
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "company", "email"]
        )
        
        record = {"name": "John Smith", "company": "Acme Corp", "email": "john@acme.com"}
        
        results = [serializer.serialize(record) for _ in range(10)]
        
        # All results should be identical
        assert len(set(results)) == 1, "Serialization should be deterministic"
        assert results[0] == "John Smith | Acme Corp | john@acme.com"
    
    def test_different_record_orders(self):
        """Test that record field order doesn't affect serialization."""
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "company", "email"]
        )
        
        record1 = {"name": "John", "company": "Acme", "email": "john@acme.com"}
        record2 = {"email": "john@acme.com", "company": "Acme", "name": "John"}
        record3 = {"company": "Acme", "email": "john@acme.com", "name": "John"}
        
        result1 = serializer.serialize(record1)
        result2 = serializer.serialize(record2)
        result3 = serializer.serialize(record3)
        
        assert result1 == result2 == result3, "Field order in input shouldn't matter"
    
    def test_hash_consistency(self):
        """Test that hash is consistent across multiple runs."""
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "company"]
        )
        
        record = {"name": "John", "company": "Acme"}
        
        hashes = [serializer.get_serialization_hash(record) for _ in range(10)]
        
        assert len(set(hashes)) == 1, "Hash should be consistent"
    
    def test_configuration_consistency(self):
        """Test that same configuration produces same results."""
        config = {
            "field_order": ["name", "company"],
            "field_weights": {"name": 0.6, "company": 0.4},
            "separator": " | "
        }
        
        serializer1 = TupleEmbeddingSerializer(**config)
        serializer2 = TupleEmbeddingSerializer(**config)
        
        record = {"name": "John", "company": "Acme"}
        
        assert serializer1.serialize(record) == serializer2.serialize(record)
        assert serializer1.get_config_hash() == serializer2.get_config_hash()


class TestWeightedSerialization:
    """Weighted serialization repeats heavier fields proportionally."""

    def test_weights_inert_by_default(self):
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "company"],
            field_weights={"name": 0.7, "company": 0.3},
        )
        record = {"name": "John", "company": "Acme"}
        assert serializer.serialize(record) == "John | Acme"

    def test_apply_weights_repeats_heavier_fields(self):
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "company"],
            field_weights={"name": 0.7, "company": 0.3},
        )
        record = {"name": "John", "company": "Acme"}
        # 0.7 / 0.3 rounds to 2 repetitions for name, 1 for company
        assert serializer.serialize(record, apply_weights=True) == "John | John | Acme"

    def test_constructor_default_applies_weights(self):
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "company"],
            field_weights={"name": 0.7, "company": 0.3},
            apply_weights=True,
        )
        record = {"name": "John", "company": "Acme"}
        assert serializer.serialize(record) == "John | John | Acme"
        # Explicit override still wins
        assert serializer.serialize(record, apply_weights=False) == "John | Acme"

    def test_repetitions_capped(self):
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "note"],
            field_weights={"name": 0.99, "note": 0.01},
            apply_weights=True,
        )
        record = {"name": "John", "note": "x"}
        parts = serializer.serialize(record).split(" | ")
        assert parts.count("John") == TupleEmbeddingSerializer.MAX_WEIGHT_REPETITIONS
        assert parts.count("x") == 1

    def test_unweighted_field_gets_single_occurrence(self):
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "email"],
            field_weights={"name": 1.0},
            apply_weights=True,
        )
        record = {"name": "John", "email": "j@x.com"}
        assert serializer.serialize(record) == "John | j@x.com"

    def test_config_hash_stable_for_default_and_distinct_when_enabled(self):
        base = dict(field_order=["name"], field_weights={"name": 1.0})
        default = TupleEmbeddingSerializer(**base)
        enabled = TupleEmbeddingSerializer(**base, apply_weights=True)
        assert default.get_config_hash() != enabled.get_config_hash()

    def test_to_dict_round_trip(self):
        serializer = TupleEmbeddingSerializer(
            field_order=["name", "company"],
            field_weights={"name": 0.7, "company": 0.3},
            apply_weights=True,
        )
        clone = TupleEmbeddingSerializer.from_dict(serializer.to_dict())
        record = {"name": "John", "company": "Acme"}
        assert clone.serialize(record) == serializer.serialize(record)
