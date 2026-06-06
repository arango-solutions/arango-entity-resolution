"""
Vector Blocking Example

This example demonstrates how to use vector-based entity resolution with the
VectorBlockingStrategy and EmbeddingService.

Vector blocking uses semantic similarity (via embeddings) to find candidate pairs
that traditional exact or text-based blocking might miss. It's particularly effective
for fuzzy matching of records with typos, abbreviations, or different phrasings.

Prerequisites:
- ArangoDB running (default: localhost:8529)
- sentence-transformers and torch installed:
  pip install sentence-transformers torch

Usage:
    python examples/vector_blocking_example.py

This example will:
1. Create sample customer data
2. Generate vector embeddings
3. Perform vector-based blocking
4. Compare with traditional blocking methods
5. Display results and statistics
"""

import os
import sys
from datetime import datetime

# Add src directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from entity_resolution.utils.database import DatabaseManager
from entity_resolution.services.embedding_service import EmbeddingService
from entity_resolution.strategies import (
    VectorBlockingStrategy,
    CollectBlockingStrategy,
    BM25BlockingStrategy
)


def print_section(title: str):
    """Print a formatted section header"""
    print(f"\n{'='*70}")
    print(f"{title:^70}")
    print(f"{'='*70}\n")


def create_sample_data(db, collection_name: str):
    """Create sample customer data with intentional fuzzy duplicates"""
    print_section("Step 1: Creating Sample Customer Data")
    
    # Create collection
    if db.has_collection(collection_name):
        db.delete_collection(collection_name)
    
    collection = db.create_collection(collection_name)
    
    # Sample data with intentional duplicates (typos, abbreviations, etc.)
    customers = [
        # Group 1: John Smith variations
        {
            '_key': 'cust_001',
            'name': 'John Smith',
            'company': 'Acme Corporation',
            'email': 'john.smith@acme.com',
            'address': '123 Main Street, New York, NY 10001',
            'phone': '555-1234'
        },
        {
            '_key': 'cust_002',
            'name': 'John R Smith',  # Middle initial added
            'company': 'Acme Corp',   # Abbreviated
            'email': 'j.smith@acme.com',  # Different format
            'address': '123 Main St, New York, NY',  # Abbreviated
            'phone': '555-1234'
        },
        {
            '_key': 'cust_003',
            'name': 'Jon Smith',  # Typo in first name
            'company': 'Acme Corporation',
            'email': 'jsmith@acme.com',
            'address': '123 Main Street, NYC',
            'phone': '(555) 1234'  # Different format
        },
        
        # Group 2: Jane Doe variations
        {
            '_key': 'cust_004',
            'name': 'Jane Doe',
            'company': 'TechCo Incorporated',
            'email': 'jane.doe@techco.com',
            'address': '456 Oak Avenue, San Francisco, CA 94102',
            'phone': '555-5678'
        },
        {
            '_key': 'cust_005',
            'name': 'Jane M. Doe',  # Middle initial
            'company': 'TechCo Inc',  # Abbreviated
            'email': 'jdoe@techco.com',
            'address': '456 Oak Ave, San Francisco, CA',
            'phone': '555-5678'
        },
        
        # Group 3: Robert Johnson (unique, no duplicates)
        {
            '_key': 'cust_006',
            'name': 'Robert Johnson',
            'company': 'Global Enterprises LLC',
            'email': 'robert.j@global-ent.com',
            'address': '789 Elm Boulevard, Chicago, IL 60601',
            'phone': '555-9999'
        },
        
        # Group 4: Maria Garcia variations
        {
            '_key': 'cust_007',
            'name': 'Maria Garcia',
            'company': 'Sunrise Solutions',
            'email': 'maria@sunrise.io',
            'address': '321 Pine Street, Austin, TX 78701',
            'phone': '555-3333'
        },
        {
            '_key': 'cust_008',
            'name': 'Maria L Garcia',  # Middle initial
            'company': 'Sunrise Solutions Inc',  # Inc added
            'email': 'm.garcia@sunrise.io',
            'address': '321 Pine St, Austin, Texas',  # State spelled out
            'phone': '555-3333'
        },
        
        # Group 5: Michael Chen (unique)
        {
            '_key': 'cust_009',
            'name': 'Michael Chen',
            'company': 'DataViz Analytics',
            'email': 'mchen@dataviz.com',
            'address': '555 Market Street, Seattle, WA 98101',
            'phone': '555-7777'
        },
        
        # Group 6: Sarah Williams variations
        {
            '_key': 'cust_010',
            'name': 'Sarah Williams',
            'company': 'CloudFirst Technologies',
            'email': 'sarah.w@cloudfirst.com',
            'address': '999 Broadway, Boston, MA 02101',
            'phone': '555-4444'
        },
        {
            '_key': 'cust_011',
            'name': 'Sara Williams',  # Typo (Sarah vs Sara)
            'company': 'CloudFirst Tech',  # Abbreviated
            'email': 'swilliams@cloudfirst.com',
            'address': '999 Broadway, Boston, Massachusetts',
            'phone': '(555) 444-4444'  # Different format
        }
    ]
    
    # Insert documents
    for customer in customers:
        collection.insert(customer)
    
    print(f"[OK] Created collection '{collection_name}' with {len(customers)} customers")
    print(f"[OK] Intentional duplicate groups:")
    print(f"  - John Smith (3 variations: cust_001, cust_002, cust_003)")
    print(f"  - Jane Doe (2 variations: cust_004, cust_005)")
    print(f"  - Maria Garcia (2 variations: cust_007, cust_008)")
    print(f"  - Sarah Williams (2 variations: cust_010, cust_011)")
    print(f"  - Robert Johnson (unique: cust_006)")
    print(f"  - Michael Chen (unique: cust_009)")
    
    return customers


