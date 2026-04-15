# Changelog

All notable changes to the arango-entity-resolution library will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Web UI** (`[ui]` optional extra) — optional browser-based interface for entity resolution
  workflows, launched with `arango-er ui`. Includes Review Queue (human-in-the-loop match
  review with keyboard shortcuts), Cluster Browser (paginated list with interactive React Flow
  graph visualization), Pipeline Runner (WebSocket-driven live progress), Config Builder
  (visual pipeline configuration with advisor tool integration), Entity Resolver (interactive
  single-record resolution), Golden Record Manager (field-level provenance and conflict
  resolution), and Export Center. Backend is FastAPI wrapping existing services — no new
  resolution logic. Install with `pip install "arango-entity-resolution[ui]"`.
- **`FeedbackStore.query_verdicts()`** — paginated, filterable AQL queries over the feedback
  collection with bind-variable safety.
- **`FeedbackStore.count_by_status()`** — grouped verdict counts by decision.
- **`FeedbackStore.pending_review_count()`** — count of LLM verdicts awaiting human review.
- **`ConfigurableERPipeline.run(on_progress=...)`** — optional callback parameter for
  stage-by-stage progress reporting during pipeline execution.

## [3.5.1] - 2026-03-30

### Security
- **AQL injection hardening** — converted ~30 f-string collection name interpolations
  across 13 service files to `@@collection` AQL bind variables. Collection names are now
  never placed directly into query strings.
- **MCP SSE default bind** changed from `0.0.0.0` to `127.0.0.1` — prevents unintentional
  network exposure when running the MCP server without explicit `--host`.
- **Silent exception logging** — 12 `except Exception: pass` blocks across services, MCP,
  ETL, and utils now log with `logger.debug` (or `logger.warning` for data-loss-risk paths
  like `batch_similarity_service` document fetches).

### Added
- **`MultiStrategyOrchestrator`** — run multiple blocking strategies with union/intersection
  modes and configurable field weights.
- **`AddressERPipeline`** — first-class pipeline for address entity resolution with
  built-in normalization and geocoding support.
- **`GraphRAGLinker` / `DocumentEntityExtractor`** — LLM-powered document entity extraction
  and graph-based record linking via litellm.
- **`GeospatialValidator` / `TemporalValidator`** — coordinate distance and date-range
  validation for candidate pairs.
- **`ShardParallelBlockingStrategy`** — blocking strategy optimised for sharded ArangoDB
  clusters with parallel shard queries.
- **`OnnxModelExporter`** — export sentence-transformers models to ONNX format with
  validation and metadata.
- **ONNX Runtime embedding backend** — `OnnxRuntimeEmbeddingBackend` for faster CPU
  inference via onnxruntime; includes encode, normalize, and batch support.
- **New CLI commands** — additional pipeline and export commands in `arango-er`.
- **`Makefile`** with 14 standard development targets (install, test, lint, format,
  typecheck, build, clean, docker-up/down/test).
- **`docs/guides/ADVANCED_MODULES_GUIDE.md`** — comprehensive documentation for 12
  previously undocumented modules (orchestrator, address pipeline, GraphRAG, geospatial,
  shard-parallel, incremental resolver, feedback, ETL normalizers).
- 3 new guides: `PERFORMANCE_GUIDE.md`, `PLATFORM_SETUP.md`, `PROVIDER_MATRIX.md`.
- **`PROVIDER_COMPATIBILITY_MATRIX.md`** — detailed ONNX Runtime provider compatibility
  matrix covering CPU, CoreML, CUDA, and TensorRT with fallback chains, model compatibility,
  and quick-reference tables.
- **`PROVIDER_ROLLOUT_RUNBOOK.md`** — operational runbook for rolling out, monitoring,
  and rolling back ONNX Runtime provider changes with pre-rollout checklists, CI gate
  commands, alert conditions, and incident response procedures.
- **Address pipeline shard-parallel blocking** — `blocking_mode='shard_parallel'` enumerates
  distinct shard-key prefix values and runs one blocking query per prefix for single-shard
  query routing on sharded ArangoDB clusters.
- **Address pipeline `edge_loading_method='auto'`** — automatically selects CSV/arangoimport
  for large edge sets (>100K) when `arangoimport` is on PATH, with fallback to API batching.
  Warns when explicit `api` mode is used with large datasets.
- **Block skip tracking** — `blocks_skipped_max_size`, `largest_skipped_block_size`, and
  `skipped_block_samples` now appear in address pipeline results for registered-agent auditing.
- **`arangoimport` availability check** at `AddressERService` init via `shutil.which`.
- 3 new examples: `onnx_runtime_embedding.py`, `yaml_config_pipeline.py`,
  `incremental_resolution.py`.

### Changed
- **`__init__.py` lazy loading** refactored from a 150-line `if/elif` `__getattr__` chain
  to a compact `_LAZY_IMPORTS` registry dict with `importlib`-based resolution and
  `globals()` caching.
