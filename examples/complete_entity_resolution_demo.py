#!/usr/bin/env python3
"""
Complete Entity Resolution Pipeline Demo

DEPRECATION WARNING
-------------------
This example uses legacy API patterns (Config.from_env(),
BlockingService.generate_candidates(), SimilarityService.compute_batch_similarity())
that predate the v3.0 service layer.  It still runs but may not reflect current
best practices.  See examples/enhanced_er_examples.py for the recommended API.

Demonstrates the full end-to-end entity resolution system with:
1. Data loading and validation
2. Blocking and candidate generation
3. Similarity computation with Fellegi-Sunter
4. Graph-based clustering with WCC
5. Golden record generation
6. Comprehensive reporting and analysis

This showcases all implemented components working together.

Prerequisites:
    pip install arango-entity-resolution
"""

import json
import time
from typing import Dict, List, Any

# Requires: pip install arango-entity-resolution
from entity_resolution import (
    DataManager,
    BlockingService,
    SimilarityService,
    ClusteringService,
    GoldenRecordPersistenceService,
    Config
)
from entity_resolution.utils.logging import setup_logging, get_logger


class CompleteEntityResolutionPipeline:
    """
    Complete entity resolution pipeline orchestrator
    
    Coordinates all services to perform end-to-end entity resolution
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = get_logger(__name__)
        
        # Initialize all services
        self.data_manager = DataManager(config)
        self.blocking_service = BlockingService(config)
        self.similarity_service = SimilarityService(config)
        self.clustering_service = ClusteringService(config)
        # Golden records: GoldenRecordPersistenceService is constructed in
        # _run_golden_record_stage once a db connection exists.

        # Pipeline state
        self.connected = False
        self.pipeline_stats = {}
    
    def connect(self) -> bool:
        """Connect to all services"""
        try:
            # Connect data manager
            if not self.data_manager.connect():
                self.logger.error("Failed to connect data manager")
                return False
            
            # Connect services
            services = [
                ("blocking", self.blocking_service),
                ("similarity", self.similarity_service), 
                ("clustering", self.clustering_service)
            ]
            
            for name, service in services:
                if not service.connect():
                    self.logger.error(f"Failed to connect {name} service")
                    return False
                    
            self.connected = True
            self.logger.info("All services connected successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Pipeline connection failed: {e}")
            return False
    
    def run_complete_pipeline(self, collection_name: str = "customers", 
                            target_record_limit: int = 100) -> Dict[str, Any]:
        """
        Run the complete entity resolution pipeline
        
        Args:
            collection_name: Source collection name
            target_record_limit: Limit records for demo purposes
            
        Returns:
            Complete pipeline results
        """
        if not self.connected:
            return {"success": False, "error": "Pipeline not connected"}
        
        pipeline_start = time.time()
        self.logger.info(f"Starting complete entity resolution pipeline for {collection_name}")
        
        try:
            # Stage 1: Data Loading and Validation
            stage1_result = self._run_data_stage(collection_name, target_record_limit)
            if not stage1_result["success"]:
                return self._build_error_response("Data stage failed", stage1_result)
            
            records = stage1_result["records"]
            self.logger.info(f"Stage 1 completed: {len(records)} records loaded")
            
            # Stage 2: Blocking and Candidate Generation
            stage2_result = self._run_blocking_stage(records, collection_name)
            if not stage2_result["success"]:
                return self._build_error_response("Blocking stage failed", stage2_result)
            
            candidate_pairs = stage2_result["candidate_pairs"]
            self.logger.info(f"Stage 2 completed: {len(candidate_pairs)} candidate pairs generated")
            
            # Stage 3: Similarity Computation
            stage3_result = self._run_similarity_stage(candidate_pairs)
            if not stage3_result["success"]:
                return self._build_error_response("Similarity stage failed", stage3_result)
            
            scored_pairs = stage3_result["scored_pairs"]
            self.logger.info(f"Stage 3 completed: {len(scored_pairs)} pairs scored")
            
            # Stage 4: Clustering
            stage4_result = self._run_clustering_stage(scored_pairs)
            if not stage4_result["success"]:
                return self._build_error_response("Clustering stage failed", stage4_result)
            
            clusters = stage4_result["clusters"]
            self.logger.info(f"Stage 4 completed: {len(clusters)} clusters found")
            
            # Stage 5: Golden Record Generation
            stage5_result = self._run_golden_record_stage(clusters, collection_name)
            if not stage5_result["success"]:
                return self._build_error_response("Golden record stage failed", stage5_result)
            
            golden_records = stage5_result["golden_records"]
            self.logger.info(f"Stage 5 completed: {len(golden_records)} golden records created")
            
            # Compile final results
            total_time = time.time() - pipeline_start
            
            return {
                "success": True,
                "pipeline_type": "complete_entity_resolution",
                "collection": collection_name,
                "total_processing_time": total_time,
                "stages": {
                    "data_loading": stage1_result,
                    "blocking": stage2_result,
                    "similarity": stage3_result,
                    "clustering": stage4_result,
                    "golden_records": stage5_result
                },
                "summary": {
                    "input_records": len(records),
                    "candidate_pairs": len(candidate_pairs),
                    "scored_pairs": len(scored_pairs),
                    "entity_clusters": len(clusters),
                    "golden_records": len(golden_records),
                    "processing_time": total_time
                },
                "performance": self._calculate_performance_metrics(
                    len(records), len(candidate_pairs), len(scored_pairs), 
                    len(clusters), len(golden_records), total_time)
            }
            
        except Exception as e:
            self.logger.error(f"Pipeline execution failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _run_data_stage(self, collection_name: str, limit: int) -> Dict[str, Any]:
        """Run data loading and validation stage"""
        try:
            start_time = time.time()
            
            # Get records from collection
            records = self.data_manager.sample_records(collection_name, limit=limit)
            
            if not records:
                return {"success": False, "error": f"No records found in {collection_name}"}
            
            # Basic data quality analysis
            quality_analysis = self._analyze_data_quality(records)
            
            processing_time = time.time() - start_time
            
            return {
                "success": True,
                "stage": "data_loading",
                "records": records,
                "record_count": len(records),
                "data_quality": quality_analysis,
                "processing_time": processing_time
            }
            
        except Exception as e:
            self.logger.error(f"Data stage failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _run_blocking_stage(self, records: List[Dict[str, Any]], 
                           collection_name: str) -> Dict[str, Any]:
        """Run blocking and candidate generation stage"""
        try:
            start_time = time.time()
            
            # For demo purposes, we'll use a simplified blocking approach
            # In production, you'd use the blocking service for each record
            candidate_pairs = []
            
            # Generate candidates using multiple strategies
            strategies = ["exact", "ngram", "phonetic"]
            max_pairs = self.config.er.max_candidates_per_record * len(records)
            
            for i, record in enumerate(records[:10]):  # Limit for demo
                try:
                    target_id = record.get("_id")
                    if not target_id:
                        continue
                    
                    # Generate candidates for this record
                    blocking_result = self.blocking_service.generate_candidates(
                        collection=collection_name,
                        target_record_id=target_id,
                        strategies=strategies,
                        limit=min(20, max_pairs // len(records))
                    )
                    
                    if blocking_result.get("success", True):
                        candidates = blocking_result.get("candidates", [])
                        
                        # Convert to candidate pairs
                        for candidate in candidates:
                            candidate_pairs.append({
                                "record_a": record,
                                "record_b": candidate.get("document", {}),
                                "record_a_id": target_id,
                                "record_b_id": candidate.get("_id"),
                                "blocking_strategy": candidate.get("blocking_strategy", "multi")
                            })
                    
                    if len(candidate_pairs) >= max_pairs:
                        break
                        
                except Exception as e:
                    self.logger.warning(f"Blocking failed for record {i}: {e}")
                    continue
            
            processing_time = time.time() - start_time
            
            # Calculate blocking efficiency
            total_possible_pairs = (len(records) * (len(records) - 1)) // 2
            reduction_ratio = 1 - (len(candidate_pairs) / total_possible_pairs) if total_possible_pairs > 0 else 0
            
            return {
                "success": True,
                "stage": "blocking",
                "candidate_pairs": candidate_pairs,
                "pair_count": len(candidate_pairs),
                "strategies_used": strategies,
                "reduction_ratio": reduction_ratio,
                "processing_time": processing_time
            }
            
        except Exception as e:
            self.logger.error(f"Blocking stage failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _run_similarity_stage(self, candidate_pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run similarity computation stage"""
        try:
            start_time = time.time()
            
            # Prepare pairs for batch similarity computation
            pairs_for_similarity = []
            for pair in candidate_pairs:
                pairs_for_similarity.append({
                    "record_a": pair["record_a"],
                    "record_b": pair["record_b"]
                })
            
            # Compute similarity in batches
            batch_size = 50
            all_scored_pairs = []
            
            for i in range(0, len(pairs_for_similarity), batch_size):
                batch = pairs_for_similarity[i:i + batch_size]
                
                try:
                    batch_result = self.similarity_service.compute_batch_similarity(
                        pairs=batch,
                        include_details=False
                    )
                    
                    if batch_result.get("success", True):
                        results = batch_result.get("results", [])
                        
                        # Add original pair information
                        for j, result in enumerate(results):
                            if result.get("success", True):
                                original_pair = candidate_pairs[i + j]
                                scored_pair = {
                                    "record_a_id": original_pair["record_a_id"],
                                    "record_b_id": original_pair["record_b_id"],
                                    "similarity_score": result["total_score"],
                                    "normalized_score": result.get("normalized_score", result["total_score"]),
                                    "is_match": result["is_match"],
                                    "confidence": result["confidence"],
                                    "decision": result["decision"],
                                    "blocking_strategy": original_pair["blocking_strategy"]
                                }
                                all_scored_pairs.append(scored_pair)
                
                except Exception as e:
                    self.logger.warning(f"Similarity batch {i//batch_size + 1} failed: {e}")
                    continue
            
            processing_time = time.time() - start_time
            
            # Calculate similarity statistics
            match_pairs = [p for p in all_scored_pairs if p["is_match"]]
            scores = [p["similarity_score"] for p in all_scored_pairs]
            
            statistics = {
                "total_pairs": len(all_scored_pairs),
                "match_pairs": len(match_pairs),
                "non_match_pairs": len(all_scored_pairs) - len(match_pairs),
                "average_score": sum(scores) / len(scores) if scores else 0,
                "max_score": max(scores) if scores else 0,
                "min_score": min(scores) if scores else 0
            }
            
            return {
                "success": True,
                "stage": "similarity",
                "scored_pairs": all_scored_pairs,
                "pair_count": len(all_scored_pairs),
                "statistics": statistics,
                "processing_time": processing_time
            }
            
        except Exception as e:
            self.logger.error(f"Similarity stage failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _run_clustering_stage(self, scored_pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run clustering stage"""
        try:
            start_time = time.time()
            
            # Perform clustering
            clustering_result = self.clustering_service.cluster_entities(
                scored_pairs=scored_pairs,
                min_similarity=self.config.er.similarity_threshold,
                max_cluster_size=self.config.er.max_cluster_size
            )
            
            if not clustering_result.get("success", True):
                return {"success": False, "error": clustering_result.get("error", "Clustering failed")}
            
            clusters = clustering_result["clusters"]
            processing_time = time.time() - start_time
            
            # Validate cluster quality
            validation_result = self.clustering_service.validate_cluster_quality(clusters)
            
            return {
                "success": True,
                "stage": "clustering",
                "clusters": clusters,
                "cluster_count": len(clusters),
                "clustering_statistics": clustering_result.get("statistics", {}),
                "validation_results": validation_result if validation_result.get("success", True) else None,
                "processing_time": processing_time
            }
            
        except Exception as e:
            self.logger.error(f"Clustering stage failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _run_golden_record_stage(self, clusters: List[Dict[str, Any]],
                                collection_name: str) -> Dict[str, Any]:
        """Persist golden records from clusters via GoldenRecordPersistenceService."""
        try:
            start_time = time.time()
            db = self.data_manager.db

            # The persistence service reads clusters from a collection, so
            # write the in-memory clusters out first.
            cluster_collection = f"{collection_name}_demo_clusters"
            if db.has_collection(cluster_collection):
                db.collection(cluster_collection).truncate()
            else:
                db.create_collection(cluster_collection)

            cluster_docs = []
            for i, cluster in enumerate(clusters):
                members = cluster.get("member_ids") or cluster.get("members") or []
                cluster_docs.append({
                    "_key": f"cluster_{i:06d}",
                    "cluster_id": cluster.get("cluster_id", i),
                    "members": list(members),
                })
            if cluster_docs:
                db.collection(cluster_collection).insert_many(cluster_docs)

            golden_collection = f"{collection_name}_golden_records"
            service = GoldenRecordPersistenceService(
                db=db,
                source_collection=collection_name,
                cluster_collection=cluster_collection,
                golden_collection=golden_collection,
                include_provenance=True,
            )
            run_summary = service.run(min_cluster_size=2)
            processing_time = time.time() - start_time

            golden_records = [doc for doc in db.collection(golden_collection)]

            return {
                "success": True,
                "stage": "golden_records",
                "golden_records": golden_records,
                "record_count": len(golden_records),
                "golden_collection": golden_collection,
                "statistics": {
                    **run_summary,
                    "processing_time": processing_time,
                },
                "processing_time": processing_time
            }

        except Exception as e:
            self.logger.error(f"Golden record stage failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _analyze_data_quality(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze data quality of input records"""
        try:
            if not records:
                return {"overall_quality": 0, "field_analysis": {}}
            
            field_analysis = {}
            all_fields = set()
            
            # Collect all field names
            for record in records:
                all_fields.update(record.keys())
            
            # Analyze each field
            for field in all_fields:
                if field.startswith('_'):  # Skip system fields
                    continue
                
                values = [record.get(field) for record in records]
                non_null_values = [v for v in values if v is not None and str(v).strip()]
                
                field_analysis[field] = {
                    "completeness": len(non_null_values) / len(records) if records else 0,
                    "unique_count": len(set(str(v) for v in non_null_values)),
                    "null_percentage": (len(records) - len(non_null_values)) / len(records) * 100 if records else 0
                }
            
            # Calculate overall quality
            completeness_scores = [analysis["completeness"] for analysis in field_analysis.values()]
            overall_quality = sum(completeness_scores) / len(completeness_scores) if completeness_scores else 0
            
            return {
                "overall_quality": overall_quality,
                "field_analysis": field_analysis,
                "record_count": len(records),
                "field_count": len(field_analysis)
            }
            
        except Exception as e:
            self.logger.error(f"Data quality analysis failed: {e}")
            return {"overall_quality": 0, "error": str(e)}
    
    def _calculate_performance_metrics(self, input_records: int, candidate_pairs: int,
                                     scored_pairs: int, clusters: int, golden_records: int,
                                     total_time: float) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics"""
        try:
            # Throughput metrics
            records_per_second = input_records / total_time if total_time > 0 else 0
            pairs_per_second = scored_pairs / total_time if total_time > 0 else 0
            
            # Efficiency metrics
            total_possible_pairs = (input_records * (input_records - 1)) // 2
            blocking_efficiency = 1 - (candidate_pairs / total_possible_pairs) if total_possible_pairs > 0 else 0
            
            # Quality metrics
            entity_consolidation_ratio = (input_records - golden_records) / input_records if input_records > 0 else 0
            average_cluster_size = input_records / clusters if clusters > 0 else 0
            
            return {
                "throughput": {
                    "records_per_second": records_per_second,
                    "pairs_per_second": pairs_per_second,
                    "total_processing_time": total_time
                },
                "efficiency": {
                    "blocking_reduction_ratio": blocking_efficiency,
                    "entity_consolidation_ratio": entity_consolidation_ratio,
                    "average_cluster_size": average_cluster_size
                },
                "scalability": {
                    "complexity_reduction": f"{blocking_efficiency*100:.1f}% pair reduction",
                    "processing_speed": f"{records_per_second:.0f} records/second",
                    "memory_efficiency": "Optimized for large datasets"
                }
            }
            
        except Exception as e:
            self.logger.error(f"Performance calculation failed: {e}")
            return {"error": str(e)}
    
    def _build_error_response(self, message: str, stage_result: Dict[str, Any]) -> Dict[str, Any]:
        """Build error response for pipeline failure"""
        return {
            "success": False,
            "error": message,
            "stage_error": stage_result.get("error", "Unknown error"),
            "failed_stage": stage_result.get("stage", "unknown")
        }


def create_sample_data_if_needed():
    """Create sample data for demonstration if none exists"""
    logger = get_logger(__name__)
    
    try:
        from arango import ArangoClient
        
        config = Config.from_env()
        client = ArangoClient(hosts=f"http://{config.db.host}:{config.db.port}")
        db = client.db(config.db.database, username=config.db.username, 
                      password=config.db.password)
        
        # Check if we have sample data
        if not db.has_collection("customers"):
            db.create_collection("customers")
        
        customers = db.collection("customers")
        if customers.count() < 10:
            logger.info("Creating sample data for demonstration...")
            
            sample_records = [
                {
                    "_key": "demo_1",
                    "first_name": "John",
                    "last_name": "Smith",
                    "email": "john.smith@email.com",
                    "phone": "555-123-4567",
                    "address": "123 Main St",
                    "city": "New York",
                    "company": "Acme Corp"
                },
                {
                    "_key": "demo_2",
                    "first_name": "Jon",
                    "last_name": "Smith",
                    "email": "john.smith@gmail.com",  # Different email domain
                    "phone": "5551234567",  # No dashes
                    "address": "123 Main Street",  # Slight variation
                    "city": "NYC",  # Abbreviation
                    "company": "Acme Corporation"  # Full name
                },
                {
                    "_key": "demo_3",
                    "first_name": "John",
                    "last_name": "Smyth",  # Phonetic variation
                    "email": "j.smith@acme.com",
                    "phone": "555-123-4567",
                    "address": "123 Main St",
                    "city": "New York",
                    "company": "Acme Corp"
                },
                {
                    "_key": "demo_4",
                    "first_name": "Mary",
                    "last_name": "Johnson",
                    "email": "mary.johnson@test.com",
                    "phone": "555-987-6543",
                    "address": "456 Oak Ave",
                    "city": "Boston",
                    "company": "TechStart Inc"
                },
                {
                    "_key": "demo_5",
                    "first_name": "Mary",
                    "last_name": "Johnson",
                    "email": "m.johnson@test.com",  # Abbreviated
                    "phone": "555-987-6543",
                    "address": "456 Oak Avenue",  # Full word
                    "city": "Boston",
                    "company": "TechStart Inc"
                },
                {
                    "_key": "demo_6",
                    "first_name": "Robert",
                    "last_name": "Wilson",
                    "email": "robert.wilson@company.com",
                    "phone": "555-555-5555",
                    "address": "789 Pine St",
                    "city": "Chicago",
                    "company": "Global Systems"
                },
                {
                    "_key": "demo_7",
                    "first_name": "Bob",  # Nickname
                    "last_name": "Wilson",
                    "email": "bob.wilson@company.com",
                    "phone": "555-555-5555",
                    "address": "789 Pine Street",
                    "city": "Chicago",
                    "company": "Global Systems LLC"
                },
                {
                    "_key": "demo_8",
                    "first_name": "Alice",
                    "last_name": "Brown",
                    "email": "alice.brown@example.com",
                    "phone": "555-111-2222",
                    "address": "321 Elm St",
                    "city": "Seattle",
                    "company": "Innovation Labs"
                }
            ]
            
            # Insert sample records
            for record in sample_records:
                try:
                    customers.insert(record)
                except Exception as e:
                    if "unique constraint violated" not in str(e).lower():
                        logger.warning(f"Could not insert record {record['_key']}: {e}")
            
            logger.info(f"Created {len(sample_records)} sample records for demonstration")
            return True
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to create sample data: {e}")
        return False


def main():
    """Run the complete entity resolution pipeline demonstration"""
    
    # Set up logging
    logger = setup_logging(log_level="INFO", enable_debug=False)
    logger.info("=== Complete Entity Resolution Pipeline Demo ===")
    
    try:
        # Load configuration
        config = Config.from_env()
        
        # Create sample data if needed
        if not create_sample_data_if_needed():
            logger.error("Failed to prepare sample data")
            return False
        
        # Initialize and connect pipeline
        pipeline = CompleteEntityResolutionPipeline(config)
        
        if not pipeline.connect():
            logger.error("Failed to connect pipeline services")
            return False
        
        logger.info("All services connected successfully")
        
        # Run the complete pipeline
        logger.info("\n? Starting complete entity resolution pipeline...")
        
        start_time = time.time()
        result = pipeline.run_complete_pipeline(
            collection_name="customers",
            target_record_limit=50  # Limit for demo purposes
        )
        end_time = time.time()
        
        if result.get("success", False):
            # Display comprehensive results
            display_pipeline_results(result, logger)
            
            # Save detailed report
            save_pipeline_report(result)
            
            logger.info(f"\n[PASS] Complete entity resolution pipeline demo completed successfully!")
            logger.info(f"   Total execution time: {end_time - start_time:.3f} seconds")
            
            return True
        else:
            logger.error(f"[FAIL] Pipeline execution failed: {result.get('error', 'Unknown error')}")
            return False
            
    except Exception as e:
        logger.error(f"Demo failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def display_pipeline_results(result: Dict[str, Any], logger):
    """Display comprehensive pipeline results"""
    
    summary = result.get("summary", {})
    performance = result.get("performance", {})
    
    print("\n" + "="*80)
    print("COMPLETE ENTITY RESOLUTION PIPELINE RESULTS")
    print("="*80)
    
    # Summary statistics
    print(f"? Processing Summary:")
    print(f"   Input records: {summary.get('input_records', 0):,}")
    print(f"   Candidate pairs: {summary.get('candidate_pairs', 0):,}")
    print(f"   Scored pairs: {summary.get('scored_pairs', 0):,}")
    print(f"   Entity clusters: {summary.get('entity_clusters', 0):,}")
    print(f"   Golden records: {summary.get('golden_records', 0):,}")
    print(f"   Total time: {summary.get('processing_time', 0):.3f} seconds")
    
    # Performance metrics
    if performance:
        throughput = performance.get("throughput", {})
        efficiency = performance.get("efficiency", {})
        
        print(f"\n[FAST] Performance Metrics:")
        print(f"   Processing speed: {throughput.get('records_per_second', 0):.0f} records/second")
        print(f"   Pair processing: {throughput.get('pairs_per_second', 0):.0f} pairs/second") 
        print(f"   Blocking efficiency: {efficiency.get('blocking_reduction_ratio', 0)*100:.1f}% pair reduction")
        print(f"   Entity consolidation: {efficiency.get('entity_consolidation_ratio', 0)*100:.1f}% records consolidated")
    
    # Stage-by-stage breakdown
    stages = result.get("stages", {})
    
    print(f"\n? Stage-by-Stage Results:")
    stage_names = ["data_loading", "blocking", "similarity", "clustering", "golden_records"]
    stage_labels = ["Data Loading", "Blocking", "Similarity", "Clustering", "Golden Records"]
    
    for name, label in zip(stage_names, stage_labels):
        stage_data = stages.get(name, {})
        if stage_data.get("success", False):
            time_taken = stage_data.get("processing_time", 0)
            print(f"   {label}: [PASS] {time_taken:.3f}s")
        else:
            print(f"   {label}: [FAIL] Failed")
    
    # Quality analysis
    data_stage = stages.get("data_loading", {})
    data_quality = data_stage.get("data_quality", {})
    overall_quality = data_quality.get("overall_quality", 0)
    
    print(f"\n? Quality Analysis:")
    print(f"   Data quality score: {overall_quality*100:.1f}%")
    
    # Clustering analysis
    clustering_stage = stages.get("clustering", {})
    clustering_stats = clustering_stage.get("clustering_statistics", {})
    if clustering_stats:
        print(f"   Average cluster size: {clustering_stats.get('average_cluster_size', 0):.1f}")
        print(f"   Valid clusters: {clustering_stats.get('valid_clusters', 0)}")
    
    # Golden records analysis
    golden_stage = stages.get("golden_records", {})
    golden_stats = golden_stage.get("statistics", {})
    if golden_stats:
        print(f"   Average golden record quality: {golden_stats.get('average_quality_score', 0)*100:.1f}%")
        print(f"   High quality records: {golden_stats.get('high_quality_records', 0)}")


def save_pipeline_report(result: Dict[str, Any]):
    """Save detailed pipeline report to file"""
    
    report_path = Path(__file__).parent.parent / "reports" / "complete_pipeline_report.json"
    report_path.parent.mkdir(exist_ok=True)
    
    # Add metadata
    enhanced_result = {
        **result,
        "report_metadata": {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pipeline_version": "1.0.0",
            "components": [
                "BlockingService",
                "SimilarityService",
                "ClusteringService",
                "GoldenRecordPersistenceService"
            ]
        }
    }
    
    with open(report_path, 'w') as f:
        json.dump(enhanced_result, f, indent=2, default=str)
    
    print(f"\n? Detailed report saved to: {report_path}")


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