def generate_embeddings(db, collection_name: str):
    """Generate vector embeddings for all customers"""
    print_section("Step 2: Generating Vector Embeddings")
    
    # Initialize embedding service
    print("Initializing EmbeddingService with 'all-MiniLM-L6-v2' model...")
    embedding_service = EmbeddingService(
        model_name='all-MiniLM-L6-v2',  # Fast, 384-dim embeddings
        device='cpu'  # Use 'cuda' if GPU available
    )
    
    # Generate embeddings for all documents
    print("Generating embeddings (this may take a few seconds)...")
    stats = embedding_service.ensure_embeddings_exist(
        collection_name=collection_name,
        text_fields=['name', 'company', 'email', 'address'],
        database_name=db.name
    )
    
    print(f"[OK] Generated embeddings for {stats['generated']} documents")
    print(f"[OK] Embedding dimension: {embedding_service.embedding_dim}")
    print(f"[OK] Model: {embedding_service.model_name}")
    print(f"[OK] Coverage: {stats['updated']}/{stats['total_docs']} documents")
    
    return stats


def run_vector_blocking(db, collection_name: str):
    """Run vector-based blocking"""
    print_section("Step 3: Vector-Based Blocking (Tier 3)")
    
    # Create vector blocking strategy. Requires ArangoDB 3.12+; create the
    # native vector index now that embeddings exist (no brute-force fallback).
    print("Initializing VectorBlockingStrategy (native vector index)...")
    strategy = VectorBlockingStrategy(
        db=db,
        collection=collection_name,
        similarity_threshold=0.7,  # 70% similarity minimum
        limit_per_entity=20,
        create_vector_index=True,
    )
    
    # Generate candidates
    print("Finding similar customer pairs using vector similarity...")
    pairs = strategy.generate_candidates()
    
    # Display results
    print(f"\n[OK] Found {len(pairs)} candidate pairs")
    
    stats = strategy.get_statistics()
    print(f"[OK] Execution time: {stats['execution_time_seconds']:.2f} seconds")
    print(f"[OK] Embedding coverage: {stats['embedding_coverage_percent']:.1f}%")
    
    # Show top pairs by similarity
    print(f"\nTop candidate pairs (sorted by similarity):")
    sorted_pairs = sorted(pairs, key=lambda p: p['similarity'], reverse=True)
    
    collection = db.collection(collection_name)
    for i, pair in enumerate(sorted_pairs[:10], 1):
        doc1 = collection.get(pair['doc1_key'])
        doc2 = collection.get(pair['doc2_key'])
        
        print(f"\n{i}. Similarity: {pair['similarity']:.3f}")
        print(f"   {pair['doc1_key']}: {doc1['name']} at {doc1['company']}")
        print(f"   {pair['doc2_key']}: {doc2['name']} at {doc2['company']}")
    
    return pairs, stats