- **Pipeline methods promoted to public API** — `run_blocking()`, `run_similarity()`,
  `run_clustering()`, `run_edge_creation()`, `batch_fetch_documents()`,
  `check_embeddings_exist()` are now public on their respective classes. All `# noqa: SLF001`
  suppressions eliminated.
- **`AdaptiveLLMVerifier.verifier`** attribute is now public (was `_verifier`).
- **`DatabaseManager`** singleton is now thread-safe via `threading.Lock` with
  double-checked locking on instance creation, client init, database cache, and cleanup.
- **Hardcoded defaults consolidated** — `localhost`, `8529`, `root`, `_system` are now
  defined once in `utils/constants.py` (`DEFAULT_HOST`, `DEFAULT_PORT`, `DEFAULT_USERNAME`,
  `DEFAULT_DATABASE`) and imported everywhere.

### Removed
- **`utils/archive_unused/`** directory deleted (322 lines) — contained `enhanced_config.py`
  (which wrote plaintext passwords to disk) and `enhanced_logging.py`.
- **Deprecated `ArangoBaseConnection`** class and **`get_default_connection_args()`** function
  removed from `utils/database.py`.
- Commented-out `_default_logger` singleton code removed from `utils/logging.py`.
- Dead `if name == '_system': pass` branch removed from `utils/validation.py`.

### Fixed
- **Always-passing test assertion** in `test_onnx_encode_and_export.py` — removed `or True`
  that made the norm check meaningless; tightened empty-array assertion.
- **6 broken links** in `README.md` corrected to actual file paths; empty stub section removed.
- Misplaced test files moved from `examples/` to `tests/` (4 files).
- `enhanced_er_examples.py` updated from stale "v2.0" branding; `main()` now runs at least
  one example.
- `complete_entity_resolution_demo.py` given deprecation header for its pre-v3.0 API usage;
  `sys.path.insert` hack removed.

### Testing
- **117 new unit tests** across 4 new test files:
  - `test_validation.py` (52 tests) — all public validation functions
  - `test_feedback.py` (17 tests) — FeedbackStore and ThresholdOptimizer
  - `test_geographic_blocking.py` (20 tests) — GeographicBlockingStrategy
  - `test_hybrid_blocking.py` (28 tests) — HybridBlockingStrategy
- 6 new test files for new modules: `test_address_pipeline.py`, `test_graph_rag.py`,
  `test_geospatial_validator.py`, `test_orchestrator.py`, `test_shard_parallel_blocking.py`,
  `test_onnx_encode_and_export.py`.
- All existing tests updated for method renames and AQL bind variable changes.
- **1,184 tests passing**, 7 skipped (3 GAE enterprise, 4 legacy scripts).

## [3.5.0] - 2026-03-16

### Added — GAE Clustering Backend
- **`GAEWCCBackend`** — WCC clustering via ArangoDB Graph Analytics Engine (enterprise).
  Manages the full engine lifecycle: deployment, graph loading, WCC execution,
  result storage to vertex documents, and optional cleanup.
- **`gae_connection.py`** — Dual-mode connection layer supporting both self-managed
  (JWT auth via `/_open/auth`) and ArangoGraph Managed Platform (oasisctl bearer token)
  deployments. Factory function `get_gae_connection()` routes by `TEST_DEPLOYMENT_MODE`.
- **`GAEClusteringConfig`** — Configuration class for GAE-specific settings:
  `enabled`, `deployment_mode`, `graph_name`, `engine_size`, `auto_cleanup`, `timeout_seconds`.
- Engine readiness polling with consecutive-OK probes for Kubernetes pod spin-up.
- GAE job polling (`loaddata`, `wcc`, `storeresults`) with configurable timeouts.
- Result reading from vertex document attributes with key mapping via AQL.

### Changed
- `ClusteringConfig.backend` default changed from `'python_union_find'` to `'auto'`.
- `ClusteringConfig.VALID_BACKENDS` now includes `'gae_wcc'`.
- `WCCClusteringService._auto_select_backend()` prioritizes GAE when `gae_config.enabled=True`,
  GAE is available, and edge count exceeds threshold.
- `WCCClusteringService.get_statistics()` includes `gae_job_id` and `gae_runtime_seconds`
  when GAE backend is used.
- `configurable_pipeline.py` and `async_pipeline.py` now pass GAE configuration to
  `WCCClusteringService`.
- Deprecation warning for `wcc_algorithm` updated to "future release" timeline.

### Testing
- New unit tests (`test_gae_clustering.py`): 29 tests covering GAE config, backend,
  and auto-selection with GAE priority.
- New integration test skeleton (`test_gae_integration.py`) with `@requires_gae` skip
  marker for environments with GAE access.
- Live integration validated against self-managed GAE on `prod.demo.pilot.arango.ai`.

## [3.4.0] - 2026-03-15

