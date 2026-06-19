"""
Weighted multi-field similarity computation.

This module provides a reusable component for computing weighted similarity
scores across multiple fields between two documents. It supports multiple
similarity algorithms and configurable field weights.
"""

from typing import Dict, Any, Callable, Optional, Union
import logging
import re

# Similarity algorithms
try:
    import jellyfish
    JELLYFISH_AVAILABLE = True
except ImportError:
    JELLYFISH_AVAILABLE = False

try:
    import Levenshtein
    LEVENSHTEIN_AVAILABLE = True
except ImportError:
    LEVENSHTEIN_AVAILABLE = False


class WeightedFieldSimilarity:
    """
    Compute weighted similarity across multiple fields.
    
    This class provides a reusable component for computing weighted similarity
    scores between two documents based on multiple fields. It supports:
    - Multiple similarity algorithms (Jaro-Winkler, Levenshtein, Jaccard)
    - Configurable field weights
    - Null value handling strategies
    - String normalization options
    
    Example:
        ```python
        similarity = WeightedFieldSimilarity(
            field_weights={'name': 0.4, 'address': 0.3, 'city': 0.3},
            algorithm='jaro_winkler',
            handle_nulls='skip'
        )
        
        doc1 = {'name': 'John Smith', 'address': '123 Main St', 'city': 'Boston'}
        doc2 = {'name': 'Jon Smith', 'address': '123 Main Street', 'city': 'Boston'}
        
        score = similarity.compute(doc1, doc2)
        # Returns: 0.92 (high similarity)
        ```
    """
    
    # Available similarity algorithms
    ALGORITHMS = {
        'jaro_winkler': 'jaro_winkler',
        'levenshtein': 'levenshtein',
        'jaccard': 'jaccard'
    }
    
    # Null handling strategies
    NULL_STRATEGIES = {'skip', 'zero', 'default'}
    VALID_TRANSFORMERS = {
        'strip',
        'lower',
        'upper',
        'collapse_whitespace',
        'remove_punctuation',
        'digits_only',
        'alphanumeric_only',
        'e164',
        'metaphone',
        'nysiis',
        'soundex',
        'match_rating',
        'state_code',
        'street_suffix',
        'company_suffix',
    }
    
    def __init__(
        self,
        field_weights: Dict[str, float],
        algorithm: Union[str, Callable[[str, str], float]] = "jaro_winkler",
        normalize: bool = True,
        handle_nulls: str = "skip",
        normalization_config: Optional[Dict[str, Any]] = None,
        field_transformers: Optional[Dict[str, Union[str, list[Union[str, Dict[str, Any]]]]]] = None,
    ):
        """
        Initialize weighted field similarity.
        
        Args:
            field_weights: Dictionary mapping field names to their weights.
                Example: {'name': 0.4, 'address': 0.3, 'city': 0.3}
                Weights will be normalized to sum to 1.0 if normalize=True.
            algorithm: Similarity algorithm to use:
                - "jaro_winkler" (default, best for names, requires jellyfish)
                - "levenshtein" (edit distance, requires python-Levenshtein)
                - "jaccard" (set-based similarity, built-in)
                - Custom callable: (str1, str2) -> float (0.0-1.0)
            normalize: Whether to normalize weights to sum to 1.0. Default True.
            handle_nulls: How to handle missing/null values:
                - "skip" (default): Skip null fields, don't count in weight
                - "zero": Count weight but contribute 0.0 to score
                - "default": Use default value (not yet implemented)
            normalization_config: String normalization options:
                {
                    "strip": True,              # Remove leading/trailing whitespace
                    "case": "upper",            # "upper", "lower", or None
                    "remove_punctuation": False,
                    "remove_extra_whitespace": True
                }
                Default: {"strip": True, "case": "upper", "remove_extra_whitespace": True}
            field_transformers: Optional per-field transformer chains applied before
                normalization_config. Example:
                {
                    "phone": ["digits_only"],
                    "state": ["state_code"],
                    "name": ["strip", "collapse_whitespace"]
                }
        
        Raises:
            ValueError: If configuration is invalid
            ImportError: If required algorithm library not available
        """
        if not field_weights:
            raise ValueError("field_weights cannot be empty")
        
        if handle_nulls not in self.NULL_STRATEGIES:
            raise ValueError(
                f"handle_nulls must be one of {self.NULL_STRATEGIES}, "
                f"got: {handle_nulls}"
            )
        
        self.field_weights = field_weights
        self.normalize = normalize
        self.handle_nulls = handle_nulls
        
        # Normalize weights if requested
        if normalize:
            total = sum(field_weights.values())
            if total == 0:
                raise ValueError("Field weights cannot all be zero")
            self.field_weights = {
                k: v / total
                for k, v in field_weights.items()
            }
        
        # Set default normalization config
        default_norm = {
            "strip": True,
            "case": "upper",
            "remove_extra_whitespace": True,
            "remove_punctuation": False
        }
        self.normalization_config = {**default_norm, **(normalization_config or {})}
        self.field_transformers = self._normalize_field_transformers(field_transformers or {})
        
        # Set up similarity algorithm
        self.similarity_fn = self._setup_algorithm(algorithm)
        self.algorithm_name = algorithm if isinstance(algorithm, str) else "custom"
        
        # Initialize logger
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def compute(
        self,
        doc1: Dict[str, Any],
        doc2: Dict[str, Any]
    ) -> float:
        """
        Compute weighted similarity between two documents.
        
        Args:
            doc1: First document dictionary
            doc2: Second document dictionary
        
        Returns:
            Weighted similarity score between 0.0 and 1.0
        
        Example:
            ```python
            doc1 = {'name': 'John Smith', 'address': '123 Main St'}
            doc2 = {'name': 'Jon Smith', 'address': '123 Main Street'}
            score = similarity.compute(doc1, doc2)
            # Returns: 0.87
            ```
        """
        total_score = 0.0
        total_weight = 0.0
        
        for field, weight in self.field_weights.items():
            val1 = doc1.get(field)
            val2 = doc2.get(field)
            
            # Handle nulls
            if val1 is None or val2 is None:
                if self.handle_nulls == "skip":
                    continue
                elif self.handle_nulls == "zero":
                    total_weight += weight
                    # Don't add to total_score (contributes 0.0)
                    continue
                # else: default value handling could go here in future
        
            # Normalize values
            val1_norm = self._normalize_value(field, str(val1) if val1 is not None else '')
            val2_norm = self._normalize_value(field, str(val2) if val2 is not None else '')
            
            if not val1_norm or not val2_norm:
                if self.handle_nulls == "skip":
                    continue
                elif self.handle_nulls == "zero":
                    total_weight += weight
                    continue
            
            # Compute field similarity
            try:
                score = self.similarity_fn(val1_norm, val2_norm)
                total_score += score * weight
                total_weight += weight
            except Exception as e:
                # Log but don't fail
                self.logger.warning(
                    f"Similarity computation failed for field '{field}': {e}",
                    exc_info=True
                )
                continue
        
        return round(total_score / total_weight, 4) if total_weight > 0 else 0.0
    
    def compute_detailed(
        self,
        doc1: Dict[str, Any],
        doc2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute detailed per-field similarity scores.
        
        Args:
            doc1: First document dictionary
            doc2: Second document dictionary
        
        Returns:
            Dictionary with detailed scores:
            {
                "overall_score": 0.87,
                "field_scores": {
                    "name": 0.95,
                    "address": 0.82,
                    "city": 0.78
                },
                "weighted_score": 0.87
            }
        """
        field_scores = {}
        total_score = 0.0
        total_weight = 0.0
        
        for field, weight in self.field_weights.items():
            val1 = doc1.get(field)
            val2 = doc2.get(field)
            
            # Handle nulls
            if val1 is None or val2 is None:
                if self.handle_nulls == "skip":
                    field_scores[field] = None
                    continue
                elif self.handle_nulls == "zero":
                    field_scores[field] = 0.0
                    total_weight += weight
                    continue
            
            # Normalize values
            val1_norm = self._normalize_value(field, str(val1) if val1 is not None else '')
            val2_norm = self._normalize_value(field, str(val2) if val2 is not None else '')
            
            if not val1_norm or not val2_norm:
                if self.handle_nulls == "skip":
                    field_scores[field] = None
                    continue
                elif self.handle_nulls == "zero":
                    field_scores[field] = 0.0
                    total_weight += weight
                    continue
            
            # Compute field similarity
            try:
                score = self.similarity_fn(val1_norm, val2_norm)
                field_scores[field] = round(score, 4)
                total_score += score * weight
                total_weight += weight
            except Exception as e:
                self.logger.warning(
                    f"Similarity computation failed for field '{field}': {e}",
                    exc_info=True
                )
                field_scores[field] = 0.0
                total_weight += weight
        
        weighted_score = round(total_score / total_weight, 4) if total_weight > 0 else 0.0
        
        return {
            'overall_score': weighted_score,
            'field_scores': field_scores,
            'weighted_score': weighted_score
        }
    
    def _normalize_value(self, field: str, value: str) -> str:
        """
        Normalize a string value according to configuration.
        
        Args:
            field: Field name being transformed
            value: Input string
        
        Returns:
            Normalized string
        """
        value = self._apply_field_transformers(field, value)

        if self.normalization_config.get('strip'):
            value = value.strip()
        
        case = self.normalization_config.get('case')
        if case == 'upper':
            value = value.upper()
        elif case == 'lower':
            value = value.lower()
        
        if self.normalization_config.get('remove_extra_whitespace'):
            value = ' '.join(value.split())
        
        if self.normalization_config.get('remove_punctuation'):
            value = self._remove_punctuation(value)
        
        return value

    def _normalize_field_transformers(
        self,
        field_transformers: Dict[str, Union[str, list[Union[str, Dict[str, Any]]]]],
    ) -> Dict[str, list[Dict[str, Any]]]:
        """Normalize transformer config into a predictable internal shape."""
        normalized: Dict[str, list[Dict[str, Any]]] = {}
        for field, spec in field_transformers.items():
            if isinstance(spec, (str, dict)):
                items = [spec]
            elif isinstance(spec, list):
                items = spec
            else:
                raise ValueError(f"field_transformers[{field!r}] must be a string, dict, or list")

            normalized[field] = []
            for item in items:
                if isinstance(item, str):
                    name = item
                    params: Dict[str, Any] = {}
                elif isinstance(item, dict):
                    name = item.get("name")
                    if not isinstance(name, str) or not name:
                        raise ValueError(
                            f"field_transformers[{field!r}] dict entries must include a non-empty 'name'"
                        )
                    params = {k: v for k, v in item.items() if k != "name"}
                else:
                    raise ValueError(
                        f"field_transformers[{field!r}] entries must be strings or dicts"
                    )

                if name not in self.VALID_TRANSFORMERS:
                    opts = ", ".join(sorted(self.VALID_TRANSFORMERS))
                    raise ValueError(f"Unknown transformer: {name}. Supported: {opts}")
                normalized[field].append({"name": name, "params": params})
        return normalized

    def _apply_field_transformers(self, field: str, value: str) -> str:
        """Apply configured field-specific transformers in order."""
        transformed = value
        for transformer in self.field_transformers.get(field, []):
            transformed = self._apply_transformer(
                transformer["name"],
                transformed,
                transformer["params"],
            )
        return transformed

    def _apply_transformer(self, name: str, value: str, params: Dict[str, Any]) -> str:
        """Apply a single named transformer."""
        if name == "strip":
            return value.strip()
        if name == "lower":
            return value.lower()
        if name == "upper":
            return value.upper()
        if name == "collapse_whitespace":
            return " ".join(value.split())
        if name == "remove_punctuation":
            return self._remove_punctuation(value)
        if name == "digits_only":
            return "".join(ch for ch in value if ch.isdigit())
        if name == "alphanumeric_only":
            return "".join(ch for ch in value if ch.isalnum())
        if name == "e164":
            return self._normalize_e164(value)
        if name in ("metaphone", "nysiis", "soundex", "match_rating"):
            if not JELLYFISH_AVAILABLE:
                raise ImportError(f"jellyfish library required for {name} transformer")
            # Phonetic encoders compare best per-token (so multi-word names like
            # "John Smith" encode token-wise rather than as one blob).
            fn = {
                "metaphone": jellyfish.metaphone,
                "nysiis": jellyfish.nysiis,
                "soundex": jellyfish.soundex,
                "match_rating": jellyfish.match_rating_codex,
            }[name]
            tokens = value.split()
            if not tokens:
                return ""
            return " ".join(fn(tok) for tok in tokens)
        if name == "state_code":
            return self._normalize_state_code(value)
        if name == "street_suffix":
            return self._normalize_street_suffix(value)
        if name == "company_suffix":
            return self._normalize_company_suffix(value)
        raise ValueError(f"Unsupported transformer: {name}")

    @staticmethod
    def _remove_punctuation(value: str) -> str:
        """Remove punctuation characters from a string."""
        import string

        return value.translate(str.maketrans('', '', string.punctuation))

    def _normalize_e164(self, value: str) -> str:
        """Basic phone normalization for matching-oriented E.164 formatting."""
        digits = "".join(ch for ch in value if ch.isdigit())
        if not digits:
            return ""
        if len(digits) == 10:
            return f"+1{digits}"
        if len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        return f"+{digits}"

    def _normalize_state_code(self, value: str) -> str:
        """Normalize US state names/abbreviations to a two-letter code when known."""
        state_lookup = {
            "ALABAMA": "AL", "AL": "AL",
            "ALASKA": "AK", "AK": "AK",
            "ARIZONA": "AZ", "AZ": "AZ",
            "ARKANSAS": "AR", "AR": "AR",
            "CALIFORNIA": "CA", "CA": "CA",
            "COLORADO": "CO", "CO": "CO",
            "CONNECTICUT": "CT", "CT": "CT",
            "DELAWARE": "DE", "DE": "DE",
            "DISTRICT OF COLUMBIA": "DC", "DC": "DC",
            "FLORIDA": "FL", "FL": "FL",
            "GEORGIA": "GA", "GA": "GA",
            "HAWAII": "HI", "HI": "HI",
            "IDAHO": "ID", "ID": "ID",
            "ILLINOIS": "IL", "IL": "IL",
            "INDIANA": "IN", "IN": "IN",
            "IOWA": "IA", "IA": "IA",
            "KANSAS": "KS", "KS": "KS",
            "KENTUCKY": "KY", "KY": "KY",
            "LOUISIANA": "LA", "LA": "LA",
            "MAINE": "ME", "ME": "ME",
            "MARYLAND": "MD", "MD": "MD",
            "MASSACHUSETTS": "MA", "MA": "MA",
            "MICHIGAN": "MI", "MI": "MI",
            "MINNESOTA": "MN", "MN": "MN",
            "MISSISSIPPI": "MS", "MS": "MS",
            "MISSOURI": "MO", "MO": "MO",
            "MONTANA": "MT", "MT": "MT",
            "NEBRASKA": "NE", "NE": "NE",
            "NEVADA": "NV", "NV": "NV",
            "NEW HAMPSHIRE": "NH", "NH": "NH",
            "NEW JERSEY": "NJ", "NJ": "NJ",
            "NEW MEXICO": "NM", "NM": "NM",
            "NEW YORK": "NY", "NY": "NY",
            "NORTH CAROLINA": "NC", "NC": "NC",
            "NORTH DAKOTA": "ND", "ND": "ND",
            "OHIO": "OH", "OH": "OH",
            "OKLAHOMA": "OK", "OK": "OK",
            "OREGON": "OR", "OR": "OR",
            "PENNSYLVANIA": "PA", "PA": "PA",
            "RHODE ISLAND": "RI", "RI": "RI",
            "SOUTH CAROLINA": "SC", "SC": "SC",
            "SOUTH DAKOTA": "SD", "SD": "SD",
            "TENNESSEE": "TN", "TN": "TN",
            "TEXAS": "TX", "TX": "TX",
            "UTAH": "UT", "UT": "UT",
            "VERMONT": "VT", "VT": "VT",
            "VIRGINIA": "VA", "VA": "VA",
            "WASHINGTON": "WA", "WA": "WA",
            "WEST VIRGINIA": "WV", "WV": "WV",
            "WISCONSIN": "WI", "WI": "WI",
            "WYOMING": "WY", "WY": "WY",
        }
        normalized = self._remove_punctuation(value).strip().upper()
        normalized = " ".join(normalized.split())
        return state_lookup.get(normalized, normalized)

    def _normalize_street_suffix(self, value: str) -> str:
        """Normalize common street suffix variants.

        Uses the canonical suffix map from ``etl.normalizers`` (lowered for
        legacy compatibility with the similarity scorer which expects
        lowercase output).
        """
        from ..etl.normalizers import STREET_SUFFIX_MAP

        cleaned = self._remove_punctuation(value).strip()
        if not cleaned:
            return cleaned
        parts = cleaned.split()
        last = parts[-1].upper()
        if last in STREET_SUFFIX_MAP:
            parts[-1] = STREET_SUFFIX_MAP[last].lower()
        return " ".join(parts)

    def _normalize_company_suffix(self, value: str) -> str:
        """Normalize common company suffix variants."""
        suffix_map = {
            "CO": "company",
            "COMPANY": "company",
            "CORP": "corporation",
            "CORPORATION": "corporation",
            "INC": "incorporated",
            "INCORPORATED": "incorporated",
            "LLC": "llc",
            "LTD": "limited",
            "LIMITED": "limited",
        }
        cleaned = self._remove_punctuation(value).strip()
        if not cleaned:
            return cleaned
        parts = cleaned.split()
        last = parts[-1].upper()
        if last in suffix_map:
            parts[-1] = suffix_map[last]
        normalized = " ".join(parts)
        return re.sub(r"\s+", " ", normalized).strip()
    
    def _setup_algorithm(
        self,
        algorithm: Union[str, Callable[[str, str], float]]
    ) -> Callable[[str, str], float]:
        """
        Set up the similarity algorithm function.
        
        Args:
            algorithm: Algorithm name or callable
        
        Returns:
            Callable that computes similarity between two strings
        
        Raises:
            ValueError: If algorithm name is invalid
            ImportError: If required library not available
        """
        if callable(algorithm):
            return algorithm
        
        algorithm = algorithm.lower()
        
        if algorithm == "jaro_winkler":
            if not JELLYFISH_AVAILABLE:
                raise ImportError(
                    "jellyfish library required for jaro_winkler algorithm. "
                    "Install with: pip install jellyfish"
                )
            return jellyfish.jaro_winkler_similarity
        
        elif algorithm == "levenshtein":
            if not LEVENSHTEIN_AVAILABLE:
                raise ImportError(
                    "python-Levenshtein library required for levenshtein algorithm. "
                    "Install with: pip install python-Levenshtein"
                )
            # Normalize to 0-1 range
            return lambda s1, s2: 1.0 - (Levenshtein.distance(s1, s2) / max(len(s1), len(s2), 1))
        
        elif algorithm == "jaccard":
            return self._jaccard_similarity
        
        else:
            raise ValueError(
                f"Unknown algorithm: {algorithm}. "
                f"Supported: 'jaro_winkler', 'levenshtein', 'jaccard', or custom callable"
            )
    
    @staticmethod
    def _jaccard_similarity(str1: str, str2: str) -> float:
        """
        Compute Jaccard similarity between two strings (word-based).
        
        Args:
            str1: First string
            str2: Second string
        
        Returns:
            Jaccard similarity (0.0-1.0)
        """
        set1 = set(str1.split())
        set2 = set(str2.split())
        
        if not set1 and not set2:
            return 1.0
        if not set1 or not set2:
            return 0.0
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    def __repr__(self) -> str:
        """String representation."""
        fields_str = ', '.join(self.field_weights.keys())
        return (f"WeightedFieldSimilarity("
                f"algorithm='{self.algorithm_name}', "
                f"fields=[{fields_str}], "
                f"handle_nulls='{self.handle_nulls}')")

