# ArangoDB Entity Resolution

A production-ready entity resolution system for ArangoDB that identifies and links records referring to the same real-world entity across multiple data sources. Uses record blocking, graph algorithms, and AI to scale from thousands to millions of records.

**Version 3.5.1** | [Changelog](CHANGELOG.md) | [Version History](VERSION_HISTORY.md) | [PyPI](https://pypi.org/project/arango-entity-resolution/)

## Installation

```bash
pip install arango-entity-resolution

# With optional features
pip install "arango-entity-resolution[mcp]"       # MCP server for AI agents
pip install "arango-entity-resolution[llm]"       # LLM match verification
pip install "arango-entity-resolution[ml]"        # Vector embeddings (sentence-transformers)
pip install "arango-entity-resolution[mcp,llm,ml]"  # Everything
```

## Quick Start

### CLI

```bash
# Run a pipeline from YAML config
arango-er run --config config/er_config.example.yaml

# Inspect clusters
arango-er status --collection companies
arango-er clusters --collection companies --limit 20

# Export results
arango-er export --collection companies --output-dir ./exports
```

### Python

```python
from entity_resolution import ConfigurableERPipeline, ERPipelineConfig

config = ERPipelineConfig.from_yaml("config/er_config.example.yaml")
pipeline = ConfigurableERPipeline(config=config, db=db)
results = pipeline.run()

print(f"Candidates: {results['blocking']['candidates_found']}")
print(f"Clusters:   {results['clustering']['clusters_found']}")
```

### MCP Server (AI Agent Integration)

```bash
# stdio for Claude Desktop / Cursor
arango-er-mcp

# SSE for remote clients
arango-er-mcp --transport sse --port 8080
```

Exposes 15 tools and 2 resources for any MCP-compatible AI agent. See [MCP Tools](#mcp-tools) below for the full inventory.

## How It Works

Entity resolution runs as a multi-stage pipeline, each stage narrowing candidates and increasing precision:

```
Data Sources → Blocking → Similarity → Clustering → Golden Records
                 ↓            ↓            ↓
              99%+ pair    Field-level   Graph-based
              reduction    scoring       grouping
```

**Stage 1 — Record Blocking** reduces O(n²) comparisons to O(n) using ArangoSearch full-text indexes, phonetic matching, n-gram overlap, vector similarity, and geographic proximity.

**Stage 2 — Similarity Scoring** computes field-level similarity (Jaro-Winkler, Levenshtein, Jaccard) with configurable weights and a Fellegi-Sunter probabilistic framework.

**Stage 3 — Clustering** groups matched pairs into entity clusters using Weakly Connected Components with pluggable backends (Union-Find, DFS, scipy sparse, AQL graph, or GAE enterprise).

**Stage 4 — Golden Record Generation** fuses cluster members into authoritative master records with source ranking, conflict resolution, and full audit trail.

Optional AI stages can be inserted into the pipeline:

- **LLM Match Verification** — auto-calls an LLM for ambiguous pairs in the 0.55–0.80 confidence range
- **GraphRAG Entity Extraction** — extracts entities from unstructured documents and links them to the graph
- **Geospatial-Temporal Validation** — confirms or rejects matches based on location and time feasibility

## Key Features

### Blocking Strategies
| Strategy | Use Case |
|----------|----------|
| **Exact / COLLECT** | High-precision blocking on email, phone, composite keys |
| **BM25 / ArangoSearch** | Fuzzy text matching (400x faster than Levenshtein) |
| **Vector / ANN** | Semantic similarity via sentence-transformers embeddings; **requires** ArangoDB 3.12+ with a native `APPROX_NEAR_COSINE` vector index (no brute-force fallback) |
| **Geographic** | Proximity-based blocking with coordinate distance |
| **LSH** | Locality-sensitive hashing for high-dimensional data |
| **Graph Traversal** | Shared-identifier network analysis |
| **Shard-Parallel** | Optimised for sharded ArangoDB clusters |

### Clustering Backends

The default `backend: auto` selects the best available backend based on edge count, optional dependencies, and whether the ArangoDB Graph Analytics Engine is reachable:

| Backend | Best For | Selection |
|---------|----------|-----------|
| `python_union_find` | General purpose | Default when GAE is unavailable |
| `python_dfs` | Reliable DFS traversal | Explicit only |
| `python_sparse` | Very large dense graphs | Auto-selected above 2M edges when scipy installed |
| `aql_graph` | Server-side processing | Explicit only |
| `gae_wcc` | Enterprise-scale (millions of edges) | Auto-selected when GAE is enabled and reachable |

#### GAE Clustering (Enterprise)

For graphs too large for in-process clustering, the `gae_wcc` backend offloads WCC to the [ArangoDB Graph Analytics Engine](https://docs.arangodb.com/stable/data-science/graph-analytics-engine/) — a dedicated compute cluster. The backend manages the full lifecycle: engine deployment, graph loading, WCC execution, result storage, and cleanup.

```yaml
clustering:
  backend: auto
  gae:
    enabled: true
    deployment_mode: self_managed   # or "amp" for ArangoGraph Managed Platform
    graph_name: companies_similarity_graph
    engine_size: e16
    auto_cleanup: true
    timeout_seconds: 3600
```

Supports both self-managed deployments (JWT auth) and ArangoGraph Managed Platform (oasisctl bearer token).

### Embedding & GPU Support

Embedding generation for vector blocking auto-detects the best available hardware:

| Device | Platform | How to use |
|--------|----------|------------|
| **CUDA** | Linux / Windows with NVIDIA GPU | `device: auto` (auto-detected) or `device: cuda` |
| **MPS** | macOS with Apple Silicon | `device: auto` (auto-detected) or `device: mps` |
| **CPU** | Any platform | `device: cpu` (fallback) |

```yaml
embedding:
  model: all-MiniLM-L6-v2
  device: auto              # selects CUDA > MPS > CPU at runtime
  max_batch_size: 256       # OOM safety cap for GPU workloads
  runtime: pytorch          # or onnx for faster CPU inference
```

The ONNX Runtime backend (`pip install "arango-entity-resolution[onnx]"`) provides faster CPU inference and supports export from any sentence-transformers model via `OnnxModelExporter`.

### LLM Match Curation

When similarity scoring produces ambiguous pairs (default 0.55–0.80 confidence), the pipeline can auto-delegate them to an LLM for a match/no-match decision. This dramatically improves precision for hard cases like abbreviated company names, nickname variations, and varied address formats — without manual review.

The verifier works with any provider supported by [litellm](https://docs.litellm.ai/), including fully local models that need no API key:

| Provider | Example model string | API key required |
|----------|---------------------|------------------|
| **Ollama** (local) | `ollama/llama3.1:8b`, `ollama/mistral` | No |
| **OpenRouter** | `openrouter/google/gemini-2.0-flash` | `OPENROUTER_API_KEY` |
| **OpenAI** | `openai/gpt-4o` | `OPENAI_API_KEY` |
| **Anthropic** | `anthropic/claude-3-5-sonnet-20241022` | `ANTHROPIC_API_KEY` |

```yaml
active_learning:
  enabled: true
  llm:
    provider: ollama                # local LLM, no API key needed
    model: llama3.1:8b
    base_url: http://localhost:11434
    timeout_seconds: 120
    healthcheck_on_start: true
    fallback_provider: openrouter   # auto-fallback if Ollama is unreachable
  low_threshold: 0.55              # below this → auto no_match
  high_threshold: 0.80             # above this → auto match
  refresh_every_n: 100             # re-optimize thresholds every N verifications
```

The LLM receives both records, the overall similarity score, and field-level scores, and returns a structured JSON verdict with decision, confidence, and reasoning. When the LLM overrides a score, the system synthesises a new score that pushes the pair above or below the thresholds so downstream clustering reflects the decision.

**Active Learning** wraps the verifier in a feedback loop (`AdaptiveLLMVerifier`). Every verdict is persisted to a feedback store in ArangoDB. Human corrections can be recorded via `record_human_correction()`, and the system periodically re-optimizes the low/high thresholds based on accumulated feedback — reducing LLM calls over time as the thresholds converge on the data distribution.

### MCP Tools

The MCP server exposes 15 tools organized into two groups — core ER operations and an advisory layer that helps an AI agent decide *how* to resolve before running the pipeline.

#### Core ER Tools

| Tool | What it does |
|------|-------------|
| `list_collections` | Discover all document/edge collections with counts |
| `find_duplicates` | Run the full blocking → similarity → clustering pipeline |
| `pipeline_status` | Document count, edge stats, cluster count for a collection |
| `resolve_entity` | Find existing records matching a given record (read-only) |
| `resolve_entity_cross_collection` | Link entities across two collections with field mapping |
| `explain_match` | Field-level similarity breakdown between two records |
| `get_clusters` | Return entity clusters with quality metadata (density, similarity stats) |
| `merge_entities` | Preview a golden record merge ("most_complete", "newest", or "first") |

#### Advisor Tools

An AI agent can use the advisor tools to analyze a dataset, choose the right strategy (including pre-ingest canonicalization vs post-ingest matching), tune weights, and simulate pipeline variants — all before executing anything.

| Tool | What it does |
|------|-------------|
| `profile_dataset` | Profile fields: null rates, distinct counts, heavy hitters, duplicate/hub risk |
| `recommend_resolution_strategy` | Rank strategy families from a profile and objective constraints |
| `recommend_blocking_candidates` | Rank single-field and composite blocking keys by fit score |
| `evaluate_blocking_plan` | Estimate pair volume, block-size distribution, and risk flags |
| `estimate_feature_weights` | Estimate field weights and threshold from labeled pairs |
| `simulate_pipeline_variants` | Compare multiple pipeline configs (runtime, memory, precision, recall) |
| `export_recommended_config` | Export a recommendation as deployable YAML/JSON with SHA256 hash |

The `recommend_resolution_strategy` tool evaluates five strategy families and ranks them against your data profile and objectives:

| Strategy | When it fits |
|----------|-------------|
| `hybrid_block_then_weighted_match` | General purpose — balanced precision, recall, throughput |
| `pre_ingest_canonicalize_then_match` | Canonicalize addresses/names *before* loading to reduce variant noise |
| `deterministic_rules_then_review` | Auditable rule-based matching with human review |
| `embedding_first_nearest_neighbor` | Semantic recall on noisy text (requires embeddings) |
| `graph_first_collective_resolution` | Multi-hop graph reasoning for complex relationship networks |

For address resolution specifically, there is a dedicated `AddressERPipeline` that handles street/city/state/postal normalization, custom analyzers, and address-specific blocking — usable standalone or as part of the recommended strategy.

#### Resources

| URI | Returns |
|-----|---------|
| `arango://collections/{collection}/summary` | Document count, inferred schema, sample documents |
| `arango://clusters/{collection}/{key}` | Full cluster details with all member documents |

### Other Integrations
- **ONNX Runtime** — faster CPU inference for embedding workloads
- **Incremental Resolver** — real-time single-record matching without batch re-run

### Web UI (Optional)

A browser-based interface for analysts and data stewards who need to interact with entity resolution results without writing code.

```bash
pip install "arango-entity-resolution[ui]"
arango-er ui --port 8787 --open
```

| Screen | What it does |
|--------|-------------|
| **Dashboard** | Operational overview — document counts, cluster stats, pending reviews, pipeline history |
| **Review Queue** | Side-by-side record comparison with field-level similarity scores, LLM reasoning display, and one-click human verdicts (keyboard shortcuts: M/N/S) |
| **Cluster Browser** | Paginated cluster list with quality scores, drill-down to interactive graph visualization (React Flow) |
| **Pipeline Runner** | Configure and execute pipelines with real-time WebSocket progress tracking |
| **Config Builder** | Visual pipeline configuration with advisor tool integration (strategy recommendations, weight estimation, variant simulation) |
| **Entity Resolver** | Interactive single-record resolution for testing |
| **Golden Records** | Field-level provenance, source ranking, and conflict resolution |

The UI calls the same Python services as the CLI and MCP server — no new resolution logic. See [UI Design](docs/architecture/ENTITY_RESOLUTION_UI.md) for architecture details.

## Configuration

Pipelines are driven by YAML (or JSON) configuration:

```yaml
entity_resolution:
  entity_type: company
  collection: companies

  blocking:
    strategy: collect
    fields:
      - field: state
      - field: city

  similarity:
    algorithm: jaro_winkler
    threshold: 0.80
    fields:
      name: 0.40
      address: 0.30
      phone: 0.20
      email: 0.10

  clustering:
    backend: auto          # picks best available backend
    min_cluster_size: 2
    store_results: true
```

See [`config/er_config.example.yaml`](config/er_config.example.yaml) for a complete example with all options.

## Why ArangoDB?

Entity resolution requires document storage, graph traversal, full-text search, and vector similarity — typically needing 3–4 separate systems. ArangoDB handles all of these natively:

- **Documents** — flexible schema for heterogeneous source records
- **Graphs** — native WCC, traversals, and relationship modeling
- **ArangoSearch** — integrated full-text search with phonetic, n-gram, and BM25 analyzers
- **Vectors** — embedding storage with native vector-index ANN search (`APPROX_NEAR_COSINE`); vector blocking requires ArangoDB 3.12+ (no brute-force fallback)

This eliminates the integration overhead of Elasticsearch + Neo4j + PostgreSQL stacks and keeps blocking, similarity, clustering, and golden records in a single transactional system.

## Performance

Record blocking reduces quadratic comparisons to linear:

| Records | Naive Pairs | After Blocking | Time |
|---------|-------------|----------------|------|
| 10K | 50M | 500K | ~2s |
| 100K | 5B | 5M | ~20s |
| 1M | 500B | 50M | ~3min |

Clustering backends scale from Union-Find (general purpose) through scipy sparse (large dense graphs) to GAE enterprise (millions of edges on dedicated compute).

## Project Structure

```
src/entity_resolution/
├── core/           Entity resolver, configurable pipeline, incremental resolver, orchestrator
├── services/       Blocking, similarity, clustering, embedding, export services
│   └── clustering_backends/   Union-Find, DFS, Sparse, AQL, GAE
├── strategies/     Exact, BM25, vector, geographic, LSH, shard-parallel blocking
├── mcp/            MCP server (15 tools, 2 resources)
├── reasoning/      LLM verifier, GraphRAG, feedback/active learning
├── enrichments/    Type constraints, context resolver, acronym handler, provenance sweeper
├── etl/            Canonical resolver, normalizers, arangoimport integration
├── similarity/     Weighted field similarity, geospatial/temporal validators
├── config/         YAML/JSON pipeline configuration
└── utils/          Database, logging, validation, constants
```

## Documentation

| Resource | Description |
|----------|-------------|
| [Documentation Index](docs/README.md) | Complete navigation |
| [Quick Start](docs/guides/QUICK_START.md) | Get started in 5 minutes |
| [API Reference](docs/api/API_REFERENCE.md) | CLI, MCP, Python, and config reference |
| [Advanced Modules Guide](docs/guides/ADVANCED_MODULES_GUIDE.md) | Orchestrator, GraphRAG, geospatial, feedback, ETL |
| [Performance Guide](docs/guides/PERFORMANCE_GUIDE.md) | Tuning and scaling |
| [Platform Setup](docs/guides/PLATFORM_SETUP.md) | ArangoDB, Docker, and provider setup |
| [Provider Matrix](docs/guides/PROVIDER_MATRIX.md) | LLM and embedding provider comparison |
| [Migration Guide](docs/guides/MIGRATION_GUIDE_V3.md) | Upgrading from v1.x or v2.x |
| [PRD](docs/PRD.md) | Product requirements and roadmap |

## Examples

| Example | Description |
|---------|-------------|
| [`yaml_config_pipeline.py`](examples/yaml_config_pipeline.py) | Config-driven end-to-end pipeline |
| [`clustering_backend_comparison.py`](examples/clustering_backend_comparison.py) | Compare all clustering backends |
| [`multi_strategy_orchestration.py`](examples/multi_strategy_orchestration.py) | Union/intersection blocking modes |
| [`onnx_runtime_embedding.py`](examples/onnx_runtime_embedding.py) | ONNX export and fast inference |
| [`incremental_resolution.py`](examples/incremental_resolution.py) | Real-time streaming resolution |
| [`ollama_llm_verification.py`](examples/ollama_llm_verification.py) | Local LLM match verification |
| [`vector_blocking_example.py`](examples/vector_blocking_example.py) | Semantic similarity blocking |

## Development

```bash
# Install with dev + test deps
pip install -e ".[dev,test,mcp,llm,ml]"

# Or use the Makefile
make install-all
make test          # all tests
make test-unit     # unit tests only
make lint          # flake8
make format        # black
make typecheck     # mypy
make build         # sdist + wheel
```

Pre-commit hooks validate syntax, check for hardcoded credentials, and verify critical imports. Pre-push hooks run the full test suite against a temporary ArangoDB instance.

## Contributing

1. Review the [PRD](docs/PRD.md) and [Documentation Index](docs/README.md)
2. Install git hooks: `./scripts/setup-git-hooks.sh`
3. Follow Python 3.10+ with type hints, DRY principles, and comprehensive docstrings
4. Run `make test` before submitting PRs
5. Update documentation for any user-facing changes

## License

[Apache License 2.0](LICENSE)