### Changed — Promoted Defaults
- `EmbeddingConfig.device` default changed from `'cpu'` to `'auto'` — automatically
  selects CUDA, MPS (Apple Silicon), or CPU at runtime. MPS/CUDA parity confirmed in 3.3.0.
- `ClusteringConfig.backend` default changed from `'python_dfs'` to `'python_union_find'`.
  Parity with `python_dfs` output confirmed in 3.3.0.

### Added
- **`PythonSparseBackend`** — WCC via `scipy.sparse.csgraph.connected_components()`.
  Faster than Union-Find for very dense large graphs. Optional dependency (scipy).
- **`backend='auto'`** selection logic in `WCCClusteringService` — selects `python_sparse`
  above `auto_select_threshold_edges` (default 2M) when scipy is available, otherwise
  `python_union_find`.
- `ClusteringConfig` gains `auto_select_threshold_edges` and `sparse_backend_enabled` fields.
- `EmbeddingConfig.max_batch_size` cap for OOM safety on GPU workloads.
- `LLMMatchVerifier.healthcheck()` — validates provider reachability before pipeline runs.
- `LLMProviderConfig` gains `healthcheck_on_start` and `fallback_provider` fields.

### Testing
- New `test_auto_backend_selection.py` covering auto selection, sparse parity, and
  scipy-unavailable fallback.
- Updated existing tests for new `'auto'` device and `'python_union_find'` backend defaults.

## [3.3.0] - 2026-03-14

### Added — Clustering Backend Abstraction
- **`clustering_backends/`** package with pluggable WCC backend architecture:
  - `ClusteringBackend` protocol (`base.py`)
  - `PythonDFSBackend` — extracted from existing bulk-fetch DFS logic
  - `PythonUnionFindBackend` — near-linear Union-Find with path compression and union by rank
  - `AQLGraphBackend` — extracted from existing AQL traversal logic
- `WCCClusteringService` refactored to dispatch to named backends via `backend=` parameter.
- `get_statistics()` now includes `backend_used` key.

### Added — Embedding Runtime Expansion
- `EmbeddingConfig` gains `runtime` field (`'pytorch'` in 3.3.0) and accepts
  `'mps'` and `'auto'` as valid `device` values.
- `EmbeddingService.resolve_device()` detects CUDA or MPS availability at runtime.
- `requested_device` and `resolved_device` added to embedding metadata.
- `batch_size` now explicitly configurable on `EmbeddingService`.

### Added — LLM Provider Configuration
- **`LLMProviderConfig`** — structured provider settings for Ollama, OpenRouter, OpenAI,
  and Anthropic. Translates to litellm model strings automatically.
- `ActiveLearningConfig` gains `llm: LLMProviderConfig` field;
  `effective_model_string()` prefers `llm` over bare `model` string.
- `LLMMatchVerifier` gains `base_url` and `timeout_seconds` for Ollama support.
- `LLMMatchVerifier.from_provider_config()` class method for structured construction.

### Added — Runtime Health Infrastructure
- ONNX Runtime backend scaffold with provider resolution and CPU fallback.
- Runtime telemetry, baseline registry, compare workflows, and CI gate commands:
  `arango-er runtime-health`, `runtime-health-export`, `runtime-health-baseline`,
  `runtime-health-compare`, `runtime-health-gate`.
- Startup policy controls (`permissive` / `strict`).

### Changed
- `ClusteringConfig` gains `backend` field; `wcc_algorithm` deprecated with warning.
- `WCCClusteringService(use_bulk_fetch=...)` deprecated with warning; maps to `backend=`.

### Testing
- New `test_clustering_backends.py` covering Union-Find, DFS parity, backend dispatch,
  deprecation warnings, and statistics.
- New `test_llm_provider_config.py` and embedding device resolution tests.

## [3.2.3] - 2026-03-08

### Fixed
- `SimilarityEdgeService` now supports SmartGraph-compliant deterministic edge keys via
  `deterministic_key_mode="smartgraph"` or `deterministic_key_mode="auto"` when the edge
  collection can be identified from graph metadata. Standard collections keep the legacy
  MD5-based deterministic key format.
- Added coverage for real SmartGraph metadata shapes returned by `python-arango` and
  validated the fix against a local Docker-based Enterprise ArangoDB SmartGraph,
  reproducing and then clearing `ERR 1466`.

## [3.2.2] - 2026-03-08

### Fixed
- `merge_entities` now produces a deterministic golden-record preview directly from the MCP path
  instead of calling an incompatible service constructor.
- Demo SSE startup now uses the supported FastMCP SSE transport path instead of constructing a
  separate `sse_app()` server manually.

### Documentation
- Added a release checklist for `3.2.2` that explicitly documents GitHub Release -> PyPI publish.
- Clarified SSE usage guidance: prefer `stdio` for Claude Desktop/local IDE integrations and use SSE
  for remote HTTP MCP-capable clients.

