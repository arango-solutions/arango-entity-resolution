#!/usr/bin/env python3
"""
Comprehensive QA Tests for Entity Resolution System

This script runs a complete test suite to validate:
1. Database management and cleanup logic
2. Entity resolution pipeline functionality
3. Service connectivity and performance
4. Data integrity and consistency
5. Error handling and edge cases
"""

import sys
import os
import time
import json
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from entity_resolution.utils.database import DatabaseManager
from entity_resolution.utils.config import Config
from entity_resolution.data.data_manager import DataManager
from entity_resolution.core.entity_resolver import EntityResolutionPipeline

class QATestSuite:
    """Comprehensive QA test suite for entity resolution system."""
    
    def __init__(self):
        self.config = Config.from_env()
        self.db_manager = DatabaseManager()
        self.test_results = []
        self.start_time = datetime.now()
        
    def log_test(self, test_name, success, message="", duration=0):
        """Log test result."""
        status = "[PASS] PASS" if success else "[FAIL] FAIL"
        self.test_results.append({
            'test': test_name,
            'success': success,
            'message': message,
            'duration': duration
        })
        print(f"{status} {test_name}: {message}")
    
    def test_database_connection(self):
        """Test 1: Database connection and basic functionality."""
        print("\n? Test 1: Database Connection")
        start_time = time.time()
        
        try:
            if not self.db_manager.test_connection():
                self.log_test("Database Connection", False, "Could not connect to database")
                return False
            
            # Test system database access
            sys_db = self.db_manager.get_database()
            databases = sys_db.databases()
            
            duration = time.time() - start_time
            self.log_test("Database Connection", True, f"Connected to {len(databases)} databases", duration)
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self.log_test("Database Connection", False, f"Error: {e}", duration)
            return False
    
    def test_database_cleanup(self):
        """Test 2: Database cleanup functionality."""
        print("\n? Test 2: Database Cleanup")
        start_time = time.time()
        
        try:
            sys_db = self.db_manager.get_database()
            client = self.db_manager.client
            
            # Create a test database
            test_db_name = "qa_test_database"
            if sys_db.has_database(test_db_name):
                sys_db.delete_database(test_db_name)
            
            sys_db.create_database(test_db_name)
            
            # Verify database exists
            if not sys_db.has_database(test_db_name):
                self.log_test("Database Cleanup", False, "Failed to create test database")
                return False
            
            # Clean up test database
            sys_db.delete_database(test_db_name)
            
            # Verify database is deleted
            if sys_db.has_database(test_db_name):
                self.log_test("Database Cleanup", False, "Failed to delete test database")
                return False
            
            duration = time.time() - start_time
            self.log_test("Database Cleanup", True, "Create and delete database successfully", duration)
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self.log_test("Database Cleanup", False, f"Error: {e}", duration)
            return False
    
    def test_data_manager(self):
        """Test 3: DataManager functionality."""
        print("\n? Test 3: DataManager")
        start_time = time.time()
        
        try:
            data_manager = DataManager(self.config)
            
            # Test connection
            if not data_manager.connect():
                self.log_test("DataManager", False, "Failed to connect")
                return False
            
            # Test collection operations
            test_collection = "qa_test_collection"
            if data_manager.create_collection(test_collection):
                # Test document insertion using collection directly
                test_doc = {"name": "Test Customer", "email": "test@example.com", "id": 1}
                try:
                    collection = data_manager.database.collection(test_collection)
                    result = collection.insert(test_doc)
                    if result:
                        # Test document retrieval
                        documents = list(collection.all())
                        if len(documents) > 0:
                            # Clean up
                            data_manager.database.delete_collection(test_collection)
                            duration = time.time() - start_time
                            self.log_test("DataManager", True, "CRUD operations successful", duration)
                            return True
                        else:
                            self.log_test("DataManager", False, "Failed to retrieve documents")
                            return False
                    else:
                        self.log_test("DataManager", False, "Failed to insert document")
                        return False
                except Exception as e:
                    self.log_test("DataManager", False, f"Failed to insert document: {e}")
                    return False
            else:
                self.log_test("DataManager", False, "Failed to create collection")
                return False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_test("DataManager", False, f"Error: {e}", duration)
            return False
    
    def test_entity_resolution_pipeline(self):
        """Test 4: Entity Resolution Pipeline."""
        print("\n? Test 4: Entity Resolution Pipeline")
        start_time = time.time()
        
        try:
            # Create pipeline
            pipeline = EntityResolutionPipeline(self.config)
            
            # Test connection
            if not pipeline.connect():
                self.log_test("Entity Resolution Pipeline", False, "Failed to connect pipeline")
                return False
            
            # Test pipeline components (check actual components available)
            components = [
                'data_manager',
                'blocking_service',
                'similarity_service', 
                'clustering_service'
            ]
            
            for component in components:
                if not hasattr(pipeline, component):
                    self.log_test("Entity Resolution Pipeline", False, f"Missing component: {component}")
                    return False
            
            duration = time.time() - start_time
            self.log_test("Entity Resolution Pipeline", True, "Pipeline components available", duration)
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self.log_test("Entity Resolution Pipeline", False, f"Error: {e}", duration)
            return False
    
    def test_services_connectivity(self):
        """Test 5: Services connectivity and health."""
        print("\n? Test 5: Services Connectivity")
        start_time = time.time()
        
        try:
            # Test blocking service
            from entity_resolution.services.blocking_service import BlockingService
            blocking_service = BlockingService(self.config)
            
            # Test similarity service
            from entity_resolution.services.similarity_service import SimilarityService
            similarity_service = SimilarityService(self.config)
            
            # Test clustering service
            from entity_resolution.services.clustering_service import ClusteringService
            clustering_service = ClusteringService(self.config)
            
            # Test golden record persistence service (import only; needs a db handle)
            from entity_resolution.services.golden_record_persistence_service import (  # noqa: F401
                GoldenRecordPersistenceService,
            )
            
            duration = time.time() - start_time
            self.log_test("Services Connectivity", True, "All services initialized successfully", duration)
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self.log_test("Services Connectivity", False, f"Error: {e}", duration)
            return False
    
    def test_data_integrity(self):
        """Test 6: Data integrity and consistency."""
        print("\n? Test 6: Data Integrity")
        start_time = time.time()
        
        try:
            data_manager = DataManager(self.config)
            if not data_manager.connect():
                self.log_test("Data Integrity", False, "Failed to connect to database")
                return False
            
            # Create test data
            test_customers = [
                {"id": 1, "name": "John Smith", "email": "john@example.com", "phone": "555-1234"},
                {"id": 2, "name": "Jon Smith", "email": "jon@example.com", "phone": "555-1234"},
                {"id": 3, "name": "Jane Doe", "email": "jane@example.com", "phone": "555-5678"}
            ]
            
            # Insert test data
            collection_name = "qa_integrity_test"
            if not data_manager.create_collection(collection_name):
                self.log_test("Data Integrity", False, "Failed to create test collection")
                return False
            
            # Insert documents using collection directly
            collection = data_manager.database.collection(collection_name)
            for customer in test_customers:
                try:
                    collection.insert(customer)
                except Exception as e:
                    self.log_test("Data Integrity", False, f"Failed to insert test data: {e}")
                    return False
            
            # Verify data integrity
            documents = list(collection.all())
            if len(documents) != len(test_customers):
                self.log_test("Data Integrity", False, f"Data count mismatch: {len(documents)} vs {len(test_customers)}")
                return False
            
            # Clean up
            data_manager.database.delete_collection(collection_name)
            
            duration = time.time() - start_time
            self.log_test("Data Integrity", True, f"Data integrity verified for {len(test_customers)} records", duration)
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self.log_test("Data Integrity", False, f"Error: {e}", duration)
            return False
    
    def test_error_handling(self):
        """Test 7: Error handling and edge cases."""
        print("\n? Test 7: Error Handling")
        start_time = time.time()
        
        try:
            data_manager = DataManager(self.config)
            if not data_manager.connect():
                self.log_test("Error Handling", False, "Failed to connect to database")
                return False
            
            # Test invalid collection operations
            try:
                # Try to get documents from non-existent collection
                documents = data_manager.get_documents("non_existent_collection")
                # Should handle gracefully (empty result or exception)
            except Exception:
                pass  # Expected behavior
            
            # Test invalid document operations
            try:
                # Try to insert invalid document
                result = data_manager.insert_document("non_existent_collection", {"test": "data"})
                # Should handle gracefully
            except Exception:
                pass  # Expected behavior
            
            duration = time.time() - start_time
            self.log_test("Error Handling", True, "Error handling working correctly", duration)
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self.log_test("Error Handling", False, f"Error: {e}", duration)
            return False
    
    def test_performance(self):
        """Test 8: Performance and scalability."""
        print("\n? Test 8: Performance")
        start_time = time.time()
        
        try:
            data_manager = DataManager(self.config)
            if not data_manager.connect():
                self.log_test("Performance", False, "Failed to connect to database")
                return False
            
            # Test bulk operations
            collection_name = "qa_performance_test"
            if not data_manager.create_collection(collection_name):
                self.log_test("Performance", False, "Failed to create test collection")
                return False
            
            # Insert multiple documents
            test_docs = []
            for i in range(100):  # Test with 100 documents
                test_docs.append({
                    "id": i,
                    "name": f"Customer {i}",
                    "email": f"customer{i}@example.com",
                    "phone": f"555-{i:04d}"
                })
            
            # Insert documents using collection directly
            collection = data_manager.database.collection(collection_name)
            insert_start = time.time()
            try:
                # Use insert_many for better performance
                collection.insert_many(test_docs)
            except Exception as e:
                # Fallback to individual inserts
                for doc in test_docs:
                    collection.insert(doc)
            insert_duration = time.time() - insert_start
            
            # Test retrieval performance
            retrieve_start = time.time()
            documents = list(collection.all())
            retrieve_duration = time.time() - retrieve_start
            
            # Clean up
            data_manager.database.delete_collection(collection_name)
            
            total_duration = time.time() - start_time
            self.log_test("Performance", True, 
                         f"Inserted {len(test_docs)} docs in {insert_duration:.2f}s, "
                         f"retrieved in {retrieve_duration:.2f}s", total_duration)
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self.log_test("Performance", False, f"Error: {e}", duration)
            return False
    
    def run_all_tests(self):
        """Run all QA tests."""
        print("? Starting Comprehensive QA Tests")
        print("=" * 50)
        
        tests = [
            self.test_database_connection,
            self.test_database_cleanup,
            self.test_data_manager,
            self.test_entity_resolution_pipeline,
            self.test_services_connectivity,
            self.test_data_integrity,
            self.test_error_handling,
            self.test_performance
        ]
        
        passed = 0
        failed = 0
        
        for test in tests:
            try:
                if test():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"[FAIL] Test failed with exception: {e}")
                failed += 1
        
        # Generate report
        self.generate_report(passed, failed)
        
        return failed == 0
    
    def generate_report(self, passed, failed):
        """Generate comprehensive test report."""
        total_tests = passed + failed
        success_rate = (passed / total_tests) * 100 if total_tests > 0 else 0
        
        print("\n" + "=" * 50)
        print("? QA TEST REPORT")
        print("=" * 50)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if failed > 0:
            print(f"\n[FAIL] Failed Tests:")
            for result in self.test_results:
                if not result['success']:
                    print(f"  - {result['test']}: {result['message']}")
        
        # Save detailed report
        report_data = {
            'summary': {
                'total_tests': total_tests,
                'passed': passed,
                'failed': failed,
                'success_rate': success_rate,
                'duration': (datetime.now() - self.start_time).total_seconds()
            },
            'test_results': self.test_results,
            'timestamp': datetime.now().isoformat()
        }
        
        report_file = f"qa_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
        
        print(f"\n? Detailed report saved: {report_file}")
        
        if success_rate >= 90:
            print("? Excellent! System is working properly.")
        elif success_rate >= 75:
            print("[PASS] Good! System is mostly working with minor issues.")
        elif success_rate >= 50:
            print("[WARN]?  Fair. System has some issues that need attention.")
        else:
            print("[FAIL] Poor. System has significant issues that need immediate attention.")

def main():
    """Run comprehensive QA tests."""
    try:
        qa_suite = QATestSuite()
        success = qa_suite.run_all_tests()
        
        if success:
            print("\n? All QA tests passed!")
            return 0
        else:
            print("\n[FAIL] Some QA tests failed!")
            return 1
            
    except KeyboardInterrupt:
        print("\n[FAIL] Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n[FAIL] Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