def run_exact_blocking(db, collection_name: str):
    """Run exact (Tier 1) blocking for comparison"""
    print_section("Step 4: Exact Blocking (Tier 1) - For Comparison")
    
    print("Running CollectBlockingStrategy with exact phone matching...")
    strategy = CollectBlockingStrategy(
        db=db,
        collection=collection_name,
        blocking_fields=['phone'],
        filters={'phone': {'not_null': True}}
    )
    
    pairs = strategy.generate_candidates()
    
    print(f"[OK] Found {len(pairs)} candidate pairs")
    print(f"[OK] Execution time: {strategy.get_statistics()['execution_time_seconds']:.2f} seconds")
    
    return pairs


def run_fuzzy_blocking(db, collection_name: str):
    """Run fuzzy text blocking (Tier 2) for comparison"""
    print_section("Step 5: Fuzzy Text Blocking (Tier 2) - For Comparison")
    
    # First, create ArangoSearch view
    view_name = f"{collection_name}_bm25_view"
    
    # Check if view exists by listing views
    existing_views = [v['name'] for v in db.views()]
    if view_name not in existing_views:
        print(f"Creating ArangoSearch view '{view_name}'...")
        db.create_view(
            name=view_name,
            view_type='arangosearch',
            properties={
                'links': {
                    collection_name: {
                        'analyzers': ['text_en'],
                        'includeAllFields': False,
                        'fields': {
                            'name': {},
                            'company': {}
                        }
                    }
                }
            }
        )
    
    print("Running BM25BlockingStrategy with fuzzy text matching...")
    strategy = BM25BlockingStrategy(
        db=db,
        collection=collection_name,
        search_view=view_name,
        search_field='name',  # Search on name field
        bm25_threshold=1.0,
        limit_per_entity=20
    )
    
    pairs = strategy.generate_candidates()
    
    print(f"[OK] Found {len(pairs)} candidate pairs")
    print(f"[OK] Execution time: {strategy.get_statistics()['execution_time_seconds']:.2f} seconds")
    
    return pairs


def compare_blocking_methods(vector_pairs, exact_pairs, fuzzy_pairs):
    """Compare the three blocking methods"""
    print_section("Step 6: Comparing Blocking Methods")
    
    # Convert to sets of (doc1, doc2) tuples for comparison
    vector_set = {(p['doc1_key'], p['doc2_key']) for p in vector_pairs}
    exact_set = {(p['doc1_key'], p['doc2_key']) for p in exact_pairs}
    fuzzy_set = {(p['doc1_key'], p['doc2_key']) for p in fuzzy_pairs}
    
    # Find unique pairs in each method
    vector_only = vector_set - exact_set - fuzzy_set
    exact_only = exact_set - vector_set - fuzzy_set
    fuzzy_only = fuzzy_set - vector_set - exact_set
    
    # Find overlaps
    all_three = vector_set & exact_set & fuzzy_set
    vector_and_exact = (vector_set & exact_set) - fuzzy_set
    vector_and_fuzzy = (vector_set & fuzzy_set) - exact_set
    exact_and_fuzzy = (exact_set & fuzzy_set) - vector_set
    
    print("Blocking Method Comparison:")
    print(f"\n{'Method':<25} {'Total Pairs':<15} {'Unique Pairs':<15}")
    print(f"{'-'*55}")
    print(f"{'Vector (Tier 3)':<25} {len(vector_set):<15} {len(vector_only):<15}")
    print(f"{'Exact (Tier 1)':<25} {len(exact_set):<15} {len(exact_only):<15}")
    print(f"{'Fuzzy Text (Tier 2)':<25} {len(fuzzy_set):<15} {len(fuzzy_only):<15}")
    
    print(f"\nOverlaps:")
    print(f"  All three methods: {len(all_three)} pairs")
    print(f"  Vector + Exact: {len(vector_and_exact)} pairs")
    print(f"  Vector + Fuzzy: {len(vector_and_fuzzy)} pairs")
    print(f"  Exact + Fuzzy: {len(exact_and_fuzzy)} pairs")
    
    # Combined results
    combined = vector_set | exact_set | fuzzy_set
    print(f"\n  Combined total (union): {len(combined)} unique pairs")
    
    print(f"\nKey Insight:")
    print(f"  Vector blocking found {len(vector_only)} pairs that other methods missed")
    print(f"  These are typically fuzzy matches with semantic similarity")
    
    return {
        'vector': vector_set,
        'exact': exact_set,
        'fuzzy': fuzzy_set,
        'combined': combined
    }