### Added
- Opt-in active learning configuration for `ERPipelineConfig`, including feedback storage,
  adaptive threshold refresh, and MCP `find_duplicates` parameters for uncertain-pair review.
- Cluster quality metadata for stored WCC clusters and MCP `get_clusters`, including edge count,
  similarity summaries, density, and a composite `quality_score`.
- Config-driven similarity field transformers for normalization-heavy fields such as phones,
  state names, street suffixes, and company suffixes in the configurable pipeline.
- New `arango-er` commands for `status`, `clusters`, `export`, and `benchmark`.
- JSON/CSV cluster export artifacts built from stored cluster docs and pipeline statistics.
- A supported exact-vs-BM25 blocking benchmark workflow built on `ABEvaluationHarness`.

## [3.2.0] - 2026-03-05

### Security
- **AQL injection prevention** across all blocking strategy filter conditions (`base_strategy.py`,
  `collect_blocking.py`, `graph_traversal_blocking.py`, `geographic_blocking.py`,
  `pipeline_utils.py`). Dynamic string values are now placed in AQL bind variables,
  never interpolated inline (C1 \u2014 pipeline_utils, C2 \u2014 strategies).

### Added \u2014 MCP Server
- New `entity_resolution.mcp` package exposing entity resolution as MCP tools and resources.
- **Entry point**: `arango-er-mcp` (stdio for Claude Desktop / Cursor; `--transport sse` for HTTP).
- **7 tools**: `list_collections`, `find_duplicates`, `pipeline_status`, `resolve_entity`,
  `explain_match`, `get_clusters`, `merge_entities`.
- **2 resources**: `arango://collections/{name}/summary`, `arango://clusters/{collection}/{key}`.
- New optional dependency group: `mcp = ["mcp>=1.0.0"]`.

### Added \u2014 Incremental Resolver
- `IncrementalResolver` (`src/entity_resolution/core/incremental_resolver.py`):
  find matches for a single new record without re-running the full batch pipeline.
  Uses prefix-based blocking to avoid full collection scans.

### Added \u2014 LLM Match Verification
- `LLMMatchVerifier` (`src/entity_resolution/reasoning/llm_verifier.py`):
  calls an LLM only for pairs in the uncertain score range (default 0.55\u20130.80).
  High/low-confidence pairs are fast-path (no LLM call).
  Supports OpenRouter, OpenAI, Anthropic, and local Ollama via `litellm`.
- New optional dependency group: `llm = ["litellm>=1.0.0"]`.

### Changed
- `BlockingConfig.parse_fields()` \u2014 single canonical field-parsing method replaces duplicated
  logic in `ERPipelineConfig` and `ConfigurableERPipeline` (H3).
- `arangosearch` blocking strategy now aliases `bm25` instead of silently returning empty
  results (H1).
- Configurable `DEFAULT_BLOCKING_RECORD_LIMIT` replaces hardcoded `limit=10000`; a
  `UserWarning` is now emitted when the limit is reached (H2).
- `count_inferred_edges` reduced from 3 to 2 AQL round-trips by combining count + average
  into a single `COLLECT AGGREGATE` query (M6).
- Python version requirement bumped from 3.8+ to 3.10+ (to match actual code usage).
- `__version__` restored to a static string in `constants.py` so hatchling's regex-based
  version scraping continues to work during builds.

### Fixed
- `validate_edge_quality` now counts distinct defective edges via a single OR-condition AQL
  query instead of double-counting (L1).
- Dead private methods `_simple_blocking_check` and `_simple_ngram_similarity` removed from
  `EntityResolutionPipeline` (H4).
- Unused `import requests` removed from `base_service.py` (M2).
- Duplicate flat DB connection constants removed from `constants.py` (M4).
- `self.logger` removed from `ERPipelineConfig` \u2014 config objects are plain data containers (M5).

### Testing
- `db_connection` fixture in `conftest.py` rewritten with 3-tier resolution:
  env vars \u2192 labelled container \u2192 auto-spin `arangodb:3.12`. Previously 17 integration
  tests were always skipped due to hardcoded credentials.
- **567 tests pass, 0 skipped** (was 549 passing, 17 skipped in 3.1.x).
- New test files: `test_mcp_tools.py` (8 tests), `test_llm_verifier.py` (10 tests).


### Security

- Harden AQL identifier validation across services/strategies to reduce injection risk.
- Redact `arangoimport` failure logging to avoid credential leakage.

### Testing

- Add Docker-backed integration tests for Node2Vec and expand unit test coverage across core modules.

## [3.1.1] - 2026-02-01

### Added - GoldenRecord persistence + resolvedTo edges

**Feature**: Persist golden records and source-to-golden relationships from clustering output.

**Component**: `GoldenRecordPersistenceService`

- Creates/updates GoldenRecord documents from cluster memberships
- Creates resolvedTo edges from source entities to GoldenRecord
- Deterministic/idempotent reruns via deterministic keys + overwrite modes

