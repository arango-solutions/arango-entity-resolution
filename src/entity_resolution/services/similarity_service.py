"""
Similarity Service for Entity Resolution (v1.x Legacy)

[WARN]?  DEPRECATED: This service is deprecated and will be removed in v3.0.
Use v2.0 BatchSimilarityService instead for better performance.

Note: This is the legacy v1.x SimilarityService. For v2.0+, use:
- BatchSimilarityService for batch document fetching and similarity computation

Handles similarity computation using:
- Fellegi-Sunter probabilistic framework
- ArangoDB native similarity functions
- Python-based implementation
"""

import warnings
import math
from typing import Dict, List, Any, Optional
from .base_service import BaseEntityResolutionService, Config
from ..utils.algorithms import validate_email, validate_phone, validate_zip_code, validate_state


class SimilarityService(BaseEntityResolutionService):
    """
    Similarity computation service using Fellegi-Sunter framework
    
    [WARN]?  DEPRECATED: Use BatchSimilarityService instead.
    This service will be removed in v3.0.
    
    Can work in two modes:
    1. Foxx service mode: Uses ArangoDB native similarity functions
    2. Python mode: Fallback implementation with Python similarity functions
    """
    
    def __init__(self, config: Optional[Config] = None):
        warnings.warn(
            "SimilarityService is deprecated and will be removed in v3.0. "
            "Use BatchSimilarityService instead for better performance with batch document fetching. "
            "See docs/guides/MIGRATION_GUIDE_V3.md for migration instructions.",
            DeprecationWarning,
            stacklevel=2
        )
        super().__init__(config)
        
    def _get_service_name(self) -> str:
        return "similarity"
    
    def _test_service_endpoints(self) -> bool:
        """Test if similarity Foxx endpoints are available"""
        try:
            result = self._make_foxx_request("similarity/compute", method="GET")
            return result.get("success", False) or "error" not in result or "404" not in str(result.get("error", ""))
        except Exception:
            return False
    
    def compute_similarity(self, doc_a: Dict[str, Any], doc_b: Dict[str, Any],
                          field_weights: Optional[Dict[str, Any]] = None,
                          include_details: bool = False) -> Dict[str, Any]:
        """
        Compute similarity score between two documents
        
        Args:
            doc_a: First document
            doc_b: Second document  
            field_weights: Field-specific weights for Fellegi-Sunter
            include_details: Whether to include detailed field scores
            
        Returns:
            Similarity computation results
        """
        field_weights = field_weights or self.get_field_weights()
        
        # v2.0: Python-only implementation
        return self._compute_via_python(doc_a, doc_b, field_weights, include_details)
    
    def compute_batch_similarity(self, pairs: List[Dict[str, Any]],
                                field_weights: Optional[Dict[str, Any]] = None,
                                include_details: bool = False) -> Dict[str, Any]:
        """
        Compute similarity for multiple document pairs
        
        Args:
            pairs: List of document pairs to compare
            field_weights: Field-specific weights
            include_details: Whether to include detailed scores
            
        Returns:
            Batch similarity results
        """
        field_weights = field_weights or self.get_field_weights()
        
        # v2.0: Python-only implementation
        return self._compute_batch_via_python(pairs, field_weights, include_details)
    
    def get_default_field_weights(self) -> Dict[str, Any]:
        """Get default Fellegi-Sunter field weights"""
        return {
            # Name fields - n-gram similarity
            "name_ngram": {
                "m_prob": 0.9,
                "u_prob": 0.01,
                "threshold": 0.7,
                "importance": 1.0
            },
            "first_name_ngram": {
                "m_prob": 0.85,
                "u_prob": 0.02,
                "threshold": 0.7,
                "importance": 0.8
            },
            "last_name_ngram": {
                "m_prob": 0.9,
                "u_prob": 0.015,
                "threshold": 0.7,
                "importance": 1.0
            },
            
            # Name fields - Levenshtein similarity
            "first_name_levenshtein": {
                "m_prob": 0.8,
                "u_prob": 0.05,
                "threshold": 0.6,
                "importance": 0.7
            },
            "last_name_levenshtein": {
                "m_prob": 0.85,
                "u_prob": 0.03,
                "threshold": 0.6,
                "importance": 0.9
            },
            
            # Name fields - Jaro-Winkler similarity
            "first_name_jaro_winkler": {
                "m_prob": 0.88,
                "u_prob": 0.03,
                "threshold": 0.75,
                "importance": 0.9
            },
            "last_name_jaro_winkler": {
                "m_prob": 0.92,
                "u_prob": 0.02,
                "threshold": 0.75,
                "importance": 1.1
            },
            
            # Name fields - Phonetic similarity
            "first_name_phonetic": {
                "m_prob": 0.75,
                "u_prob": 0.08,
                "threshold": 1.0,
                "importance": 0.6
            },
            "last_name_phonetic": {
                "m_prob": 0.8,
                "u_prob": 0.06,
                "threshold": 1.0,
                "importance": 0.7
            },
            
            # Address fields
            "address_ngram": {
                "m_prob": 0.8,
                "u_prob": 0.03,
                "threshold": 0.6,
                "importance": 0.8
            },
            "city_ngram": {
                "m_prob": 0.9,
                "u_prob": 0.05,
                "threshold": 0.8,
                "importance": 0.6
            },
            
            # Exact match fields
            "email_exact": {
                "m_prob": 0.95,
                "u_prob": 0.001,
                "threshold": 1.0,
                "importance": 1.2
            },
            "phone_exact": {
                "m_prob": 0.9,
                "u_prob": 0.005,
                "threshold": 1.0,
                "importance": 1.1
            },
            
            # Company field
            "company_ngram": {
                "m_prob": 0.8,
                "u_prob": 0.02,
                "threshold": 0.7,
                "importance": 0.7
            },
            
            # Global thresholds
            "global": {
                "upper_threshold": 3.5,   # Clear match (increased for more fields)
                "lower_threshold": -1.5,  # Clear non-match
                # Scoring method: "weighted_heuristic" (default, importance-weighted,
                # heuristic confidence) or "fellegi_sunter" (pure LLR sum, calibrated
                # posterior confidence). Default kept for behavior stability until
                # EM-estimated parameters land (Phase 1).
                "scoring_method": "weighted_heuristic",
                # Prior match probability used only by fellegi_sunter to convert the
                # LLR sum into a posterior (default 0.5 = neutral prior).
                "match_prior": 0.5,
            }
        }
    
    def configure_field_weights(self, custom_weights: Dict[str, Any]) -> None:
        """
        Configure custom field weights for similarity computation
        
        Args:
            custom_weights: Custom field weights to override defaults
        """
        default_weights = self.get_default_field_weights()
        
        # Deep merge custom weights with defaults
        for field, weights in custom_weights.items():
            if field in default_weights:
                if isinstance(weights, dict) and isinstance(default_weights[field], dict):
                    default_weights[field].update(weights)
                else:
                    default_weights[field] = weights
            else:
                default_weights[field] = weights
        
        self._custom_field_weights = default_weights
        self.logger.info(f"Configured custom field weights for {len(custom_weights)} fields")
    
    def get_field_weights(self) -> Dict[str, Any]:
        """Get currently configured field weights (custom or default)"""
        return getattr(self, '_custom_field_weights', self.get_default_field_weights())
    
    def _compute_via_foxx(self, doc_a: Dict[str, Any], doc_b: Dict[str, Any],
                         field_weights: Dict[str, Any], include_details: bool) -> Dict[str, Any]:
        """Compute similarity via Foxx service"""
        payload = {
            "docA": doc_a,
            "docB": doc_b,
            "fieldWeights": field_weights,
            "includeDetails": include_details
        }
        
        result = self._make_foxx_request("similarity/compute", method="POST", payload=payload)
        
        if result.get("success", True):
            return result.get("similarity", result)
        else:
            return self._handle_service_error("Foxx similarity computation", Exception(result.get("error", "Unknown error")))
    
    def _compute_via_python(self, doc_a: Dict[str, Any], doc_b: Dict[str, Any],
                           field_weights: Dict[str, Any], include_details: bool) -> Dict[str, Any]:
        """Compute similarity via Python implementation"""
        try:
            # Compute individual field similarities
            similarities = {}
            
            # Name comparisons
            full_name_a = f"{doc_a.get('first_name', '')} {doc_a.get('last_name', '')}".strip()
            full_name_b = f"{doc_b.get('first_name', '')} {doc_b.get('last_name', '')}".strip()
            
            if full_name_a and full_name_b:
                similarities["name_ngram"] = self._ngram_similarity(full_name_a, full_name_b)
            
            # Individual name fields
            if doc_a.get('first_name') and doc_b.get('first_name'):
                similarities["first_name_ngram"] = self._ngram_similarity(
                    doc_a['first_name'], doc_b['first_name'])
                similarities["first_name_levenshtein"] = self._normalized_levenshtein(
                    doc_a['first_name'], doc_b['first_name'])
                similarities["first_name_jaro_winkler"] = self._jaro_winkler_similarity(
                    doc_a['first_name'], doc_b['first_name'])
                similarities["first_name_phonetic"] = self._phonetic_similarity(
                    doc_a['first_name'], doc_b['first_name'])
            
            if doc_a.get('last_name') and doc_b.get('last_name'):
                similarities["last_name_ngram"] = self._ngram_similarity(
                    doc_a['last_name'], doc_b['last_name'])
                similarities["last_name_levenshtein"] = self._normalized_levenshtein(
                    doc_a['last_name'], doc_b['last_name'])
                similarities["last_name_jaro_winkler"] = self._jaro_winkler_similarity(
                    doc_a['last_name'], doc_b['last_name'])
                similarities["last_name_phonetic"] = self._phonetic_similarity(
                    doc_a['last_name'], doc_b['last_name'])
            
            # Address comparisons
            if doc_a.get('address') and doc_b.get('address'):
                similarities["address_ngram"] = self._ngram_similarity(
                    doc_a['address'], doc_b['address'])
            
            if doc_a.get('city') and doc_b.get('city'):
                similarities["city_ngram"] = self._ngram_similarity(
                    doc_a['city'], doc_b['city'])
            
            # Exact match fields
            similarities["email_exact"] = 1.0 if (doc_a.get('email') and doc_b.get('email') and 
                                                 doc_a['email'].lower() == doc_b['email'].lower()) else 0.0
            similarities["phone_exact"] = 1.0 if (doc_a.get('phone') and doc_b.get('phone') and 
                                                 doc_a['phone'] == doc_b['phone']) else 0.0
            
            # Company comparison
            if doc_a.get('company') and doc_b.get('company'):
                similarities["company_ngram"] = self._ngram_similarity(
                    doc_a['company'], doc_b['company'])
            
            # Score via the configured method (weighted_heuristic by default)
            result = self._score_pair(similarities, field_weights, include_details)

            return result
            
        except Exception as e:
            self.logger.error(f"Python similarity computation failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _compute_batch_via_foxx(self, pairs: List[Dict[str, Any]],
                               field_weights: Dict[str, Any], include_details: bool) -> Dict[str, Any]:
        """Compute batch similarity via Foxx service"""
        try:
            url = self.config.get_foxx_service_url("similarity/batch")
            
            payload = {
                "pairs": pairs,
                "fieldWeights": field_weights,
                "includeDetails": include_details
            }
            
            response = requests.post(
                url,
                auth=self.config.get_auth_tuple(),
                json=payload,
                timeout=self.config.er.foxx_timeout * 2  # Longer timeout for batch
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "error": f"Foxx service returned {response.status_code}"}
                
        except Exception as e:
            self.logger.error(f"Foxx batch similarity computation failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _compute_batch_via_python(self, pairs: List[Dict[str, Any]],
                                 field_weights: Dict[str, Any], include_details: bool) -> Dict[str, Any]:
        """Compute batch similarity via Python implementation"""
        try:
            results = []
            
            for i, pair in enumerate(pairs):
                doc_a = pair.get("docA") or pair.get("record_a")
                doc_b = pair.get("docB") or pair.get("record_b")
                
                if not doc_a or not doc_b:
                    results.append({
                        "success": False,
                        "error": f"Missing documents in pair {i}",
                        "pair_index": i
                    })
                    continue
                
                similarity = self._compute_via_python(doc_a, doc_b, field_weights, include_details)
                similarity["pair_index"] = i
                results.append(similarity)
            
            successful_results = [r for r in results if r.get("success", True)]
            
            return {
                "success": True,
                "method": "python",
                "results": results,
                "statistics": {
                    "total_pairs": len(pairs),
                    "successful_pairs": len(successful_results),
                    "failed_pairs": len(pairs) - len(successful_results),
                    "average_score": sum(r.get("total_score", 0) for r in successful_results) / len(successful_results) if successful_results else 0
                }
            }
            
        except Exception as e:
            self.logger.error(f"Python batch similarity computation failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _ngram_similarity(self, str1: str, str2: str, n: int = 3) -> float:
        """Calculate n-gram similarity between two strings"""
        if not str1 or not str2:
            return 0.0
        
        str1 = str1.lower().strip()
        str2 = str2.lower().strip()
        
        if str1 == str2:
            return 1.0
        
        # Generate n-grams
        ngrams1 = set(str1[i:i+n] for i in range(len(str1)-n+1))
        ngrams2 = set(str2[i:i+n] for i in range(len(str2)-n+1))
        
        if not ngrams1 or not ngrams2:
            return 0.0
        
        intersection = len(ngrams1.intersection(ngrams2))
        union = len(ngrams1.union(ngrams2))
        
        return intersection / union if union > 0 else 0.0
    
    def _normalized_levenshtein(self, str1: str, str2: str) -> float:
        """Calculate normalized Levenshtein distance (1 - distance/max_length)"""
        if not str1 or not str2:
            return 0.0
        
        if str1 == str2:
            return 1.0
        
        distance = self._levenshtein_distance(str1, str2)
        max_length = max(len(str1), len(str2))
        
        return 1 - (distance / max_length) if max_length > 0 else 0.0
    
    def _levenshtein_distance(self, str1: str, str2: str) -> int:
        """Calculate Levenshtein distance between two strings"""
        if not str1:
            return len(str2)
        if not str2:
            return len(str1)
        
        # Create distance matrix
        matrix = [[0] * (len(str2) + 1) for _ in range(len(str1) + 1)]
        
        # Initialize first row and column
        for i in range(len(str1) + 1):
            matrix[i][0] = i
        for j in range(len(str2) + 1):
            matrix[0][j] = j
        
        # Fill matrix
        for i in range(1, len(str1) + 1):
            for j in range(1, len(str2) + 1):
                if str1[i-1] == str2[j-1]:
                    cost = 0
                else:
                    cost = 1
                
                matrix[i][j] = min(
                    matrix[i-1][j] + 1,      # deletion
                    matrix[i][j-1] + 1,      # insertion
                    matrix[i-1][j-1] + cost  # substitution
                )
        
        return matrix[len(str1)][len(str2)]
    
    def _jaro_winkler_similarity(self, str1: str, str2: str, prefix_scale: float = 0.1) -> float:
        """Calculate Jaro-Winkler similarity between two strings"""
        if not str1 or not str2:
            return 0.0
        
        str1 = str1.lower().strip()
        str2 = str2.lower().strip()
        
        if str1 == str2:
            return 1.0
        
        # Calculate Jaro similarity
        jaro_sim = self._jaro_similarity(str1, str2)
        
        if jaro_sim < 0.7:  # Standard threshold for applying Winkler prefix bonus
            return jaro_sim
        
        # Calculate common prefix length (up to 4 characters)
        prefix_len = 0
        for i in range(min(len(str1), len(str2), 4)):
            if str1[i] == str2[i]:
                prefix_len += 1
            else:
                break
        
        # Apply Winkler modification
        return jaro_sim + (prefix_len * prefix_scale * (1 - jaro_sim))
    
    def _jaro_similarity(self, str1: str, str2: str) -> float:
        """Calculate Jaro similarity between two strings"""
        if not str1 or not str2:
            return 0.0
        
        if str1 == str2:
            return 1.0
        
        len1, len2 = len(str1), len(str2)
        match_window = max(len1, len2) // 2 - 1
        match_window = max(0, match_window)
        
        str1_matches = [False] * len1
        str2_matches = [False] * len2
        
        matches = 0
        transpositions = 0
        
        # Find matches
        for i in range(len1):
            start = max(0, i - match_window)
            end = min(i + match_window + 1, len2)
            
            for j in range(start, end):
                if str2_matches[j] or str1[i] != str2[j]:
                    continue
                str1_matches[i] = True
                str2_matches[j] = True
                matches += 1
                break
        
        if matches == 0:
            return 0.0
        
        # Count transpositions
        k = 0
        for i in range(len1):
            if not str1_matches[i]:
                continue
            while not str2_matches[k]:
                k += 1
            if str1[i] != str2[k]:
                transpositions += 1
            k += 1
        
        jaro = (matches / len1 + matches / len2 + (matches - transpositions / 2) / matches) / 3
        return jaro
    
    def _phonetic_similarity(self, str1: str, str2: str) -> float:
        """Calculate phonetic similarity using Soundex algorithm"""
        if not str1 or not str2:
            return 0.0
        
        soundex1 = self._soundex(str1)
        soundex2 = self._soundex(str2)
        
        return 1.0 if soundex1 == soundex2 else 0.0
    
    def _soundex(self, name: str) -> str:
        """Generate Soundex code for a name"""
        if not name:
            return "0000"
        
        name = name.upper().strip()
        if not name:
            return "0000"
        
        # Soundex mapping
        soundex_map = {
            'B': '1', 'F': '1', 'P': '1', 'V': '1',
            'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
            'D': '3', 'T': '3',
            'L': '4',
            'M': '5', 'N': '5',
            'R': '6'
        }
        
        # Keep first letter
        result = name[0]
        
        # Process remaining characters
        for char in name[1:]:
            if char in soundex_map:
                code = soundex_map[char]
                # Don't add consecutive duplicates
                if not result or result[-1] != code:
                    result += code
        
        # Remove vowels and H, W, Y (except first letter)
        if len(result) > 1:
            result = result[0] + ''.join(c for c in result[1:] if c.isdigit())
        
        # Pad with zeros or truncate to 4 characters
        result = (result + "000")[:4]
        
        return result

    def _score_pair(self, similarities: Dict[str, float],
                    field_weights: Dict[str, Any],
                    include_details: bool = False) -> Dict[str, Any]:
        """Dispatch scoring by configured method.

        ``field_weights["global"]["scoring_method"]`` selects:
        - ``"weighted_heuristic"`` (default): importance-weighted average of
          per-field log-likelihood ratios. NOT a calibrated probability; the
          ``confidence`` it returns is a heuristic in [0,1].
        - ``"fellegi_sunter"``: a pure Fellegi-Sunter log-likelihood-ratio sum
          (no importance multiplier) with a calibrated posterior ``confidence``.
        """
        method = field_weights.get("global", {}).get("scoring_method", "weighted_heuristic")
        if method == "fellegi_sunter":
            return self._compute_fellegi_sunter_score(similarities, field_weights, include_details)
        return self._compute_weighted_heuristic_score(similarities, field_weights, include_details)

    def _field_llrs(self, similarities: Dict[str, float],
                    field_weights: Dict[str, Any]):
        """Per-field Fellegi-Sunter log-likelihood ratios.

        Returns ``(field_scores, agreeing_count)`` where each field score holds
        the (natural-log) LLR contributed by that field's agreement state.
        """
        field_scores = {}
        agreeing = 0
        for field, sim_value in similarities.items():
            if field not in field_weights:
                continue
            weights = field_weights[field]
            threshold = weights.get("threshold", 0.5)
            agreement = sim_value >= threshold

            m_prob = max(min(weights.get("m_prob", 0.8), 0.999), 0.001)
            u_prob = max(min(weights.get("u_prob", 0.05), 0.999), 0.001)

            if agreement:
                llr = math.log(m_prob / u_prob)
                agreeing += 1
            else:
                llr = math.log((1 - m_prob) / (1 - u_prob))

            field_scores[field] = {
                "similarity": sim_value,
                "agreement": agreement,
                "weight": llr,
                "threshold": threshold,
                "m_prob": m_prob,
                "u_prob": u_prob,
            }
        return field_scores, agreeing

    def _compute_fellegi_sunter_score(self, similarities: Dict[str, float],
                                     field_weights: Dict[str, Any],
                                     include_details: bool = False) -> Dict[str, Any]:
        """Pure Fellegi-Sunter scoring with a calibrated posterior.

        The match score is the unweighted sum of per-field log-likelihood
        ratios (true Fellegi-Sunter — no importance multiplier). ``confidence``
        is the posterior match probability ``P(match | gamma)`` derived from
        that LLR sum and a configurable prior, so it is a real probability in
        [0,1] and monotone in the score.
        """
        field_scores, agreeing = self._field_llrs(similarities, field_weights)
        total_score = sum(f["weight"] for f in field_scores.values())

        global_weights = field_weights.get("global", {})
        upper_threshold = global_weights.get("upper_threshold", 2.0)
        lower_threshold = global_weights.get("lower_threshold", -1.0)

        # Posterior odds = prior odds * likelihood ratio; in log space the
        # log-LR is exactly total_score, so logit(posterior) = logit(prior) +
        # total_score and the posterior is its logistic transform.
        prior = max(min(global_weights.get("match_prior", 0.5), 0.999999), 1e-6)
        prior_logit = math.log(prior / (1 - prior))
        confidence = 1.0 / (1.0 + math.exp(-(total_score + prior_logit)))

        is_match = total_score > upper_threshold
        is_possible_match = lower_threshold < total_score <= upper_threshold

        result = {
            "success": True,
            "total_score": total_score,
            "normalized_score": total_score,
            "is_match": is_match,
            "is_possible_match": is_possible_match,
            "confidence": confidence,
            "confidence_is_calibrated": True,
            "decision": "match" if is_match else ("possible_match" if is_possible_match else "non_match"),
            "method": "fellegi_sunter",
        }

        if include_details:
            result["field_scores"] = field_scores
            result["thresholds"] = global_weights
            result["match_prior"] = prior
            result["statistics"] = {
                "fields_compared": len(field_scores),
                "agreeing_fields": agreeing,
                "total_weight": len(field_scores),
            }

        return result

    def _compute_weighted_heuristic_score(self, similarities: Dict[str, float],
                                          field_weights: Dict[str, Any],
                                          include_details: bool = False) -> Dict[str, Any]:
        """Importance-weighted heuristic score (legacy default behavior).

        Per-field LLRs are averaged using each field's ``importance`` as a
        weight. This is NOT the Fellegi-Sunter model and the ``confidence`` it
        returns is a heuristic distance-from-threshold value, NOT a calibrated
        probability — consumers must not treat it as one (see
        ``confidence_is_calibrated``).
        """
        field_scores, agreeing = self._field_llrs(similarities, field_weights)

        total_score = 0.0
        total_weight = 0.0
        for field, fs in field_scores.items():
            importance = field_weights[field].get("importance", 1.0)
            total_score += fs["weight"] * importance
            total_weight += importance

        normalized_score = total_score / total_weight if total_weight > 0 else 0

        global_weights = field_weights.get("global", {})
        upper_threshold = global_weights.get("upper_threshold", 2.0)
        lower_threshold = global_weights.get("lower_threshold", -1.0)

        is_match = total_score > upper_threshold
        is_possible_match = total_score > lower_threshold and total_score <= upper_threshold

        # Heuristic confidence based on distance from thresholds (NOT a probability).
        if is_match:
            confidence = min(0.5 + (total_score - upper_threshold) / (upper_threshold * 2), 1.0)
        elif is_possible_match:
            confidence = 0.3 + 0.4 * (total_score - lower_threshold) / (upper_threshold - lower_threshold)
        else:
            confidence = max(0.1 * (total_score - lower_threshold) / abs(lower_threshold), 0.0)

        result = {
            "success": True,
            "total_score": total_score,
            "normalized_score": normalized_score,
            "is_match": is_match,
            "is_possible_match": is_possible_match,
            "confidence": confidence,
            "confidence_is_calibrated": False,
            "decision": "match" if is_match else ("possible_match" if is_possible_match else "non_match"),
            "method": "weighted_heuristic",
        }

        if include_details:
            result["field_scores"] = field_scores
            result["thresholds"] = global_weights
            result["statistics"] = {
                "fields_compared": len(field_scores),
                "agreeing_fields": agreeing,
                "total_weight": total_weight,
            }

        return result
