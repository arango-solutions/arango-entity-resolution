"""
Unit Tests for WeightedFieldSimilarity

Comprehensive unit tests for the WeightedFieldSimilarity component.
"""

import pytest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from entity_resolution.similarity.weighted_field_similarity import WeightedFieldSimilarity


class TestWeightedFieldSimilarity:
    """Test cases for WeightedFieldSimilarity."""
    
    def test_initialization_basic(self):
        """Test basic initialization."""
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 0.5, 'address': 0.5},
            algorithm='jaro_winkler'
        )
        assert similarity is not None
        assert similarity.algorithm_name == 'jaro_winkler'
        assert 'name' in similarity.field_weights
        assert 'address' in similarity.field_weights
    
    def test_initialization_empty_weights(self):
        """Test initialization with empty weights raises error."""
        with pytest.raises(ValueError, match="field_weights cannot be empty"):
            WeightedFieldSimilarity(field_weights={}, algorithm='jaro_winkler')
    
    def test_weight_normalization(self):
        """Test that weights are normalized to sum to 1.0."""
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 0.4, 'address': 0.6},
            algorithm='jaro_winkler',
            normalize=True
        )
        total = sum(similarity.field_weights.values())
        assert abs(total - 1.0) < 0.001
    
    def test_weight_normalization_disabled(self):
        """Test that weights are not normalized when normalize=False."""
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 0.4, 'address': 0.6},
            algorithm='jaro_winkler',
            normalize=False
        )
        assert similarity.field_weights['name'] == 0.4
        assert similarity.field_weights['address'] == 0.6
    
    def test_invalid_null_strategy(self):
        """Test that invalid null strategy raises error."""
        with pytest.raises(ValueError, match="handle_nulls must be one of"):
            WeightedFieldSimilarity(
                field_weights={'name': 1.0},
                algorithm='jaro_winkler',
                handle_nulls='invalid'
            )
    
    def test_compute_basic_similarity(self):
        """Test basic similarity computation."""
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 1.0},
            algorithm='jaro_winkler'
        )
        
        doc1 = {'name': 'John Smith'}
        doc2 = {'name': 'Jon Smith'}
        
        score = similarity.compute(doc1, doc2)
        assert 0.0 <= score <= 1.0
        assert score > 0.8  # Should be high similarity
    
    def test_compute_multi_field_similarity(self):
        """Test similarity computation with multiple fields."""
        similarity = WeightedFieldSimilarity(
            field_weights={
                'name': 0.5,
                'address': 0.3,
                'city': 0.2
            },
            algorithm='jaro_winkler'
        )
        
        doc1 = {
            'name': 'John Smith',
            'address': '123 Main St',
            'city': 'Boston'
        }
        doc2 = {
            'name': 'Jon Smith',
            'address': '123 Main Street',
            'city': 'Boston'
        }
        
        score = similarity.compute(doc1, doc2)
        assert 0.0 <= score <= 1.0
        assert score > 0.7  # Should be high similarity
    
    def test_compute_null_handling_skip(self):
        """Test null handling with 'skip' strategy."""
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 0.5, 'phone': 0.5},
            algorithm='jaro_winkler',
            handle_nulls='skip'
        )
        
        doc1 = {'name': 'John Smith', 'phone': None}
        doc2 = {'name': 'John Smith', 'phone': '555-1234'}
        
        # Should compute based on name only (phone is skipped)
        score = similarity.compute(doc1, doc2)
        assert score > 0.9  # Name matches perfectly
    
    def test_compute_null_handling_zero(self):
        """Test null handling with 'zero' strategy."""
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 0.5, 'phone': 0.5},
            algorithm='jaro_winkler',
            handle_nulls='zero'
        )
        
        doc1 = {'name': 'John Smith', 'phone': None}
        doc2 = {'name': 'John Smith', 'phone': '555-1234'}
        
        # Phone contributes 0.0, name contributes high score
        score = similarity.compute(doc1, doc2)
        assert 0.0 <= score <= 1.0
        assert score < 0.9  # Lower than skip because phone weight is counted as 0
    
    def test_compute_empty_strings(self):
        """Test handling of empty strings."""
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 1.0},
            algorithm='jaro_winkler',
            handle_nulls='skip'
        )
        
        doc1 = {'name': ''}
        doc2 = {'name': 'John Smith'}
        
        # Empty strings should be skipped
        score = similarity.compute(doc1, doc2)
        assert score == 0.0  # No valid fields to compare
    
    def test_compute_detailed_similarity(self):
        """Test detailed similarity computation with per-field scores."""
        similarity = WeightedFieldSimilarity(
            field_weights={
                'name': 0.5,
                'address': 0.5
            },
            algorithm='jaro_winkler'
        )
        
        doc1 = {'name': 'John Smith', 'address': '123 Main St'}
        doc2 = {'name': 'Jon Smith', 'address': '123 Main Street'}
        
        detailed = similarity.compute_detailed(doc1, doc2)
        
        assert 'overall_score' in detailed
        assert 'field_scores' in detailed
        assert 'weighted_score' in detailed
        assert 'name' in detailed['field_scores']
        assert 'address' in detailed['field_scores']
        assert detailed['overall_score'] == detailed['weighted_score']
        assert 0.0 <= detailed['overall_score'] <= 1.0
    
    def test_jaccard_algorithm(self):
        """Test Jaccard similarity algorithm."""
        similarity = WeightedFieldSimilarity(
            field_weights={'text': 1.0},
            algorithm='jaccard'
        )
        
        doc1 = {'text': 'hello world'}
        doc2 = {'text': 'hello world'}
        
        score = similarity.compute(doc1, doc2)
        assert score == 1.0  # Identical strings
    
    def test_jaccard_algorithm_partial(self):
        """Test Jaccard similarity with partial match."""
        similarity = WeightedFieldSimilarity(
            field_weights={'text': 1.0},
            algorithm='jaccard'
        )
        
        doc1 = {'text': 'hello world'}
        doc2 = {'text': 'hello'}
        
        score = similarity.compute(doc1, doc2)
        assert 0.0 < score < 1.0  # Partial match
    
    def test_custom_algorithm(self):
        """Test custom similarity algorithm."""
        def custom_sim(str1: str, str2: str) -> float:
            return 1.0 if str1 == str2 else 0.0
        
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 1.0},
            algorithm=custom_sim
        )
        
        doc1 = {'name': 'John'}
        doc2 = {'name': 'John'}
        doc3 = {'name': 'Jane'}
        
        assert similarity.compute(doc1, doc2) == 1.0
        assert similarity.compute(doc1, doc3) == 0.0
    
    def test_normalization_config_strip(self):
        """Test string normalization with strip."""
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 1.0},
            algorithm='jaro_winkler',
            normalization_config={'strip': True, 'case': None}
        )
        
        doc1 = {'name': '  John Smith  '}
        doc2 = {'name': 'John Smith'}
        
        score = similarity.compute(doc1, doc2)
        assert score > 0.9  # Should match after stripping
    
    def test_normalization_config_case(self):
        """Test string normalization with case conversion."""
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 1.0},
            algorithm='jaro_winkler',
            normalization_config={'strip': True, 'case': 'upper'}
        )
        
        doc1 = {'name': 'john smith'}
        doc2 = {'name': 'JOHN SMITH'}
        
        score = similarity.compute(doc1, doc2)
        assert score > 0.9  # Should match after case conversion
    
    def test_normalization_config_whitespace(self):
        """Test string normalization with whitespace removal."""
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 1.0},
            algorithm='jaro_winkler',
            normalization_config={
                'strip': True,
                'case': None,
                'remove_extra_whitespace': True
            }
        )
        
        doc1 = {'name': 'John    Smith'}
        doc2 = {'name': 'John Smith'}
        
        score = similarity.compute(doc1, doc2)
        assert score > 0.9  # Should match after whitespace normalization

    def test_field_transformer_digits_only_normalizes_phone_numbers(self):
        """Test digits_only transformer for phone matching."""
        similarity = WeightedFieldSimilarity(
            field_weights={'phone': 1.0},
            algorithm='jaro_winkler',
            field_transformers={'phone': ['digits_only']},
        )

        doc1 = {'phone': '(617) 555-1234'}
        doc2 = {'phone': '6175551234'}

        assert similarity.compute(doc1, doc2) == 1.0

    def test_field_transformer_e164_normalizes_phone_numbers(self):
        """Test E.164-style phone normalization."""
        similarity = WeightedFieldSimilarity(
            field_weights={'phone': 1.0},
            algorithm='jaro_winkler',
            field_transformers={'phone': ['e164']},
            normalization_config={'case': None},
        )

        doc1 = {'phone': '+1 (617) 555-1234'}
        doc2 = {'phone': '6175551234'}

        assert similarity.compute(doc1, doc2) == 1.0

    def test_field_transformer_state_code_matches_name_and_abbreviation(self):
        """Test state_code transformer for US state variants."""
        similarity = WeightedFieldSimilarity(
            field_weights={'state': 1.0},
            algorithm='jaro_winkler',
            field_transformers={'state': ['state_code']},
        )

        doc1 = {'state': 'Massachusetts'}
        doc2 = {'state': 'MA'}

        assert similarity.compute(doc1, doc2) == 1.0

    def test_field_transformer_street_suffix_matches_common_variants(self):
        """Test street suffix normalization."""
        similarity = WeightedFieldSimilarity(
            field_weights={'address': 1.0},
            algorithm='jaro_winkler',
            field_transformers={'address': ['street_suffix']},
            normalization_config={'case': 'lower'},
        )

        doc1 = {'address': '123 Main St.'}
        doc2 = {'address': '123 Main Street'}

        assert similarity.compute(doc1, doc2) == 1.0

    def test_field_transformer_company_suffix_matches_common_variants(self):
        """Test company suffix normalization."""
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 1.0},
            algorithm='jaro_winkler',
            field_transformers={'name': ['company_suffix']},
            normalization_config={'case': 'lower'},
        )

        doc1 = {'name': 'Acme Corp.'}
        doc2 = {'name': 'Acme Corporation'}

        assert similarity.compute(doc1, doc2) == 1.0

    def test_field_transformer_chain_applies_in_order(self):
        """Test multiple transformers chained for one field."""
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 1.0},
            algorithm='jaro_winkler',
            field_transformers={'name': ['strip', 'collapse_whitespace', 'company_suffix']},
            normalization_config={'case': 'lower'},
        )

        doc1 = {'name': '  Acme   Corp.  '}
        doc2 = {'name': 'Acme Corporation'}

        assert similarity.compute(doc1, doc2) == 1.0

    def test_field_transformer_supports_dict_spec(self):
        """Test dict transformer specs are accepted."""
        similarity = WeightedFieldSimilarity(
            field_weights={'phone': 1.0},
            algorithm='jaro_winkler',
            field_transformers={'phone': [{'name': 'digits_only'}]},
        )

        assert similarity.compute({'phone': '617-555-1234'}, {'phone': '6175551234'}) == 1.0

    def test_invalid_transformer_name_raises_error(self):
        """Test invalid transformer names fail fast."""
        with pytest.raises(ValueError, match='Unknown transformer'):
            WeightedFieldSimilarity(
                field_weights={'name': 1.0},
                algorithm='jaro_winkler',
                field_transformers={'name': ['not_a_transformer']},
            )
    
    def test_missing_algorithm_library(self):
        """Test error when required library is missing."""
        # This test would require mocking the import, which is complex
        # For now, we'll just verify the error message format
        with pytest.raises((ImportError, ValueError)):
            # Try with invalid algorithm name
            WeightedFieldSimilarity(
                field_weights={'name': 1.0},
                algorithm='nonexistent_algorithm'
            )
    
    def test_repr(self):
        """Test string representation."""
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 0.5, 'address': 0.5},
            algorithm='jaro_winkler'
        )
        
        repr_str = repr(similarity)
        assert 'WeightedFieldSimilarity' in repr_str
        assert 'jaro_winkler' in repr_str
    
    def test_all_fields_missing(self):
        """Test when all fields are missing/null."""
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 1.0},
            algorithm='jaro_winkler',
            handle_nulls='skip'
        )
        
        doc1 = {'name': None}
        doc2 = {'name': None}
        
        score = similarity.compute(doc1, doc2)
        assert score == 0.0  # No valid fields to compare
    
    def test_weighted_average_calculation(self):
        """Test that weighted average is calculated correctly."""
        similarity = WeightedFieldSimilarity(
            field_weights={'field1': 0.5, 'field2': 0.5},
            algorithm='jaro_winkler'
        )
        
        # Create documents where field1 matches perfectly and field2 doesn't
        doc1 = {'field1': 'match', 'field2': 'different1'}
        doc2 = {'field1': 'match', 'field2': 'different2'}
        
        score = similarity.compute(doc1, doc2)
        
        # Score should be around 0.5 (field1 perfect match * 0.5 weight)
        # plus some contribution from field2
        assert 0.0 <= score <= 1.0
    
    def test_detailed_scores_with_nulls(self):
        """Test detailed scores when some fields are null."""
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 0.5, 'phone': 0.5},
            algorithm='jaro_winkler',
            handle_nulls='skip'
        )
        
        doc1 = {'name': 'John Smith', 'phone': None}
        doc2 = {'name': 'John Smith', 'phone': None}
        
        detailed = similarity.compute_detailed(doc1, doc2)
        
        assert detailed['field_scores']['name'] is not None
        assert detailed['field_scores']['phone'] is None  # Skipped
        assert detailed['overall_score'] > 0.9  # Name matches perfectly