### Added - Deterministic Edge Keys

**Feature**: Idempotent edge creation across all deployment types

**Component**: `SimilarityEdgeService`

- Added `use_deterministic_keys` parameter (default: `True`)
- Generates MD5 hash of `_from + _to` as edge `_key`
- Order-independent: `(A, B)` and `(B, A)` generate same key
- Uses `overwriteMode='ignore'` to prevent duplicates
- Initial release note incorrectly claimed the same MD5-only key format worked for SmartGraph
  edge collections. That claim was corrected in a later release with SmartGraph-aware keys.

**Benefits**:
- Idempotent pipelines - safe to run multiple times
- No duplicate edges
- Backward compatible - can disable with `use_deterministic_keys=False`
- Verified against production code (dnb_er project pattern)

**Usage**:
```python
service = SimilarityEdgeService(
db=db,
edge_collection='similarTo',
use_deterministic_keys=True # Default
)

# Run multiple times - no duplicates created
service.create_edges(matches)
service.create_edges(matches) # Safe - same edges won't duplicate
```

**SmartGraph Support**:
- The original `3.1.1` implementation did not generate SmartGraph-compliant edge keys.
- SmartGraph-aware deterministic keys were added in a later release.

## [3.1.0] - 2026-01-08

**Version Identifier**: 3.1.0-stable

### Added - Entity Resolution Enrichments

**New Feature**: Specialized components for technical, hierarchical, and domain-specific entity resolution.

**New Components**:

1. **TypeCompatibilityFilter** (`src/entity_resolution/enrichments/type_constraints.py`)
- Pre-filters candidates using a compatibility matrix before similarity scoring.
- Prevents nonsensical matches between incompatible types.
- Supports strict and loose matching modes.

2. **HierarchicalContextResolver** (`src/entity_resolution/enrichments/context_resolver.py`)
- Blends base similarity with token overlap between parent context and candidate description.
- Resolves ambiguities in hierarchical data where parent context provides critical disambiguation.
- Configurable weight for context influence.

3. **AcronymExpansionHandler** (`src/entity_resolution/enrichments/acronym_handler.py`)
- Expands search terms using domain-specific abbreviation dictionaries.
- Critical for technical and medical domains with heavy abbreviation use.
- Supports case-sensitive and case-insensitive matching.

4. **RelationshipProvenanceSweeper** (`src/entity_resolution/enrichments/relationship_sweeper.py`)
- Remaps relationships after deduplication to canonical golden entities.
- Maintains full audit trail and provenance of original source relationships.
- Optional relationship deduplication during remapping.

### Improved - Library Infrastructure

- **Lazy Configuration Loading**: Modified logging utilities to support standalone module imports without requiring database credentials.
- **Anonymized Documentation**: Removed specific customer references and anonymized examples for public distribution.
- **Emoji Removal**: Standardized all documentation to plain text for professional distribution.

### Fixed

- **Logging**: Fixed segfaults and import-time dependencies in `entity_resolution.utils.logging`.
- **Pre-commit Hooks**: Updated to correctly handle `PYTHONPATH` during import verification.

---

## [3.0.0] - 2025-12-09

**Version Identifier**: 3.0.0-stable

This is the current production release including all major ER services extracted from customer projects. See [VERSION_HISTORY.md](VERSION_HISTORY.md) for complete version timeline.

### Added - Vector Search-Based Entity Resolution (Phase 2)

**New Feature:** Tier 3 (Vector Blocking) with Semantic Embeddings

Implements Phase 2 Tier 3 (vector blocking) using pre-trained sentence-transformers models
and vector similarity search. Enables semantic matching that goes beyond exact text
or fuzzy string matching.

**New Components:**

1. **EmbeddingService** (`src/entity_resolution/services/embedding_service.py`)
- Generate vector embeddings for database records
- Uses sentence-transformers with pre-trained models (see config/vector_search_setup.md for model comparison)
- Batch processing for efficiency (1000+ records/batch)
- Automatic embedding storage in ArangoDB documents
- Coverage tracking and statistics

2. **VectorBlockingStrategy** (`src/entity_resolution/strategies/vector_blocking.py`)
- Tier 3 (vector blocking) for semantic similarity-based candidate generation
- Cosine similarity with configurable threshold
- Optional geographic/categorical blocking constraints
- Similarity distribution analysis for threshold tuning
- Compatible with existing blocking strategies

**Key Features:**
- Finds fuzzy matches that exact and text-based blocking miss
- Handles typos, abbreviations, and semantic variations
- Configurable similarity threshold (default: see DEFAULT_SIMILARITY_THRESHOLD in source)
- Limit candidates per entity to prevent explosion
- Combines with Tier 1 (exact) and Tier 2 (fuzzy text) blocking
- Performance: ~100-500 docs/second embedding generation (CPU)

