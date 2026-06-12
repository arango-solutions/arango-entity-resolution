"""
DEPRECATED: Golden Record Service for Entity Resolution

This class was never wired to the database: record retrieval is a placeholder,
so ``generate_golden_records`` always produced empty results. It now raises
instead of silently returning garbage.

Use :class:`entity_resolution.services.golden_record_persistence_service.GoldenRecordPersistenceService`
instead — it persists golden records from cluster collections and supports
per-field survivorship strategies (field_voting, most_complete, most_recent,
source_priority).
"""

import json
import warnings
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter
from datetime import datetime

from ..utils.config import Config, get_config
from ..utils.logging import get_logger


class GoldenRecordService:
    """
    DEPRECATED golden record generation service.

    The end-to-end path (``generate_golden_records``) raises
    NotImplementedError because record retrieval was never implemented.
    Use ``GoldenRecordPersistenceService`` instead. The field-level
    quality/validation helpers remain functional.
    """

    def __init__(self, config: Optional[Config] = None):
        warnings.warn(
            "GoldenRecordService is deprecated and its end-to-end path is "
            "non-functional; use GoldenRecordPersistenceService instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.config = config or get_config()
        self.logger = get_logger(__name__)
        
        # Default field resolution strategies
        self.field_strategies = {
            'first_name': 'most_complete_with_quality',
            'last_name': 'most_complete_with_quality', 
            'email': 'highest_quality',
            'phone': 'most_recent_valid',
            'address': 'most_complete_with_quality',
            'city': 'most_frequent',
            'state': 'most_frequent',
            'zip_code': 'most_recent_valid',
            'company': 'most_complete_with_quality',
            'created_at': 'earliest',
            'updated_at': 'latest'
        }
        
        # Data quality rules
        self.quality_rules = {
            'email': self._validate_email,
            'phone': self._validate_phone,
            'zip_code': self._validate_zip_code,
            'state': self._validate_state
        }
    
    def generate_golden_records(self, clusters: List[Dict[str, Any]], 
                               source_collection: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate golden records from entity clusters
        
        Args:
            clusters: List of entity clusters with member IDs
            source_collection: Source collection name for record retrieval
            
        Returns:
            Golden record generation results

        Raises:
            NotImplementedError: always — record retrieval was never
                implemented, so this path can only produce empty results.
        """
        raise NotImplementedError(
            "GoldenRecordService.generate_golden_records is non-functional: "
            "record retrieval was never implemented, so it silently produced "
            "empty golden records. Use GoldenRecordPersistenceService instead "
            "(supports per-field survivorship via merge_strategy)."
        )

    def _consolidate_cluster_records(self, cluster: Dict[str, Any], 
                                   source_records: List[Dict[str, Any]],
                                   stats: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Consolidate multiple records into a single golden record
        
        Args:
            cluster: Cluster metadata
            source_records: Source records to consolidate
            stats: Statistics tracking object
            
        Returns:
            Consolidated golden record
        """
        try:
            if not source_records:
                return None
            
            # Initialize golden record with metadata
            golden_record = {
                '_id': f"golden_{cluster.get('cluster_id', 'unknown')}",
                'cluster_id': cluster.get('cluster_id'),
                'cluster_size': len(source_records),
                'source_record_ids': [r.get('_id') for r in source_records],
                'generation_timestamp': datetime.now().isoformat(),
                'confidence_score': 0.0,
                'field_provenance': {},
                'data_quality_score': 0.0
            }
            
            # Get all field names from source records
            all_fields = set()
            for record in source_records:
                all_fields.update(record.keys())
            
            # Remove system fields
            content_fields = {f for f in all_fields if not f.startswith('_')}
            
            total_confidence = 0.0
            resolved_fields = 0
            
            # Resolve each field
            for field in content_fields:
                try:
                    resolution_result = self._resolve_field_conflict(
                        field, source_records, stats)
                    
                    if resolution_result:
                        golden_record[field] = resolution_result['value']
                        golden_record['field_provenance'][field] = resolution_result['provenance']
                        total_confidence += resolution_result['confidence']
                        resolved_fields += 1
                        
                        if resolution_result.get('had_conflict', False):
                            stats['field_conflicts_resolved'] += 1
                            
                except Exception as e:
                    self.logger.warning(f"Failed to resolve field '{field}': {e}")
                    continue
            
            # Calculate overall confidence
            if resolved_fields > 0:
                golden_record['confidence_score'] = total_confidence / resolved_fields
            
            # Calculate data quality score
            golden_record['data_quality_score'] = self._calculate_data_quality_score(golden_record)
            
            return golden_record
            
        except Exception as e:
            self.logger.error(f"Failed to consolidate cluster records: {e}")
            return None
    
    def _resolve_field_conflict(self, field_name: str, records: List[Dict[str, Any]], 
                               stats: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Resolve conflicts for a specific field across multiple records
        
        Args:
            field_name: Name of the field to resolve
            records: Source records containing the field
            stats: Statistics tracking object
            
        Returns:
            Field resolution result with value, confidence, and provenance
        """
        try:
            # Get all values for this field
            field_values = []
            for i, record in enumerate(records):
                if field_name in record and record[field_name] is not None:
                    field_values.append({
                        'value': record[field_name],
                        'record_index': i,
                        'record_id': record.get('_id'),
                        'quality_score': self._assess_field_quality(field_name, record[field_name])
                    })
            
            if not field_values:
                return None
            
            # If only one value, return it
            if len(field_values) == 1:
                return {
                    'value': field_values[0]['value'],
                    'confidence': field_values[0]['quality_score'],
                    'provenance': {
                        'source_record_id': field_values[0]['record_id'],
                        'resolution_strategy': 'single_value',
                        'alternatives_count': 0
                    },
                    'had_conflict': False
                }
            
            # Multiple values - resolve conflict
            strategy = self.field_strategies.get(field_name, 'highest_quality')
            resolution_result = self._apply_resolution_strategy(strategy, field_name, field_values)
            
            if resolution_result:
                resolution_result['had_conflict'] = True
                resolution_result['provenance']['alternatives_count'] = len(field_values) - 1
            
            return resolution_result
            
        except Exception as e:
            self.logger.error(f"Failed to resolve field conflict for '{field_name}': {e}")
            return None
    
    def _apply_resolution_strategy(self, strategy: str, field_name: str, 
                                  field_values: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Apply the specified resolution strategy to resolve field conflicts"""
        
        try:
            if strategy == 'highest_quality':
                # Choose value with highest quality score
                best_value = max(field_values, key=lambda x: x['quality_score'])
                return {
                    'value': best_value['value'],
                    'confidence': best_value['quality_score'],
                    'provenance': {
                        'source_record_id': best_value['record_id'],
                        'resolution_strategy': 'highest_quality'
                    }
                }
            
            elif strategy == 'most_frequent':
                # Choose most frequently occurring value
                value_counts = Counter(str(v['value']) for v in field_values)
                most_common_value = value_counts.most_common(1)[0][0]
                
                # Find a record with this value to get metadata
                source_record = next(v for v in field_values if str(v['value']) == most_common_value)
                
                return {
                    'value': source_record['value'],
                    'confidence': min(0.9, 0.5 + (value_counts[most_common_value] / len(field_values))),
                    'provenance': {
                        'source_record_id': source_record['record_id'],
                        'resolution_strategy': 'most_frequent',
                        'frequency': value_counts[most_common_value]
                    }
                }
            
            elif strategy == 'most_complete_with_quality':
                # Choose the most complete (longest) value with decent quality
                valid_values = [v for v in field_values if v['quality_score'] >= 0.5]
                if not valid_values:
                    valid_values = field_values  # Fall back to all values
                
                best_value = max(valid_values, key=lambda x: (len(str(x['value'])), x['quality_score']))
                
                return {
                    'value': best_value['value'],
                    'confidence': best_value['quality_score'],
                    'provenance': {
                        'source_record_id': best_value['record_id'],
                        'resolution_strategy': 'most_complete_with_quality'
                    }
                }
            
            elif strategy == 'most_recent_valid':
                # For now, just return highest quality (would need timestamp info)
                return self._apply_resolution_strategy('highest_quality', field_name, field_values)
            
            elif strategy == 'earliest' or strategy == 'latest':
                # For now, just return highest quality (would need timestamp info)
                return self._apply_resolution_strategy('highest_quality', field_name, field_values)
            
            else:
                # Default to highest quality
                return self._apply_resolution_strategy('highest_quality', field_name, field_values)
                
        except Exception as e:
            self.logger.error(f"Failed to apply resolution strategy '{strategy}': {e}")
            return None
    
    def _assess_field_quality(self, field_name: str, value: Any) -> float:
        """
        Assess the quality of a field value
        
        Args:
            field_name: Name of the field
            value: Field value to assess
            
        Returns:
            Quality score between 0.0 and 1.0
        """
        try:
            if value is None or value == '':
                return 0.0
            
            base_score = 0.5  # Base score for non-empty values
            
            # Apply field-specific quality rules
            if field_name in self.quality_rules:
                validation_result = self.quality_rules[field_name](value)
                if validation_result['valid']:
                    base_score += 0.3
                else:
                    base_score -= 0.2
            
            # General quality indicators
            value_str = str(value).strip()
            
            # Length-based scoring (reasonable length is better)
            if len(value_str) > 2:
                base_score += 0.1
            if len(value_str) > 5:
                base_score += 0.1
            
            # Penalize very long values (might be corrupted)
            if len(value_str) > 100:
                base_score -= 0.2
            
            # Penalize values with too many special characters
            special_char_ratio = sum(1 for c in value_str if not c.isalnum() and c != ' ') / len(value_str)
            if special_char_ratio > 0.3:
                base_score -= 0.1
            
            return max(0.0, min(1.0, base_score))
            
        except Exception as e:
            self.logger.warning(f"Failed to assess quality for field '{field_name}': {e}")
            return 0.5  # Default neutral score
    
    def _validate_email(self, email: str) -> Dict[str, Any]:
        """Validate email format"""
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        is_valid = bool(re.match(email_pattern, str(email).strip()))
        return {'valid': is_valid, 'reason': 'format_check'}
    
    def _validate_phone(self, phone: str) -> Dict[str, Any]:
        """Validate phone number format"""
        import re
        # Simple US phone number validation
        phone_clean = re.sub(r'[^\d]', '', str(phone))
        is_valid = len(phone_clean) >= 10 and len(phone_clean) <= 11
        return {'valid': is_valid, 'reason': 'length_check'}
    
    def _validate_zip_code(self, zip_code: str) -> Dict[str, Any]:
        """Validate ZIP code format"""
        import re
        zip_pattern = r'^\d{5}(-\d{4})?$'
        is_valid = bool(re.match(zip_pattern, str(zip_code).strip()))
        return {'valid': is_valid, 'reason': 'format_check'}
    
    def _validate_state(self, state: str) -> Dict[str, Any]:
        """Validate US state code"""
        valid_states = {
            'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
            'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
            'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
            'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
            'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
        }
        is_valid = str(state).strip().upper() in valid_states
        return {'valid': is_valid, 'reason': 'state_code_check'}
    
    def _calculate_data_quality_score(self, golden_record: Dict[str, Any]) -> float:
        """Calculate overall data quality score for the golden record"""
        try:
            # Key fields that contribute to quality
            key_fields = ['first_name', 'last_name', 'email', 'phone', 'address']
            
            quality_scores = []
            for field in key_fields:
                if field in golden_record and golden_record[field] is not None:
                    field_quality = self._assess_field_quality(field, golden_record[field])
                    quality_scores.append(field_quality)
            
            if not quality_scores:
                return 0.0
            
            # Average quality with bonus for completeness
            avg_quality = sum(quality_scores) / len(quality_scores)
            completeness_bonus = len(quality_scores) / len(key_fields) * 0.2
            
            return min(1.0, avg_quality + completeness_bonus)
            
        except Exception as e:
            self.logger.error(f"Failed to calculate data quality score: {e}")
            return 0.0
    
    def validate_golden_record(self, golden_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a golden record for completeness and quality
        
        Args:
            golden_record: Golden record to validate
            
        Returns:
            Validation results
        """
        try:
            validation_results = {
                'is_valid': True,
                'quality_score': golden_record.get('data_quality_score', 0),
                'confidence_score': golden_record.get('confidence_score', 0),
                'completeness_score': 0,
                'issues': [],
                'warnings': []
            }
            
            # Check required fields
            required_fields = ['first_name', 'last_name']
            missing_required = []
            
            for field in required_fields:
                if field not in golden_record or not golden_record[field]:
                    missing_required.append(field)
            
            if missing_required:
                validation_results['is_valid'] = False
                validation_results['issues'].append(f"Missing required fields: {missing_required}")
            
            # Calculate completeness
            key_fields = ['first_name', 'last_name', 'email', 'phone', 'address', 'city', 'state']
            complete_fields = sum(1 for field in key_fields 
                                if field in golden_record and golden_record[field])
            validation_results['completeness_score'] = complete_fields / len(key_fields)
            
            # Quality thresholds
            if validation_results['quality_score'] < 0.5:
                validation_results['warnings'].append('Low data quality score')
            
            if validation_results['confidence_score'] < 0.6:
                validation_results['warnings'].append('Low confidence score')
            
            if validation_results['completeness_score'] < 0.4:
                validation_results['warnings'].append('Low completeness score')
            
            return validation_results
            
        except Exception as e:
            self.logger.error(f"Failed to validate golden record: {e}")
            return {'is_valid': False, 'error': str(e)}
    
    def get_generation_statistics(self, golden_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate comprehensive statistics about golden record generation"""
        try:
            if not golden_records:
                return {'total_records': 0}
            
            quality_scores = [r.get('data_quality_score', 0) for r in golden_records]
            confidence_scores = [r.get('confidence_score', 0) for r in golden_records]
            cluster_sizes = [r.get('cluster_size', 0) for r in golden_records]
            
            return {
                'total_records': len(golden_records),
                'quality_statistics': {
                    'average_quality': sum(quality_scores) / len(quality_scores),
                    'min_quality': min(quality_scores),
                    'max_quality': max(quality_scores),
                    'high_quality_records': sum(1 for q in quality_scores if q >= 0.8)
                },
                'confidence_statistics': {
                    'average_confidence': sum(confidence_scores) / len(confidence_scores),
                    'min_confidence': min(confidence_scores),
                    'max_confidence': max(confidence_scores),
                    'high_confidence_records': sum(1 for c in confidence_scores if c >= 0.8)
                },
                'cluster_statistics': {
                    'average_cluster_size': sum(cluster_sizes) / len(cluster_sizes),
                    'min_cluster_size': min(cluster_sizes),
                    'max_cluster_size': max(cluster_sizes),
                    'single_record_clusters': sum(1 for s in cluster_sizes if s == 1)
                }
            }
            
        except Exception as e:
            self.logger.error(f"Failed to generate statistics: {e}")
            return {'error': str(e)}