def demonstrate_geographic_blocking(db, collection_name: str):
    """Demonstrate vector blocking with geographic constraints"""
    print_section("Step 8: Geographic Blocking (Optional Constraint)")
    
    # First, add a 'state' field to documents for geographic blocking
    collection = db.collection(collection_name)
    
    print("Adding state field for geographic blocking demo...")
    states = {
        'cust_001': 'NY', 'cust_002': 'NY', 'cust_003': 'NY',
        'cust_004': 'CA', 'cust_005': 'CA',
        'cust_006': 'IL',
        'cust_007': 'TX', 'cust_008': 'TX',
        'cust_009': 'WA',
        'cust_010': 'MA', 'cust_011': 'MA'
    }
    
    for key, state in states.items():
        collection.update({'_key': key, 'state': state})
    
    # Run vector blocking with geographic constraint
    print("\nRunning vector blocking with geographic constraint (same state only)...")
    strategy = VectorBlockingStrategy(
        db=db,
        collection=collection_name,
        similarity_threshold=0.6,
        blocking_field='state',  # Only compare within same state
        create_vector_index=True,
    )
    
    pairs = strategy.generate_candidates()
    
    print(f"[OK] Found {len(pairs)} candidate pairs (same state only)")
    print(f"\nThis ensures cross-state duplicates are not matched,")
    print(f"which is useful when records from different states are known to be distinct.")


def main():
    """Main execution flow"""
    # Configuration
    COLLECTION_NAME = "vector_blocking_demo"
    
    print_section("Vector Blocking Example - Entity Resolution")
    print("This example demonstrates semantic similarity-based blocking using")
    print("vector embeddings. It's particularly effective for fuzzy matching.")
    
    # Initialize database
    print("\nConnecting to ArangoDB...")
    db_manager = DatabaseManager()
    db = db_manager.get_database('entity_resolution')
    print(f"[OK] Connected to database '{db.name}'")
    
    try:
        # Run the example workflow
        create_sample_data(db, COLLECTION_NAME)
        generate_embeddings(db, COLLECTION_NAME)
        
        vector_pairs, vector_stats = run_vector_blocking(db, COLLECTION_NAME)
        exact_pairs = run_exact_blocking(db, COLLECTION_NAME)
        fuzzy_pairs = run_fuzzy_blocking(db, COLLECTION_NAME)
        
        compare_blocking_methods(vector_pairs, exact_pairs, fuzzy_pairs)
        demonstrate_geographic_blocking(db, COLLECTION_NAME)
        
        # Summary
        print_section("Summary")
        print("[OK] Vector blocking successfully demonstrated!")
        print(f"\nKey Takeaways:")
        print(f"  1. Vector blocking uses semantic similarity (embeddings)")
        print(f"  2. It captures fuzzy matches that exact blocking misses")
        print(f"  3. Works well for typos, abbreviations, and variations")
        print(f"  4. Can be combined with other blocking strategies (Tier 1, 2, 3)")
        print(f"  5. Configurable threshold and geographic constraints")
        
        print(f"\nNext Steps:")
        print(f"  - Adjust similarity_threshold based on your data")
        print(f"  - Combine with exact and fuzzy blocking for best results")
        print(f"  - See config/vector_search_setup.md for configuration details")
        
    finally:
        # Cleanup
        print("\nCleaning up...")
        if db.has_collection(COLLECTION_NAME):
            db.delete_collection(COLLECTION_NAME)
        view_name = f"{COLLECTION_NAME}_bm25_view"
        try:
            # Try to delete view if it exists
            db.delete_view(view_name)
        except:
            pass  # View doesn't exist or already deleted
        print("[OK] Cleanup complete")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