**Configuration:**
```yaml
blocking:
strategy: "vector"
vector:
embedding_model: "all-MiniLM-L6-v2"
similarity_threshold: 0.7
limit_per_entity: 20
text_fields: ["name", "company", "address"]
```

**Usage Example:**
```python
from entity_resolution.services import EmbeddingService
from entity_resolution.strategies import VectorBlockingStrategy

# Step 1: Generate embeddings
embedding_service = EmbeddingService()
embedding_service.ensure_embeddings_exist(
'customers', 
text_fields=['name', 'company', 'address']
)

# Step 2: Find similar pairs
strategy = VectorBlockingStrategy(
db=db,
collection='customers',
similarity_threshold=0.7
)
pairs = strategy.generate_candidates()
```

**Testing:**
- 300+ unit tests for EmbeddingService
- 400+ integration tests for VectorBlockingStrategy
- End-to-end example with sample data
- Performance baselines established

**Documentation:**
- Configuration guide: `config/vector_search_setup.md`
- API reference updated
- Complete example: `examples/vector_blocking_example.py`
- Research notes: `research/papers/embeddings/`

**Dependencies:**
- Added `sentence-transformers>=2.2.0`
- Added `torch>=2.0.0`

**Based on Research:**
- Ebraheem et al. (2018): "Distributed Representations of Tuples for Entity Resolution"
- See: `research/papers/embeddings/2018_Ebraheem_DistributedEntityMatching_notes.md`

**Documentation:**
- API Reference: `docs/api/API_REFERENCE.md#embedding-service`
- Configuration Guide: `config/vector_search_setup.md`
- Working Example: `examples/vector_blocking_example.py`
- Code Quality Review: `docs/development/vector-search-code-quality-review.md`

### Fixed - CRITICAL: WCC Performance Issue (100x Speedup)

**Issue:** N+1 Query Anti-Pattern 
**Impact:** 100x performance degradation on production datasets 
**Severity:** HIGH - Made WCC unusable on real data

**Problem:**
- Old implementation: 24,256 separate queries for a 24K vertex graph
- Time: 300+ seconds (5+ minutes), often timeout
- Root cause: Per-vertex AQL traversal in a loop

**Solution:**
- New implementation: 1 bulk query + Python DFS
- Time: 3-8 seconds for same graph
- **Improvement: 40-100x faster** 

**Changes:**
- Added `_find_connected_components_bulk()` method
- Fetches ALL edges in ONE query
- Builds graph in Python memory (fast, no network calls)
- Runs DFS in Python (no database round-trips)

- Added `use_bulk_fetch` parameter (default: `True`)
- `True`: Use bulk fetch + Python DFS (FAST, recommended)
- `False`: Use per-vertex AQL traversal (SLOW, only for >10M edges)

- Backward compatible
- Existing code works without changes
- Default behavior is now 40-100x faster
- Old AQL approach still available if needed

**Performance:**
- Small graphs (100 edges): 4-5x faster
- Medium graphs (16K edges): 30-40x faster
- Large graphs (1M edges): 50-100x faster
- Memory: ~3-5 MB per 16K edges (negligible for ER use cases)

**Testing:**
- 5/5 performance tests passing
- Small, medium, large graphs tested
- Both approaches produce identical results
- Default behavior verified
- Empty graph edge case handled

**Migration:**
```python
# Before (implicit, slow):
service = WCCClusteringService(db, edge_collection='similarTo')

# After (explicit, fast - but default anyway):
service = WCCClusteringService(db, edge_collection='similarTo', use_bulk_fetch=True)

# Or keep slow approach for huge graphs:
service = WCCClusteringService(db, edge_collection='similarTo', use_bulk_fetch=False)
```

**Identified by:** dnb_er customer project 
**Test coverage:** `test_wcc_performance.py` (5/5 passing)

### Added
- **New Utility Modules** - Generic ER utilities ported from production implementations
- **`view_utils`**: ArangoSearch view analyzer verification and self-healing
- `resolve_analyzer_name()`: Automatically detects database-prefixed analyzer names
- `verify_view_analyzers()`: Tests view accessibility and detects analyzer issues
- `fix_view_analyzer_names()`: Recreates views with correct analyzer names
- `verify_and_fix_view_analyzers()`: Combined verification and auto-fix
- Prevents common deployment failures from analyzer name mismatches
- **`pipeline_utils`**: ER pipeline state management
- `clean_er_results()`: Removes previous ER results from collections
- Gracefully handles missing collections and errors
- Configurable collection list with sensible defaults
- **`config_utils`**: Configuration and environment utilities
- `verify_arango_environment()`: Validates required ArangoDB environment variables
- `get_arango_config_from_env()`: Loads ArangoDB config from environment
- Provides user-friendly error messages for missing configuration
- **`validation_utils`**: ER result validation
- `validate_er_results()`: Compares expected vs actual document counts
- Detects data consistency issues early
- Configurable validation rules with sensible defaults
- All utilities are exported from `entity_resolution.utils` for easy access
- Comprehensive test coverage (38 new test cases)
- See `docs/development/LIBRARY_PORT_ANALYSIS.md` for details