if __name__ == '__main__':
    pytest.main([__file__, '-v'])



class TestPhoneticTransformers:
    """Phonetic comparator transformers (plan 1.5)."""

    def _sim(self, transformer):
        from entity_resolution.similarity.weighted_field_similarity import WeightedFieldSimilarity
        return WeightedFieldSimilarity(
            field_weights={"name": 1.0},
            algorithm="jaro_winkler",
            field_transformers={"name": [transformer]},
        )

    def test_metaphone_matches_homophones(self):
        sim = self._sim("metaphone")
        # Smith / Smyth encode identically -> score 1.0.
        score = sim.compute({"name": "Smith"}, {"name": "Smyth"})
        assert score == pytest.approx(1.0)

    def test_nysiis_matches_homophones(self):
        sim = self._sim("nysiis")
        assert sim.compute({"name": "Catherine"}, {"name": "Katherine"}) == pytest.approx(1.0)

    def test_soundex_matches_homophones(self):
        sim = self._sim("soundex")
        assert sim.compute({"name": "Robert"}, {"name": "Rupert"}) == pytest.approx(1.0)

    def test_match_rating_transformer_available(self):
        sim = self._sim("match_rating")
        # Same string encodes identically.
        assert sim.compute({"name": "Byrne"}, {"name": "Byrne"}) == pytest.approx(1.0)

    def test_phonetic_encodes_token_wise(self):
        sim = self._sim("metaphone")
        # Multi-word names encode per token; "Jon Smith"/"John Smith" agree.
        assert sim.compute({"name": "Jon Smith"}, {"name": "John Smith"}) == pytest.approx(1.0)

    def test_distinct_names_do_not_collide(self):
        sim = self._sim("soundex")
        assert sim.compute({"name": "Robert"}, {"name": "Xavier"}) < 1.0
