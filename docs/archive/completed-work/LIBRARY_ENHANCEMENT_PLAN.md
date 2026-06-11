# ArangoER Library Enhancement Plan
## Adding Advanced Entity Resolution Capabilities

**Date:** November 12, 2025 (original), March 16, 2026 (updated), April 28, 2026 (Phase 4 audit)  
**Status:** All Phases (0–4) Completed  
**Goal:** Enhance arango-entity-resolution library with production-proven ER features

> **Archived (completed initiative).** All phases shipped through v3.5.1. This document
> is retained as a historical record. Forward-looking follow-ups that grew out of this
> plan are tracked in the living roadmap — see the [PRD](../../PRD.md) ("Other Future
> Investigation Areas") and the [MCP API migration plan](../../development/MAINTAINABILITY_API_MIGRATION_PLAN.md).

---

## Executive Summary

This plan outlines the enhancement of the arango-entity-resolution library to support advanced entity resolution operations that have been proven effective in production environments. The enhancements add six core capabilities while maintaining the library's generic, reusable nature.

### Key Enhancements

1. **CollectBlockingStrategy** - Efficient composite key blocking without cartesian products
2. **BM25BlockingStrategy** - Fast fuzzy matching using ArangoSearch
3. **BatchSimilarityService** - Optimized batch similarity computation
4. **SimilarityEdgeService** - Bulk edge creation with metadata
5. **WCCClusteringService** - Weakly Connected Components clustering with multiple algorithms
6. **Cross-Platform GPU Embedding Runtime** - ONNX Runtime provider abstraction for Apple Silicon and Linux

### Design Principles

- **Generic & Configurable**: No hardcoded collection names, field names, or business logic
- **Performance-Optimized**: Proven patterns that scale to hundreds of thousands of records
- **Multiple Algorithms**: Support for different approaches (AQL, GAE, Python fallbacks)
- **Backward Compatible**: New features don't break existing code
- **Well-Documented**: Comprehensive API docs and usage examples
- **Performance Portability**: GPU acceleration where it materially helps, with deterministic CPU fallback

---

## Current State Analysis

### Existing Library Capabilities

The library currently provides:
- `BlockingService` - Basic field-based blocking
- `SimilarityService` - Fellegi-Sunter similarity computation
- `ClusteringService` - Basic graph-based clustering
- `BulkBlockingService` - Bulk operations (underutilized)
- Foxx service APIs for server-side operations

### Gaps Identified

The following operations are commonly implemented directly in projects but should be library features:

| Feature | Value | Current Status | Priority |
|---------|-------|----------------|----------|
| COLLECT-based blocking | High - Performance critical | Not available | High |
| BM25 fuzzy blocking | High - 400x faster than Levenshtein | Not available | High |
| Batch similarity | High - Performance critical | Partial | High |
| Bulk edge creation | High - Standard pattern | Not available | High |
| WCC clustering | High - Standard algorithm | Basic only | High |
| Multi-strategy orchestration | Medium - Convenience | Not available | Medium |
| Cross-platform GPU embedding inference | High - Embedding throughput and latency | Not available as standardized provider layer | High |

---

## Enhancement Details

### 1. CollectBlockingStrategy

**Purpose:** Generate candidate pairs using ArangoDB's COLLECT operation for composite key blocking

**Key Features:**
- Composite key blocking (multiple fields)
- Configurable filters per field (not_null, min_length, not_equal, etc.)
- Block size limits (min/max) to prevent explosion
- No cartesian products (O(n) complexity)
- Generic - works with any collection and fields

**API Design:**

```python
class CollectBlockingStrategy:
"""
COLLECT-based blocking for efficient composite key matching.

Uses ArangoDB's COLLECT operation to group documents by blocking keys,
then generates candidate pairs only within small blocks. Avoids
expensive cartesian products.

Performance: O(n) where n = number of documents
"""

def __init__(
self,
db: StandardDatabase,
collection: str,
blocking_fields: List[str],
filters: Optional[Dict[str, Dict[str, Any]]] = None,
max_block_size: int = 100,
min_block_size: int = 2,
computed_fields: Optional[Dict[str, str]] = None
):
"""
Initialize COLLECT-based blocking strategy.

Args:
db: ArangoDB database connection
collection: Source collection name
blocking_fields: List of fields to use as composite blocking key
filters: Optional filters per field, e.g.:
{
"phone": {
"not_null": True,
"not_equal": ["0", "00000000000"],
"min_length": 10
},
"state": {"not_null": True}
}
max_block_size: Skip blocks larger than this (likely bad data)
min_block_size: Skip blocks smaller than this (no pairs to generate)
computed_fields: Optional computed fields, e.g.:
{"zip5": "LEFT(postal_code, 5)"}
"""
pass

def generate_candidates(self) -> List[Dict[str, Any]]:
"""
Generate candidate pairs using COLLECT-based blocking.

Returns:
List of candidate pairs with metadata:
[
{
"doc1_key": "123",
"doc2_key": "456",
"blocking_keys": {"phone": "5551234567", "state": "CA"},
"block_size": 3
},
...
]
"""
pass

def get_statistics(self) -> Dict[str, Any]:
"""
Get blocking statistics.

Returns:
{
"total_blocks": 1234,
"total_pairs": 45678,
"avg_block_size": 3.2,
"max_block_size": 15,
"skipped_blocks": 5,
"execution_time_seconds": 2.3
}
"""
pass
```

**Implementation Notes:**
- Use AQL COLLECT with INTO to group documents
- Generate pairs within blocks using nested loops in AQL
- Support both simple field filters and computed fields
- Return pairs with metadata for debugging and analysis

---

### 2. BM25BlockingStrategy

**Purpose:** Fast fuzzy matching using ArangoSearch BM25 algorithm

**Key Features:**
- BM25 scoring for text similarity (400x faster than Levenshtein for initial filtering)
- Uses ArangoSearch views
- Configurable BM25 threshold
- Limit results per entity to prevent explosion
- Optional blocking field for geographic/categorical constraints
- Generic - works with any collection and search view

**API Design:**

```python
class BM25BlockingStrategy:
"""
BM25-based fuzzy blocking using ArangoSearch.

Uses ArangoDB's BM25 scoring for fast text similarity matching.
Much faster than Levenshtein for initial candidate generation,
particularly effective for name matching.

Performance: O(n log n) where n = number of documents
"""

def __init__(
self,
db: StandardDatabase,
collection: str,
search_view: str,
search_field: str,
bm25_threshold: float = 2.0,
limit_per_entity: int = 20,
blocking_field: Optional[str] = None,
filters: Optional[Dict[str, Dict[str, Any]]] = None,
analyzer: str = "text_en"
):
"""
Initialize BM25-based blocking strategy.

Args:
db: ArangoDB database connection
collection: Source collection name
search_view: ArangoSearch view name
search_field: Field to perform BM25 search on
bm25_threshold: Minimum BM25 score to include
limit_per_entity: Max candidates per source entity
blocking_field: Optional field to constrain matches (e.g., state)
filters: Optional filters per field
analyzer: ArangoSearch analyzer to use
"""
pass

def generate_candidates(self) -> List[Dict[str, Any]]:
"""
Generate candidate pairs using BM25 fuzzy matching.

Returns:
List of candidate pairs with BM25 scores:
[
{
"doc1_key": "123",
"doc2_key": "456",
"bm25_score": 5.2,
"search_field": "company_name",
"blocking_field_value": "CA"
},
...
]
"""
pass

def get_statistics(self) -> Dict[str, Any]:
"""
Get blocking statistics including BM25 score distribution.

Returns:
{
"total_pairs": 12345,
"avg_bm25_score": 3.8,
"max_bm25_score": 12.4,
"min_bm25_score": 2.0,
"execution_time_seconds": 5.7
}
"""
pass
```

**Implementation Notes:**
- Requires pre-existing ArangoSearch view
- Use SEARCH with PHRASE and BM25 scoring
- Apply LIMIT per source entity to prevent explosion
- Optional blocking field provides additional constraint
- Return BM25 scores for downstream filtering/ranking

---

### 3. BatchSimilarityService

**Purpose:** Compute similarity scores for candidate pairs with optimized batch document fetching

**Key Features:**
- Batch document fetching (reduces queries from 100K+ to ~10-15)
- Multiple similarity algorithms (Jaro-Winkler, Levenshtein, Jaccard, custom)
- Weighted field comparison
- Configurable field normalization
- Progress callbacks for long-running operations
- Generic - works with any collection and fields

**API Design:**

```python
class BatchSimilarityService:
"""
Batch similarity computation with optimized document fetching.

Fetches all required documents in batches, then computes similarities
in-memory. Dramatically reduces network overhead compared to
per-pair queries.

Performance: ~100K+ pairs/second for Jaro-Winkler
"""

def __init__(
self,
db: StandardDatabase,
collection: str,
field_weights: Dict[str, float],
similarity_algorithm: Union[str, Callable] = "jaro_winkler",
batch_size: int = 5000,
normalization_config: Optional[Dict[str, Any]] = None,
progress_callback: Optional[Callable[[int, int], None]] = None
):
"""
Initialize batch similarity service.

Args:
db: ArangoDB database connection
collection: Source collection name
field_weights: Field names and their weights, e.g.:
{
"company_name": 0.4,
"ceo_name": 0.3,
"address": 0.2,
"city": 0.1
}
similarity_algorithm: Algorithm name or callable:
- "jaro_winkler" (default)
- "levenshtein"
- "jaccard"
- Custom callable: (str1, str2) -> float
batch_size: Documents to fetch per query
normalization_config: Field normalization options:
{
"strip": True,
"lowercase": True, # or "uppercase": True
"remove_punctuation": False,
"remove_extra_whitespace": True
}
progress_callback: Optional callback(current, total)
"""
pass

def compute_similarities(
self,
candidate_pairs: List[Tuple[str, str]],
threshold: float = 0.75,
return_all: bool = False
) -> List[Tuple[str, str, float]]:
"""
Compute similarities for candidate pairs.

Args:
candidate_pairs: List of (doc1_key, doc2_key) tuples
threshold: Minimum similarity to include in results
return_all: If True, return all pairs (even below threshold)

Returns:
List of (doc1_key, doc2_key, similarity_score) tuples
"""
pass

def compute_similarities_detailed(
self,
candidate_pairs: List[Tuple[str, str]],
threshold: float = 0.75
) -> List[Dict[str, Any]]:
"""
Compute similarities with detailed per-field scores.

Returns:
List of detailed similarity results:
[
{
"doc1_key": "123",
"doc2_key": "456",
"overall_score": 0.87,
"field_scores": {
"company_name": 0.95,
"ceo_name": 0.82,
"address": 0.78,
"city": 0.92
},
"weighted_score": 0.87
},
...
]
"""
pass

def get_statistics(self) -> Dict[str, Any]:
"""
Get computation statistics.

Returns:
{
"pairs_processed": 50000,
"pairs_above_threshold": 3421,
"documents_cached": 15234,
"batch_count": 4,
"execution_time_seconds": 12.8,
"pairs_per_second": 3906
}
"""
pass
```

**Implementation Notes:**
- Extract unique document keys from all pairs
- Fetch documents in configurable batches
- Cache all documents in memory
- Compute similarities using selected algorithm
- Support multiple algorithms via pluggable interface
- Provide progress feedback for long operations

---

### 4. SimilarityEdgeService

**Purpose:** Create similarity edges in bulk with metadata

**Key Features:**
- Bulk edge insertion (batched for performance)
- Automatic _from/_to formatting
- Configurable metadata fields
- Timestamp tracking
- Method/algorithm tracking
- Generic - works with any edge collection

**API Design:**

```python
class SimilarityEdgeService:
"""
Bulk creation of similarity edges with metadata.

Creates edges between similar entities in batches, with
comprehensive metadata for tracking and analysis.

Performance: ~10K+ edges/second
"""

def __init__(
self,
db: StandardDatabase,
edge_collection: str = "similarTo",
vertex_collection: Optional[str] = None,
batch_size: int = 1000,
auto_create_collection: bool = True
):
"""
Initialize similarity edge service.

Args:
db: ArangoDB database connection
edge_collection: Edge collection name
vertex_collection: Vertex collection name (for _from/_to formatting)
batch_size: Edges to insert per batch
auto_create_collection: Create edge collection if it doesn't exist
"""
pass

def create_edges(
self,
matches: List[Tuple[str, str, float]],
metadata: Optional[Dict[str, Any]] = None,
bidirectional: bool = False
) -> int:
"""
Create similarity edges in bulk.

Args:
matches: List of (doc1_key, doc2_key, score) tuples
metadata: Additional metadata to include in all edges:
{
"method": "hybrid_blocking",
"algorithm": "jaro_winkler",
"threshold": 0.75,
"run_id": "run_20251112_143022"
}
bidirectional: If True, create edges in both directions

Returns:
Number of edges created
"""
pass

def create_edges_detailed(
self,
matches: List[Dict[str, Any]],
bidirectional: bool = False
) -> int:
"""
Create edges with per-edge metadata.

Args:
matches: List of detailed match records:
[
{
"doc1_key": "123",
"doc2_key": "456",
"similarity": 0.87,
"field_scores": {...},
"blocking_method": "phone_state"
},
...
]
bidirectional: If True, create edges in both directions

Returns:
Number of edges created
"""
pass

def clear_edges(
self,
method: Optional[str] = None,
older_than: Optional[str] = None
) -> int:
"""
Clear similarity edges.

Args:
method: Only clear edges with this method (optional)
older_than: Only clear edges older than this ISO timestamp (optional)

Returns:
Number of edges removed
"""
pass

def get_statistics(self) -> Dict[str, Any]:
"""
Get edge creation statistics.

Returns:
{
"edges_created": 12345,
"batches_processed": 13,
"avg_batch_size": 949,
"execution_time_seconds": 1.2,
"edges_per_second": 10287
}
"""
pass
```

**Implementation Notes:**
- Use insert_many for batch operations
- Automatically add timestamps
- Support both simple and detailed metadata
- Provide cleanup operations for iterative workflows

---

### 5. WCCClusteringService

**Purpose:** Find connected components in similarity graphs

**Key Features:**
- AQL graph traversal (server-side, works on all modern ArangoDB)
- Configurable minimum cluster size
- Cluster storage with metadata
- Statistics and validation
- Generic - works with any edge collection
- Future: GAE support for very large graphs

**API Design:**

```python
class WCCClusteringService:
"""
Weakly Connected Components clustering.

Finds connected components in the similarity graph using
AQL graph traversal (server-side, efficient, works everywhere).

Future enhancement: GAE (Graph Analytics Engine) support for
extremely large graphs requiring additional backend capabilities.
"""

def __init__(
self,
db: StandardDatabase,
edge_collection: str = "similarTo",
cluster_collection: str = "entity_clusters",
vertex_collection: Optional[str] = None,
min_cluster_size: int = 2,
graph_name: Optional[str] = None
):
"""
Initialize WCC clustering service.

Args:
db: ArangoDB database connection
edge_collection: Edge collection containing similarity edges
cluster_collection: Collection to store cluster results
vertex_collection: Vertex collection name
min_cluster_size: Minimum entities per cluster to store
graph_name: Named graph to use (optional, can be created on-the-fly)

Note:
Uses AQL graph traversal for clustering. This is server-side,
efficient, and works on all modern ArangoDB installations (3.9+).
"""
pass

def cluster(
self,
store_results: bool = True,
truncate_existing: bool = True
) -> List[List[str]]:
"""
Run WCC clustering on similarity edges using AQL graph traversal.

Args:
store_results: Store clusters in cluster_collection
truncate_existing: Clear existing clusters before storing

Returns:
List of clusters, each cluster is a list of document keys:
[
["doc1", "doc2", "doc3"], # Cluster 1
["doc4", "doc5"], # Cluster 2
...
]
"""
pass

def _find_connected_components_aql(self) -> List[List[str]]:
"""
Use AQL graph traversal to find connected components.

Implementation approach:
1. Get all unique vertices from edges
2. For each unvisited vertex, traverse to find its component
3. Use AQL graph traversal (FOR v, e, p IN 0..999999 ANY ...)
4. Mark visited vertices to avoid duplicates

This is server-side and efficient for graphs up to millions of edges.
"""
pass

def get_cluster_by_member(self, member_key: str) -> Optional[Dict[str, Any]]:
"""
Find cluster containing a specific member.

Args:
member_key: Document key to search for

Returns:
Cluster record or None if not found
"""
pass

def get_statistics(self) -> Dict[str, Any]:
"""
Get clustering statistics.

Returns:
{
"total_clusters": 234,
"total_entities_clustered": 1523,
"avg_cluster_size": 6.5,
"max_cluster_size": 45,
"min_cluster_size": 2,
"cluster_size_distribution": {
"2": 120,
"3": 56,
"4-10": 45,
"11-50": 13
},
"algorithm_used": "aql_graph",
"execution_time_seconds": 3.4
}
"""
pass

def validate_clusters(self) -> Dict[str, Any]:
"""
Validate cluster quality and consistency.

Returns:
{
"valid": True,
"issues": [],
"checks_performed": [
"no_overlapping_clusters",
"all_edges_respected",
"min_size_requirement"
]
}
"""
pass
```

**Implementation Notes:**
- Use AQL graph traversal (server-side, works on all ArangoDB 3.9+)
- Iterative approach: find one component at a time, mark visited vertices
- Store clusters with comprehensive metadata
- Provide validation and quality metrics
- Future enhancement: GAE support for extremely large graphs (millions of edges)

---

### 6. Cross-Platform GPU Embedding Runtime

**Purpose:** Provide a single embedding runtime abstraction with platform-specific GPU providers for Apple Silicon and Linux.

**Key Features:**
- ONNX Runtime provider abstraction (`cpu`, `coreml`, `cuda`, `tensorrt`, `auto`)
- Provider selection by platform with explicit fallback chain
- Deterministic CPU fallback for provider init failures and unsupported operators
- Runtime metadata fields for requested vs resolved provider
- Feature flags for per-model provider rollout and emergency CPU override
- Compatibility matrix and benchmark gating before default changes

**Provider Resolution Rules:**
- Apple Silicon macOS: `coreml -> cpu`
- Linux NVIDIA: `tensorrt -> cuda -> cpu` (TensorRT opt-in first)
- Other platforms: `cpu`

**API Design:**

```python
class EmbeddingInferenceBackend(Protocol):
    """Backend interface for embedding model inference."""

    def load_model(self) -> None:
        ...

    def infer(self, texts: List[str], batch_size: int) -> List[List[float]]:
        ...

    def health(self) -> Dict[str, Any]:
        ...

    def provider_info(self) -> Dict[str, Any]:
        ...


class OnnxRuntimeEmbeddingBackend:
    """
    ONNX Runtime embedding backend with platform-aware provider selection.
    """

    def __init__(
        self,
        model_path: str,
        provider: str = "auto",
        provider_options: Optional[Dict[str, Any]] = None,
        fallback_to_cpu: bool = True,
    ):
        ...

    def resolve_provider(self, requested: str) -> str:
        """
        Resolve to concrete provider based on platform/provider availability.
        """
        ...
```

**Implementation Notes:**
- Keep existing PyTorch embedding path available during migration
- Introduce runtime/provider config as additive fields
- Keep CPU as effective default until parity/quality/performance gates pass
- Gate default promotion (`provider=auto`) on CI parity and benchmark results

---

## Implementation Plan

### Phase 0: GPU Foundation Track (Week 1-2, parallel) — COMPLETED

**Status:** Completed in Release 3.3.0 (March 2026)

**Deliverables:**
1. ~~Runtime/provider config surface for embeddings~~ DONE
2. ~~ONNX Runtime backend scaffold~~ DONE
3. ~~Provider resolver (`coreml`, `cuda`, `tensorrt`, `cpu`)~~ DONE
4. ~~Startup health checks and fallback metrics~~ DONE
5. ~~Initial benchmark harness and CPU baselines~~ DONE

**Tasks:**
- [x] Add embedding config fields: `runtime`, `provider`, `provider_options`, `onnx_model_path`
- [x] Add provider resolution logic with platform-aware priorities
- [x] Add `requested_provider` and `resolved_provider` to embedding metadata
- [x] Add provider fallback counter and startup diagnostics
- [x] Add smoke tests for provider selection and fallback behavior

See `docs/development/PHASE_0_COMPLETION_NOTES.md` for full details.

---

### Phase 1: Core Blocking Strategies (Week 1-2)

**Deliverables:**
1. `CollectBlockingStrategy` class
2. `BM25BlockingStrategy` class
3. Unit tests for both strategies
4. Integration tests with sample data
5. Performance benchmarks
6. API documentation

**Tasks:**
- [ ] Create `strategies/` directory under `services/`
- [ ] Implement `CollectBlockingStrategy`
- [ ] Implement `BM25BlockingStrategy`
- [ ] Create base `BlockingStrategy` abstract class
- [ ] Write comprehensive tests
- [ ] Document usage patterns
- [ ] Add examples to docs

**Success Criteria:**
- Both strategies work with generic collections
- Performance matches or exceeds current implementations
- All tests passing
- API documentation complete

---

### Phase 2: Similarity & Edge Services (Week 3-4)

**Deliverables:**
1. Enhanced `BatchSimilarityService` class
2. New `SimilarityEdgeService` class
3. Support for multiple similarity algorithms
4. Unit and integration tests
5. Performance benchmarks
6. API documentation

**Tasks:**
- [ ] Create `BatchSimilarityService` (refactor existing SimilarityService)
- [ ] Implement pluggable similarity algorithms
- [ ] Add field normalization options
- [ ] Create `SimilarityEdgeService`
- [ ] Implement bulk edge operations
- [ ] Write comprehensive tests
- [ ] Document usage patterns
- [ ] Add examples to docs

**Success Criteria:**
- Batch fetching reduces queries by 99%+
- Multiple algorithms supported
- All tests passing
- API documentation complete

---

### Phase 3: Clustering Service (Week 5-6) — COMPLETED

**Status:** Completed across Releases 3.3.0–3.5.0 (March 2026)

**Deliverables:**
1. ~~Enhanced `WCCClusteringService` class~~ DONE — refactored to pluggable backend architecture
2. ~~AQL graph traversal implementation~~ DONE — `AQLGraphBackend`
3. ~~Cluster validation and statistics~~ DONE
4. ~~Unit and integration tests~~ DONE
5. ~~API documentation~~ DONE
6. ~~GAE implementation~~ DONE in 3.5.0

**Tasks:**
- [x] Enhance existing `ClusteringService` or create new `WCCClusteringService`
- [x] Implement AQL graph traversal for connected components
- [x] Implement cluster storage with metadata
- [x] Add validation methods and statistics
- [x] Write comprehensive tests
- [x] Document usage patterns
- [x] Implement GAE backend with dual-mode connection layer (self-managed + AMP)

**Additional Scope Delivered (beyond original plan):**
- `PythonUnionFindBackend` — near-linear Union-Find with path compression
- `PythonSparseBackend` — scipy-backed WCC for large dense graphs
- `GAEWCCBackend` — full GAE engine lifecycle with result reading
- `gae_connection.py` — dual-mode connection abstraction
- `backend='auto'` heuristic selection (default since 3.5.0)
- Deprecation path for `use_bulk_fetch` and `wcc_algorithm`

---

### Phase 4: Integration & Documentation (Week 7-8) — COMPLETED

**Deliverables:**
1. Multi-strategy orchestration utilities
2. Complete API documentation
3. Migration guide from direct implementations
4. Usage examples
5. Performance comparison guide
6. Updated main library exports

**Tasks:**
- [x] Create orchestration utilities — `src/entity_resolution/core/orchestrator.py` (`MultiStrategyOrchestrator`)
- [x] Update `__init__.py` exports — all 7 enhancement classes exported from `entity_resolution` (orchestrator, blocking strategies, similarity/edge/clustering services)
- [x] Write comprehensive API docs — `docs/api/API_REFERENCE.md`
- [x] Create migration guide — `docs/guides/MIGRATION_GUIDE_V2.md`, `docs/guides/MIGRATION_GUIDE_V3.md`
- [x] Add usage examples — 13 examples under `examples/` (incl. `multi_strategy_orchestration.py`, `clustering_backend_comparison.py`, `onnx_runtime_embedding.py`, `vector_blocking_example.py`, `cross_collection_matching_examples.py`)
- [x] Update README — UI section, MCP tools inventory, GAE clustering, GPU/device support, LLM curation
- [x] Create performance comparison docs — `docs/guides/PERFORMANCE_GUIDE.md`
- [x] Version bump and changelog — released through 3.5.1 with detailed CHANGELOG entries
- [x] Add platform docs for Apple Silicon and Linux GPU setup — `docs/guides/PLATFORM_SETUP.md`
- [x] Add provider compatibility matrix (ORT/CoreML/CUDA/TensorRT) — `docs/guides/PROVIDER_MATRIX.md` and `docs/guides/PROVIDER_COMPATIBILITY_MATRIX.md`
- [x] Add rollout/rollback runbook for provider overrides — `docs/development/PROVIDER_ROLLOUT_RUNBOOK.md` (companion: `docs/development/RUNTIME_HEALTH_CI_RUNBOOK.md`)

**Status (as of 2026-04-28 audit):** All Phase 4 deliverables shipped. GPU provider promotion (CoreML/CUDA/TensorRT as default) remains future work pending parity and quality gates — see "Release Alignment" below.

**Success Criteria:**
- [x] All new classes properly exported
- [x] Documentation complete and clear
- [x] Migration path well-documented
- [x] Examples cover common use cases

---

## Testing Strategy

### Unit Tests

Each new class will have comprehensive unit tests covering:
- Happy path scenarios
- Edge cases (empty data, null values, etc.)
- Error handling
- Configuration variations
- Performance characteristics

### Integration Tests

Test complete workflows:
- End-to-end blocking -> similarity -> edges -> clustering
- Multiple strategies combined
- Large dataset scenarios
- Different ArangoDB configurations

### Performance Tests

Benchmark against requirements:
- Blocking: Handle 100K+ entities in <10 seconds
- Similarity: Compute 50K+ pairs in <20 seconds
- Edges: Create 10K+ edges/second
- Clustering: Process 100K+ entities in <30 seconds
- Embeddings (GraphML, ColBERT, BERT ONNX): measurable throughput/latency improvement vs CPU baseline on supported GPU platforms

### Compatibility Tests

Test across:
- ArangoDB versions (3.9, 3.10, 3.11)
- Python versions (3.8, 3.9, 3.10, 3.11)
- Different dataset sizes
- Different data quality scenarios
- Apple Silicon provider path (`coreml -> cpu`)
- Linux NVIDIA provider path (`cuda` and optional `tensorrt`)
- Provider fallback behavior when accelerators are unavailable

---

## Documentation Plan

### API Documentation

- Complete docstrings for all public methods
- Type hints for all parameters and returns
- Usage examples in docstrings
- Links to related classes/methods

### User Guide

- Overview of new capabilities
- When to use each strategy/service
- Configuration examples
- Performance tuning guide
- Troubleshooting common issues

### Migration Guide

- How to migrate from direct implementations
- Before/after code examples
- Performance comparison
- Breaking changes (if any)
- Deprecation timeline

### Examples

- Basic blocking example
- Multi-strategy blocking
- Batch similarity computation
- Complete ER pipeline
- Performance optimization examples

---

## Backward Compatibility

### Approach

- New classes don't modify existing APIs
- Existing `BlockingService`, `SimilarityService`, `ClusteringService` remain unchanged
- New classes augment, don't replace
- Optional migration path for existing users

### Deprecation Plan (if needed)

If any existing APIs need changes:
1. Mark as deprecated in v2.0
2. Maintain for 2 major versions
3. Provide clear migration path
4. Show warnings when used
5. Remove in v4.0

---

## Performance Requirements

### Blocking

- **Input:** 100K-500K entities
- **Output:** 50K-200K candidate pairs
- **Time:** <10 seconds per strategy
- **Memory:** <500MB peak

### Similarity

- **Input:** 50K-100K candidate pairs
- **Output:** 5K-20K matches above threshold
- **Time:** <20 seconds
- **Memory:** <1GB peak

### Edge Creation

- **Input:** 10K-50K matches
- **Output:** Edges in database
- **Time:** <5 seconds
- **Memory:** <100MB peak

### Clustering

- **Input:** 10K-50K edges, 20K-100K vertices
- **Output:** 1K-10K clusters
- **Time:** <30 seconds
- **Memory:** <500MB peak

---

## Success Metrics

### Code Quality

- [ ] 90%+ test coverage for new code
- [ ] All linter checks passing
- [ ] Type hints on all public APIs
- [ ] No breaking changes to existing APIs

### Performance

- [ ] Meet or exceed performance requirements
- [ ] Performance comparable to direct implementations
- [ ] Memory usage within acceptable limits

### Usability

- [ ] Clear, concise API design
- [ ] Comprehensive documentation
- [ ] Working examples for all major features
- [ ] Easy migration path from direct implementations

### Adoption

- [ ] Successfully refactor reference project (private)
- [ ] At least 2 example use cases documented
- [ ] Positive feedback from early users

---

## Risk Mitigation

### Risk: Performance degradation

**Mitigation:**
- Benchmark early and often
- Profile bottlenecks
- Keep proven implementations as reference
- Allow direct query override if needed
- Require embedding quality and retrieval-stability gates before promoting GPU defaults

### Risk: API too complex

**Mitigation:**
- Design API iteratively
- Get feedback from potential users
- Provide sensible defaults
- Include usage examples

### Risk: Breaking changes

**Mitigation:**
- Don't modify existing APIs
- Add new classes alongside old
- Provide migration guide
- Version appropriately
- Keep CPU as default until provider parity/quality/perf gates pass
- Keep per-model provider feature flags and a global CPU force switch

### Risk: Limited adoption

**Mitigation:**
- Solve real problems from production use
- Document benefits clearly
- Provide migration assistance
- Show performance comparisons

---

## Timeline Summary

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| Phase 0: GPU Foundation (parallel) | 2 weeks | ONNX runtime/provider abstraction, fallback and benchmark harness |
| Phase 1: Core Blocking | 2 weeks | CollectBlockingStrategy, BM25BlockingStrategy |
| Phase 2: Similarity & Edges | 2 weeks | BatchSimilarityService, SimilarityEdgeService |
| Phase 3: Clustering | 2 weeks | WCCClusteringService with multiple algorithms |
| Phase 4: Integration & Docs | 2 weeks | Complete documentation and examples |
| **Total** | **8-10 weeks** | Production-ready enhanced library with cross-platform GPU embedding support |

---

## Release Alignment

This plan aligned to the release sequence in `docs/development/NEXT_RELEASE_IMPLEMENTATION_BRIEF.md`.

**All three releases have been shipped:**

- `3.3.0` (shipped): Introduced runtime/provider abstraction and ONNX opt-in path; kept CPU default. Clustering backend abstraction with Union-Find. LLM provider configuration.
- `3.4.0` (shipped): Promoted `device='auto'` and `backend='python_union_find'` as defaults. Added sparse backend and auto-selection. LLM health checks.
- `3.5.0` (shipped): GAE clustering backend with dual-mode connection layer. `backend='auto'` as default.

GPU provider promotion (CoreML, CUDA, TensorRT) remains future work pending parity and quality gates.

---

## Next Steps

This plan is complete (all phases shipped through 3.5.1). Forward-looking work that grew out of this plan but is intentionally **out of scope** here:

1. **GPU provider promotion** — promote CoreML / CUDA / TensorRT from opt-in to default once parity and quality gates are met. Tracked via `docs/development/PROVIDER_ROLLOUT_RUNBOOK.md`.
2. **MCP API maintainability migration** — see `docs/development/MAINTAINABILITY_API_MIGRATION_PLAN.md` for the canonical `options`-based request shape proposal.
3. **UI Phase 4** — auth/RBAC, dark mode, responsive layout, tenant management. See `docs/architecture/ENTITY_RESOLUTION_UI.md` Phase 4 section.

---

## Notes

- All implementations must remain generic (no hardcoded collection/field names)
- Performance is critical - benchmark against production requirements
- Documentation is as important as code
- Test with real-world data scenarios
- Get early feedback from potential users

---

**Document Version:** 1.2 
**Last Updated:** March 16, 2026 
**Next Review:** Post-3.5.0 roadmap planning