- **AddressERService** - Dual edge loading methods for optimal performance
- **Optimized API method**: Cross-block batching reduces API calls by 100x (285K -> ~400 calls)
- 3-4x faster than original per-block approach
- Configurable batch size via `edge_batch_size` (default: 1000)
- Good for datasets with <100K edges
- **CSV + arangoimport method**: 10-20x faster for large datasets (>100K edges)
- Exports edges to CSV and uses ArangoDB's native bulk import tool
- Single import operation vs thousands of API calls
- Automatic fallback to API method if arangoimport unavailable
- Configurable via `edge_loading_method='csv'` in config
- **Method selection**: Choose 'api' (default) or 'csv' via configuration
- **Progress logging**: Both methods log progress every 100K edges
- See `docs/development/EDGE_BULK_LOADING_ANALYSIS.md` for details

### Fixed
- **AddressERService** - Fixed analyzer name resolution for database-prefixed analyzers
- Added `_resolve_analyzer_name()` method to detect and use database-prefixed analyzer names (e.g., `database_name::analyzer_name`)
- `_setup_search_view()` now automatically detects and uses the correct analyzer names whether they're prefixed or not
- Fixes address matching issues when analyzers are stored with database prefixes in ArangoDB
- Backward compatible: works with both prefixed and non-prefixed analyzer names
- Includes fallback logic for built-in analyzers like `text_en` and `identity`

## [3.0.0] - 2025-11-17

### Added - General-Purpose ER Components

#### Core Similarity Component
- **`WeightedFieldSimilarity`** - Standalone reusable similarity computation
- Multiple algorithms (Jaro-Winkler, Levenshtein, Jaccard)
- Configurable field weights and null handling
- String normalization options
- Can be used independently or with batch services

#### Enhanced Clustering
- **`WCCClusteringService`** - Now supports multiple algorithms:
- **Python DFS** - Reliable across all ArangoDB versions, uses bulk edge fetching
- **AQL Graph** (default) - Server-side processing for large graphs
- Eliminates N+1 query problems with single bulk edge fetch

#### Address Entity Resolution
- **`AddressERService`** - Complete address deduplication pipeline
- Custom analyzer setup for address normalization
- ArangoSearch view configuration
- Blocking with registered agent handling
- Edge creation and optional clustering
- Configurable field mapping (works with any address schema)

#### Configuration-Driven ER
- **`ERPipelineConfig`** - YAML/JSON-based ER pipeline configuration
- **`ConfigurableERPipeline`** - Run complete ER pipelines from configuration files
- Automatic service instantiation
- Validation and error handling
- Standardized ER patterns

### Fixed
- **WCC Clustering Service** - Added missing `WITH` clause in AQL graph traversal queries
- Fixes "collection not known to traversal" error (ArangoDB Error 1521)
- Auto-detects vertex collections from edge `_from` and `_to` fields
- Supports both explicit and auto-detected vertex collections
- Handles multi-collection graphs correctly
- **AddressERService** - Fixed logger.success() calls (replaced with logger.info())
- **Security** - Added field name validation to prevent AQL injection
- **Test Coverage** - Added comprehensive tests for ConfigurableERPipeline, graph_utils, config, and database modules

### Changed
- **BatchSimilarityService** - Now uses WeightedFieldSimilarity internally for consistency
- **Default Constants** - Centralized in constants.py for consistency

## [2.0.0] - 2025-11-12

### Added - Enhanced Entity Resolution Components

#### New Blocking Strategies
- **`CollectBlockingStrategy`** - COLLECT-based composite key blocking
- Efficient O(n) complexity without cartesian products
- Supports multi-field blocking (phone+state, address+zip, etc.)
- Configurable filters per field
- Block size limits to prevent explosion
- **Computed fields support** - Derive blocking keys from existing fields using AQL expressions
- Extract ZIP5 from POSTAL_CODE: `LEFT(d.postal_code, 5)`
- Normalize phone numbers: `REGEX_REPLACE(d.phone, '[^0-9]', '')`
- Combine fields: `CONCAT(d.field1, '_', d.field2)`
- Filter on computed fields
- No validation conflicts with non-standard field names

- **`BM25BlockingStrategy`** - Fast fuzzy text matching
- Uses ArangoSearch BM25 scoring
- 400x faster than Levenshtein for initial filtering
- Configurable BM25 thresholds
- Limit results per entity
- Optional blocking field constraints

#### New Similarity Service
- **`BatchSimilarityService`** - Optimized similarity computation
- Batch document fetching (reduces queries from 100K+ to ~10-15)
- Multiple algorithms: Jaro-Winkler, Levenshtein, Jaccard, custom
- Configurable field weights
- Field normalization options (case, whitespace, etc.)
- Progress callbacks for long operations
- Performance: ~100K+ pairs/second for Jaro-Winkler
- Detailed per-field similarity scores available

