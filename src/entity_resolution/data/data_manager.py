"""
Data Manager for Entity Resolution System

Handles data ingestion, validation, and basic CRUD operations.
"""

import json
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    pd = None
    PANDAS_AVAILABLE = False
from typing import Dict, List, Any, Optional, Union
from arango.database import StandardDatabase
from arango.collection import StandardCollection

from ..utils.config import Config, get_config
from ..utils.logging import get_logger
from ..utils.database import DatabaseMixin
from ..utils.validation import validate_collection_name


class DataManager(DatabaseMixin):
    """
    Manages data operations for entity resolution using centralized database management
    
    Handles:
    - Data ingestion from various sources
    - Collection management
    - Basic CRUD operations
    - Data validation and cleaning
    """
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()
        self.logger = get_logger(__name__)
        super().__init__()
        
    def connect(self) -> bool:
        """
        Establish connection to ArangoDB using centralized database manager
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Use centralized database manager
            if self.test_connection():
                self.logger.info(f"Connected to ArangoDB at {self.config.db.host}:{self.config.db.port}")
                return True
            else:
                self.logger.error("Failed to connect to ArangoDB")
                return False
            
        except Exception as e:
            self.logger.error(f"Failed to connect to ArangoDB: {e}")
            return False
    
    def create_collection(self, name: str, edge: bool = False) -> bool:
        """
        Create a collection if it doesn't exist
        
        Args:
            name: Collection name
            edge: Whether to create an edge collection
            
        Returns:
            True if created or already exists, False on error
        """
        try:
            if self.database.has_collection(name):
                self.logger.info(f"Collection '{name}' already exists")
                return True
            
            if edge:
                collection = self.database.create_collection(name, edge=True)
            else:
                collection = self.database.create_collection(name)
                
            self.logger.info(f"Created {'edge ' if edge else ''}collection: {name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create collection '{name}': {e}")
            return False
    
    def load_data_from_file(self, file_path: str, collection_name: str, 
                           batch_size: int = 1000) -> Dict[str, Any]:
        """
        Load data from JSON file into collection
        
        Args:
            file_path: Path to data file
            collection_name: Target collection name
            batch_size: Number of records per batch
            
        Returns:
            Results dictionary with statistics
        """
        try:
            # Create collection if it doesn't exist
            if not self.create_collection(collection_name):
                return {"success": False, "error": "Failed to create collection"}
            
            collection = self.database.collection(collection_name)
            
            # Load data
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # Handle different data formats
            if isinstance(data, dict):
                if 'customers' in data:
                    records = data['customers']
                elif 'data' in data:
                    records = data['data']
                else:
                    records = [data]  # Single record
            elif isinstance(data, list):
                records = data
            else:
                return {"success": False, "error": "Unsupported data format"}
            
            # Insert in batches
            total_inserted = 0
            errors = []
            
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                try:
                    result = collection.insert_many(batch)
                    total_inserted += len(result)
                except Exception as e:
                    errors.append(f"Batch {i//batch_size + 1}: {str(e)}")
            
            self.logger.info(f"Loaded {total_inserted} records into {collection_name}")
            
            return {
                "success": True,
                "collection": collection_name,
                "total_records": len(records),
                "inserted_records": total_inserted,
                "errors": errors
            }
            
        except Exception as e:
            self.logger.error(f"Failed to load data from {file_path}: {e}")
            return {"success": False, "error": str(e)}
    
    def load_data_from_dataframe(self, df: 'pd.DataFrame', collection_name: str,
                                batch_size: int = 1000) -> Dict[str, Any]:
        """
        Load data from pandas DataFrame into collection
        
        Args:
            df: Source DataFrame
            collection_name: Target collection name
            batch_size: Number of records per batch
            
        Returns:
            Results dictionary with statistics
        """
        try:
            if not PANDAS_AVAILABLE or pd is None:
                return {"success": False, "error": "pandas not available"}
            
            # Create collection if it doesn't exist
            if not self.create_collection(collection_name):
                return {"success": False, "error": "Failed to create collection"}
            
            collection = self.database.collection(collection_name)
            
            # Convert DataFrame to records
            records = df.to_dict('records')
            
            # Insert in batches
            total_inserted = 0
            errors = []
            
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                try:
                    result = collection.insert_many(batch)
                    total_inserted += len(result)
                except Exception as e:
                    errors.append(f"Batch {i//batch_size + 1}: {str(e)}")
            
            self.logger.info(f"Loaded {total_inserted} records from DataFrame into {collection_name}")
            
            return {
                "success": True,
                "collection": collection_name,
                "total_records": len(records),
                "inserted_records": total_inserted,
                "errors": errors
            }
            
        except Exception as e:
            self.logger.error(f"Failed to load DataFrame into {collection_name}: {e}")
            return {"success": False, "error": str(e)}
    
    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """
        Get statistics for a collection
        
        Args:
            collection_name: Collection name
            
        Returns:
            Statistics dictionary
        """
        try:
            if not self.db.has_collection(collection_name):
                return {"success": False, "error": f"Collection '{collection_name}' does not exist"}
            
            collection = self.database.collection(collection_name)
            properties = collection.properties()
            
            return {
                "success": True,
                "name": collection_name,
                "count": collection.count(),
                "type": properties.get("type"),
                "status": properties.get("status"),
                "indexes": collection.indexes()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get stats for {collection_name}: {e}")
            return {"success": False, "error": str(e)}
    
    def sample_records(self, collection_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get sample records from collection
        
        Args:
            collection_name: Collection name
            limit: Maximum number of records to return
            
        Returns:
            List of sample records
        """
        try:
            # Validate the collection name (interpolated into AQL) and pass the
            # limit as a bind variable to prevent AQL injection.
            safe_collection = validate_collection_name(collection_name)

            if not self.db.has_collection(safe_collection):
                self.logger.warning(f"Collection '{safe_collection}' does not exist")
                return []
            
            collection = self.database.collection(safe_collection)
            
            # Get sample using AQL
            aql = """
            FOR doc IN @@collection
                LIMIT @limit
                RETURN doc
            """
            
            cursor = self.db.aql.execute(
                aql,
                bind_vars={"@collection": safe_collection, "limit": int(limit)},
            )
            return list(cursor)
            
        except Exception as e:
            self.logger.error(f"Failed to sample records from {collection_name}: {e}")
            return []
    
    def validate_data_quality(self, collection_name: str) -> Dict[str, Any]:
        """
        Perform basic data quality validation
        
        Args:
            collection_name: Collection name
            
        Returns:
            Validation results
        """
        try:
            if not self.db.has_collection(collection_name):
                return {"success": False, "error": f"Collection '{collection_name}' does not exist"}
            
            # Get sample for analysis
            sample = self.sample_records(collection_name, 1000)
            
            if not sample:
                return {"success": False, "error": "No records found"}
            
            # Analyze fields
            field_analysis = {}
            total_records = len(sample)
            
            # Get all field names
            all_fields = set()
            for record in sample:
                all_fields.update(record.keys())
            
            # Analyze each field
            for field in all_fields:
                if field.startswith('_'):  # Skip ArangoDB internal fields
                    continue
                    
                values = [record.get(field) for record in sample]
                non_null_values = [v for v in values if v is not None and v != '']
                
                field_analysis[field] = {
                    "total_count": total_records,
                    "non_null_count": len(non_null_values),
                    "null_percentage": ((total_records - len(non_null_values)) / total_records) * 100,
                    "unique_count": len(set(str(v) for v in non_null_values)),
                    "sample_values": list(set(str(v) for v in non_null_values[:5]))
                }
            
            # Overall quality score
            avg_completeness = sum(fa["non_null_count"] / fa["total_count"] for fa in field_analysis.values()) / len(field_analysis)
            quality_score = avg_completeness * 100
            
            return {
                "success": True,
                "collection": collection_name,
                "total_records_analyzed": total_records,
                "field_analysis": field_analysis,
                "overall_quality_score": quality_score,
                "recommendations": self._generate_quality_recommendations(field_analysis)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to validate data quality for {collection_name}: {e}")
            return {"success": False, "error": str(e)}
    
    def _generate_quality_recommendations(self, field_analysis: Dict[str, Any]) -> List[str]:
        """Generate data quality recommendations"""
        recommendations = []
        
        for field, analysis in field_analysis.items():
            null_pct = analysis["null_percentage"]
            unique_count = analysis["unique_count"]
            total_count = analysis["total_count"]
            
            if null_pct > 50:
                recommendations.append(f"Field '{field}' has high null percentage ({null_pct:.1f}%) - consider data cleaning")
            
            if unique_count == total_count and field not in ['id', '_key', 'email']:
                recommendations.append(f"Field '{field}' appears to be unique - consider using as blocking key")
            
            if unique_count == 1:
                recommendations.append(f"Field '{field}' has only one unique value - may not be useful for matching")
        
        return recommendations
    
    def initialize_test_collections(self) -> Dict[str, Any]:
        """
        Initialize standard collections for entity resolution testing
        
        Returns:
            Results of initialization
        """
        collections_to_create = [
            ("customers", False),
            ("entities", False),
            ("similarities", True),
            ("entity_clusters", False),
            ("golden_records", False)
        ]
        
        results = {"success": True, "created": [], "errors": []}
        
        for name, is_edge in collections_to_create:
            if self.create_collection(name, edge=is_edge):
                results["created"].append(name)
            else:
                results["errors"].append(f"Failed to create {name}")
                results["success"] = False
        
        return results