#### New Edge Service
- **`SimilarityEdgeService`** - Bulk edge creation
- Batch insertion with configurable batch sizes
- Automatic _from/_to formatting
- Comprehensive metadata tracking
- Bidirectional edge support
- Cleanup operations for iterative workflows
- Performance: ~10K+ edges/second

#### New Clustering Service
- **`WCCClusteringService`** - Weakly Connected Components clustering
- Server-side AQL graph traversal (efficient, works on all ArangoDB 3.11+)
- Handles graphs with millions of edges
- Cluster validation methods
- Comprehensive statistics tracking
- Configurable minimum cluster size
- Automatic cluster storage
- Future: GAE enhancement path documented

### Enhanced

#### Base Classes
- **`BlockingStrategy`** - Abstract base class for all blocking strategies
- Consistent API across all blocking methods
- Built-in filter condition builders
- Pair normalization and deduplication
- Statistics tracking
- Progress reporting

#### Library Exports
- All new classes properly exported from `entity_resolution` module
- Organized imports by category (strategies, services)
- Backward compatible with existing imports

### Documentation

#### New Documentation
- **Migration Guide** (`docs/MIGRATION_GUIDE_V2.md`) - Step-by-step guide to refactor from direct implementations
- **Usage Examples** (`examples/enhanced_er_examples.py`) - 8 complete examples demonstrating all new features
- **GAE Enhancement Path** (`docs/GAE_ENHANCEMENT_PATH.md`) - Future enhancement documentation for very large graphs
- **Enhancement Plan** (`docs/LIBRARY_ENHANCEMENT_PLAN.md`) - Detailed technical specifications
- **Design Rationale** (`DESIGN_SIMPLIFICATION.md`) - Explains design decisions (AQL vs Python DFS)

#### Updated Documentation
- **README** - Added v2.0 features section at the top
- **Examples** - Comprehensive examples showing generic patterns

### Testing

#### Unit Tests
- `test_blocking_strategies.py` - Complete unit tests for blocking strategies
- `test_similarity_and_edge_services.py` - Unit tests for similarity and edge services
- `test_wcc_clustering_service.py` - Unit tests for clustering service

#### Integration Tests
- `test_integration_and_performance.py` - End-to-end integration tests with real ArangoDB
- Performance benchmarks for all components
- Complete pipeline testing

### Performance Improvements

- **Blocking**: O(n) complexity vs O(n^2) for composite keys
- **Similarity**: Batch fetching reduces network overhead by 99%+
- **Clustering**: Server-side AQL processing vs client-side Python
- **Overall**: ~87% code reduction for projects using these features

### Breaking Changes

**None** - Version 2.0 is fully backward compatible. All existing APIs remain unchanged.
New features are additive and don't modify existing functionality.

### Dependencies

- Existing: `jellyfish` and `python-Levenshtein` already in requirements.txt
- No new dependencies added

### Migration

Projects can migrate incrementally:
1. Existing code continues to work without changes
2. New features can be adopted component by component
3. See [Migration Guide](docs/guides/MIGRATION_GUIDE_V3.md) for detailed instructions

### Technical Details

#### Design Principles
- **Generic & Reusable**: No hardcoded collection or field names
- **Configuration-Driven**: All behavior controlled through parameters
- **Performance-Optimized**: Proven patterns from production use
- **Well-Documented**: Comprehensive API docs and examples

#### Quality Metrics
- Zero linter errors
- 100% type hints on public APIs
- 100% docstring coverage on public methods
- Comprehensive unit and integration tests

#### Supported Versions
- ArangoDB: 3.11+, 3.12+
- Python: 3.8+, 3.9+, 3.10+, 3.11+

---

## [1.x.x] - Previous Versions

See git history for previous version changes. Version 2.0 represents a major
enhancement adding production-grade entity resolution components while maintaining
full backward compatibility with version 1.x.

---

## Future Enhancements

### Planned Features
- ONNX Runtime GPU acceleration (CoreML on Apple Silicon, CUDA/TensorRT on Linux)
- End-to-end integration test suite with real ArangoDB in CI
- MCP server endpoint lifecycle tests
- Replace `fuzzywuzzy` dependency with `thefuzz`
- `py.typed` marker for downstream mypy consumers

### Shipped (see 3.5.1)
- ~~ONNX Runtime embedding backend~~ (3.5.1)
- ~~GraphRAG and document entity extraction~~ (3.5.1)
- ~~Geospatial-temporal validation~~ (3.5.1)
- ~~Shard-parallel address blocking for ArangoDB clusters~~ (3.5.1)
- ~~`AddressERPipeline` first-class library class~~ (3.5.1)

### How to Contribute
See CONTRIBUTING.md (if available) or open issues/PRs on the project repository.

---

**Document Version:** 2.1 
**Date:** March 30, 2026 
**Library Version:** 3.5.1
