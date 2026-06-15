# Advanced Modules Guide

**Version:** 3.5.1 | **Last Updated:** March 30, 2026

Reference documentation for advanced modules exported by `arango-entity-resolution` that extend the core pipeline with orchestration, geospatial validation, graph-RAG linking, ETL canonicalization, and more.

---

## Table of Contents

- [MultiStrategyOrchestrator](#multistrategyorchestrator) — combine blocking strategies
- [AddressERPipeline](#addresserpipeline) — YAML-driven address resolution
- [ShardParallelBlockingStrategy](#shardparallelblockingstrategy) — parallel blocking on sharded clusters
- [GeospatialValidator](#geospatialvalidator) — distance-based candidate filtering
- [TemporalValidator](#temporalvalidator) — date-proximity candidate filtering
- [DocumentEntityExtractor](#documententityextractor) — LLM entity extraction from text
- [GraphRAGLinker](#graphraglinker) — link extracted entities to a knowledge graph
- [IncrementalResolver](#incrementalresolver) — real-time single-record resolution
- [FeedbackStore](#feedbackstore) — persist LLM match verdicts
- [ThresholdOptimizer](#thresholdoptimizer) — auto-tune similarity thresholds from feedback
- [CanonicalResolver](#canonicalresolver) — ETL-time deduplication by normalized signature
- [ETL Normalizers](#etl-normalizers) — AddressNormalizer, TokenNormalizer, PostalNormalizer

---

## MultiStrategyOrchestrator

**Module:** `entity_resolution.core.orchestrator`

Runs multiple blocking strategies in sequence and merges/deduplicates candidate pairs. This lets you combine strategies with different strengths (exact key blocking, fuzzy BM25, semantic vector search) into a single candidate set with provenance tracking.

### API

```python
from entity_resolution import MultiStrategyOrchestrator

orchestrator = MultiStrategyOrchestrator(
    strategies,              # Sequence[BlockingStrategy] — ordered list of strategies
    merge_mode="union",      # "union" (recall) or "intersection" (precision)
    deduplicate=True,        # deduplicate pairs by (doc1_key, doc2_key)
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `strategies` | `Sequence[BlockingStrategy]` | *required* | One or more blocking strategy instances to execute |
| `merge_mode` | `"union"` \| `"intersection"` | `"union"` | How to combine pairs across strategies |
| `deduplicate` | `bool` | `True` | Remove duplicate pairs after merging |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `run()` | `list[dict]` | Execute all strategies and return merged candidates. Each pair carries a `"sources"` field listing which strategies produced it. |
| `get_statistics()` | `dict` | Per-strategy and aggregate stats from the last `run()` call |
| `from_config(db, config)` | `MultiStrategyOrchestrator` | Class method — build from a YAML/dict configuration |

### Usage

```python
from entity_resolution import (
    MultiStrategyOrchestrator,
    CollectBlockingStrategy,
    BM25BlockingStrategy,
    VectorBlockingStrategy,
)

collect = CollectBlockingStrategy(db, "companies", blocking_fields=["phone", "state"])
bm25 = BM25BlockingStrategy(db, "companies", search_field="name", view_name="companies_view")
vector = VectorBlockingStrategy(db, "companies", field="name")

orchestrator = MultiStrategyOrchestrator(
    strategies=[collect, bm25, vector],
    merge_mode="union",
)
candidates = orchestrator.run()
stats = orchestrator.get_statistics()

print(f"Total candidates: {stats['total_candidates']}")
for s in stats["per_strategy"]:
    print(f"  {s['strategy_name']}: {s['candidate_count']} pairs in {s['execution_time_seconds']}s")
```

### Configuration-Driven Construction

```python
config = {
    "merge_mode": "union",
    "deduplicate": True,
    "strategies": [
        {"type": "collect", "collection": "companies", "blocking_fields": ["phone", "state"]},
        {"type": "bm25", "collection": "companies", "search_field": "name", "view_name": "companies_view"},
    ],
}
orchestrator = MultiStrategyOrchestrator.from_config(db, config)
```

### When to Use

- **Use this** when a single blocking strategy doesn't achieve the recall you need. Union mode maximises recall; intersection mode maximises precision.
- **Prefer `ConfigurableERPipeline`** when you want end-to-end pipeline management (blocking + similarity + clustering) from a single config.

---

## AddressERPipeline

**Module:** `entity_resolution.core.address_pipeline`

Config-driven address entity resolution pipeline. Wraps `AddressERService` with YAML configuration, progress callbacks, and structured result metadata.

### API

```python
from entity_resolution import AddressERPipeline

pipeline = AddressERPipeline(
    db,          # ArangoDB StandardDatabase connection
    config,      # dict with required keys: "collection", "field_mapping"
)
```

| Config Key | Type | Required | Default | Description |
|------------|------|----------|---------|-------------|
| `collection` | `str` | Yes | — | Source document collection |
| `field_mapping` | `dict[str, str]` | Yes | — | Maps logical fields (`street`, `city`, `state`, `postal_code`) to collection field names |
| `edge_collection` | `str` | No | `"address_sameAs"` | Edge collection for similarity edges |
| `max_block_size` | `int` | No | `100` | Maximum block size for blocking |
| `create_edges` | `bool` | No | `True` | Write similarity edges to ArangoDB |
| `cluster` | `bool` | No | `True` | Run WCC clustering after edge creation |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `run(progress_callback=None)` | `dict` | Execute the full pipeline (setup, ER, optional clustering). Callback signature: `(step_name: str, pct: float)`. |
| `get_results()` | `dict` | Return results from the most recent `run()` |
| `from_yaml(db, yaml_path)` | `AddressERPipeline` | Class method — load config from a YAML file |

### Usage

```python
from entity_resolution import AddressERPipeline

config = {
    "collection": "addresses",
    "field_mapping": {
        "street": "ADDRESS_LINE_1",
        "city": "PRIMARY_TOWN",
        "state": "TERRITORY_CODE",
        "postal_code": "POSTAL_CODE",
    },
    "edge_collection": "address_sameAs",
    "max_block_size": 100,
    "cluster": True,
    "create_edges": True,
}

pipeline = AddressERPipeline(db, config)
results = pipeline.run(progress_callback=lambda step, pct: print(f"{step}: {pct:.0%}"))

print(f"Edges created: {results['edges_created']}")
print(f"Clusters found: {results['cluster_count']}")
print(f"Total time: {results['execution_time_seconds']}s")
```

### YAML Configuration

```yaml
address_resolution:
  collection: addresses
  field_mapping:
    street: ADDRESS_LINE_1
    city: PRIMARY_TOWN
    state: TERRITORY_CODE
    postal_code: POSTAL_CODE
  edge_collection: address_sameAs
  max_block_size: 100
  cluster: true
```

```python
pipeline = AddressERPipeline.from_yaml(db, "address_config.yaml")
results = pipeline.run()
```

### When to Use

- **Use this** for dedicated address deduplication workflows, especially when addresses live in their own collection.
- **Prefer `ConfigurableERPipeline`** for general-purpose entity resolution on companies, people, or other entity types.
- **Prefer `CanonicalResolver`** for ETL-time deduplication before data reaches ArangoDB.

---

## ShardParallelBlockingStrategy

**Module:** `entity_resolution.strategies.shard_parallel_blocking`

Distributes blocking work across ArangoDB shards for cluster deployments, enabling parallel candidate generation via `ThreadPoolExecutor`. Falls back to single-shard execution on standalone servers.

### API

```python
from entity_resolution import ShardParallelBlockingStrategy

strategy = ShardParallelBlockingStrategy(
    db,                          # ArangoDB StandardDatabase
    collection="companies",      # source collection
    blocking_fields=["state", "city"],
    max_block_size=100,          # skip oversized blocks
    min_block_size=2,            # minimum block size
    parallelism=4,               # concurrent shard queries
    filters=None,                # optional field filters
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db` | `StandardDatabase` | *required* | ArangoDB connection |
| `collection` | `str` | *required* | Source collection name |
| `blocking_fields` | `list[str]` | *required* | Fields forming the composite blocking key |
| `max_block_size` | `int` | `100` | Blocks larger than this are skipped |
| `min_block_size` | `int` | `2` | Minimum block size to generate pairs |
| `parallelism` | `int` | `4` | Max concurrent shard queries |
| `filters` | `dict` \| `None` | `None` | Field filters (same format as `BlockingStrategy`) |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `generate_candidates()` | `list[dict]` | Query all shards in parallel and return merged candidate pairs |
| `get_statistics()` | `dict` | Includes `shard_count`, `parallelism`, `blocking_fields` |

### Usage

```python
from entity_resolution import ShardParallelBlockingStrategy

strategy = ShardParallelBlockingStrategy(
    db,
    collection="companies",
    blocking_fields=["state", "city"],
    parallelism=8,
    max_block_size=200,
)

candidates = strategy.generate_candidates()
stats = strategy.get_statistics()
print(f"{stats['candidate_count']} pairs from {stats['shard_count']} shards")
```

### When to Use

- **Use this** on sharded ArangoDB cluster deployments where collections span multiple shards — it queries each shard independently to exploit parallelism.
- **Prefer `CollectBlockingStrategy`** on single-server deployments — the shard overhead adds no benefit.
- Plug into `MultiStrategyOrchestrator` alongside other strategies for combined blocking.

---

## GeospatialValidator

**Module:** `entity_resolution.similarity.geospatial_validator`

Validates candidate entity pairs by geographic distance using the Haversine formula. Designed as a pre- or post-filter in the similarity pipeline.

### API

```python
from entity_resolution import GeospatialValidator

validator = GeospatialValidator(
    max_distance_km=50.0,       # reject pairs beyond this distance
    lat_field="latitude",       # field name for latitude
    lon_field="longitude",      # field name for longitude
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_distance_km` | `float` | `50.0` | Maximum allowed distance in km |
| `lat_field` | `str` | `"latitude"` | Latitude field name in entity documents |
| `lon_field` | `str` | `"longitude"` | Longitude field name in entity documents |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `haversine(lat1, lon1, lat2, lon2)` | `float` | Great-circle distance in km |
| `validate_pair(record_a, record_b)` | `dict` | Returns `{valid, distance_km, reason}` |
| `filter_candidates(candidates, records, ...)` | `list[dict]` | Filter a candidate list, keeping only valid pairs. Adds `geo_distance_km` to each kept candidate. |

### Usage

```python
from entity_resolution import GeospatialValidator

geo = GeospatialValidator(max_distance_km=25.0, lat_field="lat", lon_field="lon")

# Validate a single pair
result = geo.validate_pair(
    {"lat": 40.7128, "lon": -74.0060},   # New York
    {"lat": 40.7580, "lon": -73.9855},   # Midtown
)
print(result)  # {"valid": True, "distance_km": 5.12, "reason": "within range"}

# Filter a candidate list
records = {
    "A": {"lat": 40.71, "lon": -74.00},
    "B": {"lat": 40.75, "lon": -73.98},
    "C": {"lat": 34.05, "lon": -118.24},  # Los Angeles
}
candidates = [
    {"doc1_key": "A", "doc2_key": "B"},
    {"doc1_key": "A", "doc2_key": "C"},
]
kept = geo.filter_candidates(candidates, records)
# Only A-B pair survives; A-C exceeds 25km threshold
```

### When to Use

- **Use this** as a post-blocking filter to eliminate physically impossible matches (e.g. two offices listed at locations 500km apart).
- Pairs with missing coordinates pass through by default (not rejected).

---

## TemporalValidator

**Module:** `entity_resolution.similarity.geospatial_validator`

Validates candidate pairs by temporal proximity — checks whether two entities are close enough in time (founding year, date ranges, active periods).

### API

```python
from entity_resolution import TemporalValidator

validator = TemporalValidator(
    max_gap_days=365,            # reject pairs more than 1 year apart
    date_field="founded_date",   # field containing the date value
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_gap_days` | `int` | `365` | Maximum gap in days between two time points |
| `date_field` | `str` | `"founded_date"` | Field name for the date/year value |

Supported date formats: `YYYY-MM-DD`, `YYYY/MM/DD`, `MM/DD/YYYY`, `YYYY` (year only), `datetime`/`date` objects, and numeric years.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `validate_pair(record_a, record_b)` | `dict` | Returns `{valid, gap_days, reason}` |
| `filter_candidates(candidates, records, ...)` | `list[dict]` | Filter candidates, adding `temporal_gap_days` to kept pairs |

### Usage

```python
from entity_resolution import TemporalValidator

temporal = TemporalValidator(max_gap_days=180, date_field="founded_date")

result = temporal.validate_pair(
    {"founded_date": "2020-01-15"},
    {"founded_date": "2020-06-01"},
)
print(result)  # {"valid": True, "gap_days": 138, "reason": "within range"}
```

### When to Use

- **Use this** alongside `GeospatialValidator` to add temporal constraints to candidate filtering.
- Stack both validators for multi-dimensional filtering (geography + time).

---

## DocumentEntityExtractor

**Module:** `entity_resolution.reasoning.graph_rag`

Uses an LLM to extract structured entities (companies, people, addresses) from unstructured text. Part of the GraphRAG pipeline.

### API

```python
from entity_resolution import DocumentEntityExtractor

extractor = DocumentEntityExtractor(
    llm_config=None,             # LLMProviderConfig or None for env defaults
    entity_types=None,           # list of valid types; defaults to ["company", "person", "address", "organization"]
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `llm_config` | `LLMProviderConfig` \| `None` | `None` | LLM provider configuration. Uses environment defaults when `None`. |
| `entity_types` | `list[str]` \| `None` | `["company", "person", "address", "organization"]` | Valid entity types to extract |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `extract(text)` | `list[dict]` | Extract entities from a single document. Each dict has `name`, `type`, `attributes`, and `extraction_metadata`. |
| `extract_batch(texts)` | `list[list[dict]]` | Extract from multiple documents |

### Usage

```python
from entity_resolution import DocumentEntityExtractor, LLMProviderConfig

config = LLMProviderConfig(provider="openai", model="gpt-4o-mini")
extractor = DocumentEntityExtractor(llm_config=config, entity_types=["company", "person"])

entities = extractor.extract("""
    Acme Corporation, founded in New York by John Smith,
    recently acquired Widget Labs in San Francisco.
""")

for ent in entities:
    print(f"{ent['name']} ({ent['type']}): {ent['attributes']}")
    # Acme Corporation (company): {"city": "New York"}
    # John Smith (person): {}
    # Widget Labs (company): {"city": "San Francisco"}
```

### When to Use

- **Use this** to bridge unstructured documents into your entity resolution graph.
- Pair with `GraphRAGLinker` to link extracted entities against existing graph entities.
- Requires the `[llm]` extra: `pip install "arango-entity-resolution[llm]"`.

---

## GraphRAGLinker

**Module:** `entity_resolution.reasoning.graph_rag`

Links extracted entities (from `DocumentEntityExtractor`) to existing entities in an ArangoDB graph using Jaro-Winkler similarity matching. Creates edges with provenance metadata.

### API

```python
from entity_resolution import GraphRAGLinker

linker = GraphRAGLinker(
    db,                                # ArangoDB database connection
    entity_collection="companies",     # collection containing existing entities
    edge_collection="extracted_links", # edge collection for link edges
    similarity_threshold=0.70,         # minimum score to create a link
    name_field="name",                 # field containing entity names
    document_collection="documents",   # source-document collection (edge _from side)
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db` | `StandardDatabase` | *required* | ArangoDB connection |
| `entity_collection` | `str` | *required* | Collection to match against |
| `edge_collection` | `str` | *required* | Edge collection for storing links |
| `similarity_threshold` | `float` | `0.70` | Minimum Jaro-Winkler score to link |
| `name_field` | `str` | `"name"` | Field in the entity collection containing names |
| `document_collection` | `str \| None` | `None` | Source-document collection. Provenance edges run **document → entity**; required (with `source_doc_key`) for edges to be created. |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `link(extracted_entities, source_doc_key=None)` | `list[dict]` | Match extracted entities to existing graph entities. Returns dicts with `extracted`, `matched_key`, `score`, `linked`, `edge_key`. `edge_key` is `None` unless both `document_collection` and `source_doc_key` are provided. |

### Usage

```python
from entity_resolution import DocumentEntityExtractor, GraphRAGLinker

# Step 1: Extract entities from text
extractor = DocumentEntityExtractor()
entities = extractor.extract("Acme Corp signed a deal with Widget Labs in Boston.")

# Step 2: Link to existing graph
linker = GraphRAGLinker(
    db,
    entity_collection="companies",
    edge_collection="doc_entity_links",
    similarity_threshold=0.75,
    document_collection="contracts",   # edges run contracts/<key> -> companies/<key>
)
results = linker.link(entities, source_doc_key="contract_42")

for r in results:
    if r["linked"]:
        print(f"Linked '{r['extracted']['name']}' -> {r['matched_key']} (score={r['score']})")
    else:
        print(f"No match for '{r['extracted']['name']}'")
```

### When to Use

- **Use this** to connect unstructured document content to your structured entity graph.
- The extraction + linking pipeline replaces manual entity tagging.
- Requires the `[llm]` extra for `DocumentEntityExtractor`; `jellyfish` for similarity.

---

## IncrementalResolver

**Module:** `entity_resolution.core.incremental_resolver`

Resolves a single new record against an existing collection without re-processing the full dataset. Uses prefix-based blocking and Jaro-Winkler similarity for real-time / streaming entity resolution.

### API

```python
from entity_resolution.core.incremental_resolver import IncrementalResolver

resolver = IncrementalResolver(
    db,                             # ArangoDB database handle
    collection="companies",         # collection to search
    fields=["name", "city"],        # fields for blocking and similarity
    confidence_threshold=0.80,      # minimum score to include in results
    blocking_strategy="prefix",     # "prefix" or "full"
    prefix_length=3,                # chars used for prefix blocking keys
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db` | `StandardDatabase` | *required* | ArangoDB connection |
| `collection` | `str` | *required* | Document collection to search |
| `fields` | `list[str]` | *required* | Fields for blocking key construction and similarity |
| `confidence_threshold` | `float` | `0.80` | Minimum weighted score to include |
| `blocking_strategy` | `str` | `"prefix"` | `"prefix"` uses first N chars as blocking keys; `"full"` compares all documents (small collections only) |
| `prefix_length` | `int` | `3` | Character count for prefix blocking keys |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `resolve(record, top_k=10, exclude_key=None)` | `list[dict]` | Return up to `top_k` matches. Each result has `_key`, `score`, `field_scores`, and `match`. |

### Usage

```python
from entity_resolution.core.incremental_resolver import IncrementalResolver

resolver = IncrementalResolver(
    db,
    collection="companies",
    fields=["name", "city", "state"],
    confidence_threshold=0.75,
)

matches = resolver.resolve(
    {"name": "Acme Corp", "city": "Boston", "state": "MA"},
    top_k=5,
)

for m in matches:
    print(f"  {m['_key']}: score={m['score']}")
    for field, info in m["field_scores"].items():
        print(f"    {field}: {info['score']} ({info['method']})")
```

### When to Use

- **Use this** for real-time resolution — e.g. checking if a new customer already exists before inserting.
- Powers the `resolve_entity` MCP tool.
- **Prefer `ConfigurableERPipeline`** for batch resolution of entire collections.

---

## FeedbackStore

**Module:** `entity_resolution.reasoning.feedback`

Persists LLM match verification verdicts (and human corrections) in an ArangoDB collection. Every verdict is valuable training data for threshold optimization.

### API

```python
from entity_resolution.reasoning.feedback import FeedbackStore

store = FeedbackStore(
    db,                              # ArangoDB database handle
    collection="er_llm_feedback",    # collection for verdicts
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db` | `StandardDatabase` | *required* | ArangoDB connection |
| `collection` | `str` | `"er_llm_feedback"` | Collection name for verdict storage |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `save(record_a, record_b, score, decision, confidence, *, source, model, field_scores)` | `str` | Persist a verdict. Returns the document `_key`. Uses deterministic keys to prevent duplicates on re-runs. |
| `record_human_correction(key_a, key_b, correct_decision, *, score, confidence)` | `str` | Override a previous verdict with a human-confirmed label |
| `all_verdicts()` | `list[dict]` | Retrieve all stored verdicts |
| `verdicts_by_decision(decision)` | `list[dict]` | Filter by `"match"` or `"no_match"` |
| `stats()` | `dict` | Aggregate statistics: count, avg score, and avg confidence by decision |

### Usage

```python
from entity_resolution.reasoning.feedback import FeedbackStore

store = FeedbackStore(db)

# Save an LLM verdict
store.save(
    record_a={"_key": "A1", "name": "Acme Corp"},
    record_b={"_key": "A2", "name": "Acme Corporation"},
    score=0.87,
    decision="match",
    confidence=0.95,
    model="gpt-4o-mini",
)

# Record a human correction
store.record_human_correction("A1", "A2", "match")

# Review statistics
print(store.stats())
# {"by_decision": [{"decision": "match", "count": 42, ...}], "total": 58}
```

### When to Use

- **Use this** to accumulate labeled pairs from LLM verification runs.
- Feed into `ThresholdOptimizer` to auto-tune similarity thresholds.
- Human corrections via `record_human_correction` improve calibration over time.

---

## ThresholdOptimizer

**Module:** `entity_resolution.reasoning.feedback`

Reads the `FeedbackStore` and uses isotonic regression (or percentile analysis as fallback) to derive optimal `low_threshold` and `high_threshold` values that minimize LLM call volume while maintaining target precision.

### API

```python
from entity_resolution.reasoning.feedback import FeedbackStore, ThresholdOptimizer

store = FeedbackStore(db)
optimizer = ThresholdOptimizer(
    feedback_store=store,
    target_precision=0.95,     # minimum acceptable precision for "match"
    min_samples=20,            # samples required before optimization runs
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `feedback_store` | `FeedbackStore` | *required* | Source of labeled verdicts |
| `target_precision` | `float` | `0.95` | Precision target for match classification |
| `min_samples` | `int` | `20` | Minimum labeled pairs before optimization activates |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `optimize()` | `dict` | Returns `{low_threshold, high_threshold, sample_count, optimized, method}`. Falls back to defaults if below `min_samples`. |

### Usage

```python
from entity_resolution.reasoning.feedback import FeedbackStore, ThresholdOptimizer

store = FeedbackStore(db, collection="er_llm_feedback")
optimizer = ThresholdOptimizer(store, target_precision=0.95, min_samples=50)

result = optimizer.optimize()
if result["optimized"]:
    print(f"Recommended: low={result['low_threshold']}, high={result['high_threshold']}")
    print(f"Method: {result['method']}, samples: {result['sample_count']}")
else:
    print(f"Not enough samples: {result['reason']}")
```

The `AdaptiveLLMVerifier` class (same module) wraps `LLMMatchVerifier` to automatically save verdicts and refresh thresholds every N calls:

```python
from entity_resolution.reasoning.feedback import FeedbackStore, AdaptiveLLMVerifier

store = FeedbackStore(db)
verifier = AdaptiveLLMVerifier(feedback_store=store, refresh_every=100)

result = verifier.verify(record_a, record_b, score=0.72, field_scores=fs)
# Verdict auto-saved; thresholds auto-refresh every 100 calls
```

### When to Use

- **Use this** after accumulating enough LLM verdicts (20+ by default) to replace hand-tuned thresholds.
- Uses `scikit-learn` isotonic regression when available; falls back to percentile analysis otherwise.
- The `[ml]` extra provides scikit-learn: `pip install "arango-entity-resolution[ml]"`.

---

## CanonicalResolver

**Module:** `entity_resolution.etl.canonical_resolver`

Streams input records (TSV/CSV or programmatic `add()`), normalizes each row via a pluggable normalizer, groups by canonical signature, and writes deduplicated JSONL output suitable for bulk loading via `arangoimport`.

### API

```python
from entity_resolution import CanonicalResolver

resolver = CanonicalResolver(
    normalizer=None,             # normalizer object (default: AddressNormalizer)
    signature_fields=None,       # fields forming the canonical signature
    field_mapping=None,          # maps logical field names to input columns
    required_fields=None,        # fields that must be non-empty
    shard_key_field="postal",    # field for SmartGraph shard prefix
    shard_key_length=3,          # characters in shard prefix
    hub_threshold=50,            # in-degree above which a node is a hub
    hub_markers=None,            # {column: value} pairs that mark hubs
    provenance=True,             # track raw variants and transforms
    max_variants=20,             # max variant entries per signature
    node_label="ADDRESS",        # label for output field names
    extra_node_fields=None,      # additional columns to carry through
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `normalizer` | object | `AddressNormalizer()` | Any object with `normalize(field, raw, track=False)` method |
| `signature_fields` | `list[str]` | `["street", "city", "state", "postal"]` | Logical fields forming the canonical signature |
| `field_mapping` | `dict[str, str]` | `{}` | Maps logical names to input column names |
| `required_fields` | `list[str]` | first 2 signature fields | Records skipped when all required fields are empty |
| `shard_key_field` | `str` | `"postal"` | Field to derive SmartGraph shard prefix from |
| `shard_key_length` | `int` | `3` | Characters in the shard prefix (e.g. 3 for ZIP3) |
| `hub_threshold` | `int` | `50` | In-degree above which a node is classified as a hub |
| `provenance` | `bool` | `True` | Track raw variants and normalization transforms |
| `node_label` | `str` | `"ADDRESS"` | Label used in output field names |

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `add(record, source_key=None, edge_fields=None)` | `None` | Add a single input record |
| `process_file(input_path, delimiter, header_path, key_field, source_lookup, edge_extra_fields)` | `dict` | Process an entire TSV/CSV file |
| `write_nodes(output_path, format="jsonl")` | `int` | Write canonical nodes to JSONL or TSV. Returns count. |
| `write_edges(output_path, from_collection, to_collection, format="jsonl", consolidate=True)` | `int` | Write edge documents. `consolidate=True` merges duplicate edges into subdocument arrays. |
| `stats` (property) | `dict` | Dedup statistics: `input_rows`, `skipped`, `unique_signatures`, `reduction_pct`, `hubs`, `total_edges` |

### Usage

```python
from entity_resolution import CanonicalResolver, AddressNormalizer

resolver = CanonicalResolver(
    normalizer=AddressNormalizer(),
    signature_fields=["street", "city", "state", "postal"],
    field_mapping={
        "street": "ADDRESS_LINE_1",
        "city": "PRIMARY_TOWN",
        "state": "TERRITORY_CODE",
        "postal": "POSTAL_CODE",
    },
    hub_threshold=50,
    shard_key_field="postal",
    shard_key_length=3,
)

# Process a file
stats = resolver.process_file("addresses.tsv", delimiter="\t")
print(f"Reduced {stats['input_rows']} rows to {stats['unique_signatures']} unique addresses "
      f"({stats['reduction_pct']}% reduction)")

# Write output
node_count = resolver.write_nodes("canonical_addresses.jsonl")
edge_count = resolver.write_edges(
    "address_edges.jsonl",
    from_collection="registrations",
    to_collection="canonical_addresses",
    consolidate=True,
)
```

### When to Use

- **Use this** at ETL time to deduplicate address records *before* loading into ArangoDB.
- Produces SmartGraph-compatible `_key` values with shard prefixes.
- Hub detection identifies high-degree nodes (e.g. registered agent addresses) that may need special handling.
- **Prefer `AddressERPipeline`** for deduplication *after* data is already in ArangoDB.

---

## ETL Normalizers

**Module:** `entity_resolution.etl.normalizers`

Three normalizer classes used by `CanonicalResolver` and available for standalone use.

### AddressNormalizer

US-locale address normalizer implementing the normalizer protocol expected by `CanonicalResolver`. Dispatches to field-specific methods for street, city, state, and postal code normalization.

```python
from entity_resolution import AddressNormalizer

norm = AddressNormalizer()

# Street normalization: expands abbreviations, strips unit designators
result, transforms = norm.normalize("street", "123 N Main St Ste 200", track=True)
# result: "123 NORTH MAIN STREET"
# transforms: ["case_normalized", "expand:N->NORTH", "expand:ST->STREET", "unit_stripped:STE 200"]

# State normalization: converts to 2-letter abbreviation
norm.normalize("state", "California")       # "CA"
norm.normalize("state", "new york")         # "NY"

# Postal normalization: extracts first 5 digits
norm.normalize("postal", "10001-4321")      # "10001"

# City normalization: uppercase, collapsed whitespace
norm.normalize("city", "  san   francisco  ")  # "SAN FRANCISCO"
```

Key expansion maps (single source of truth shared across the library):
- `STREET_SUFFIX_MAP` — ST->STREET, AVE->AVENUE, DR->DRIVE, etc.
- `DIRECTIONAL_MAP` — N->NORTH, SW->SOUTHWEST, etc.
- `ORDINAL_MAP` — 1ST->FIRST, 2ND->SECOND, etc.
- `UNIT_DESIGNATORS` — STE, APT, UNIT, FL, etc. (triggers truncation)

### TokenNormalizer

General-purpose token-level normalizer with configurable expansion maps and optional transform tracking.

```python
from entity_resolution import TokenNormalizer

normalizer = TokenNormalizer(
    expansions={"ST": "STREET", "AVE": "AVENUE"},
    strip_after={"STE", "APT"},
    case="upper",
)

result = normalizer.normalize("123 Main St")        # "123 MAIN STREET"
result, transforms = normalizer.normalize("123 Main St", track=True)
# ("123 MAIN STREET", ["case_normalized", "expand:ST->STREET"])
```

### PostalNormalizer

Extracts N-digit postal codes and derives shard key prefixes.

```python
from entity_resolution import PostalNormalizer

postal = PostalNormalizer(digits=5)
postal.normalize("10001-4321")           # "10001"
postal.shard_prefix("10001-4321", 3)     # "100"
postal.shard_prefix("", 3)              # "000" (fallback)
```

### When to Use

- **Use normalizers directly** when building custom ETL pipelines or need field-level normalization outside `CanonicalResolver`.
- **Use `CanonicalResolver`** when you want the full dedup-and-export workflow.
- `AddressNormalizer` is the default normalizer for `CanonicalResolver` — override it for non-US locales or non-address domains.

---

## Summary: Module Selection Guide

| Use Case | Module |
|----------|--------|
| Combine multiple blocking strategies | `MultiStrategyOrchestrator` |
| Dedicated address ER pipeline | `AddressERPipeline` |
| Parallel blocking on sharded clusters | `ShardParallelBlockingStrategy` |
| Filter candidates by geographic distance | `GeospatialValidator` |
| Filter candidates by temporal proximity | `TemporalValidator` |
| Extract entities from unstructured text | `DocumentEntityExtractor` |
| Link extracted entities to existing graph | `GraphRAGLinker` |
| Real-time single-record resolution | `IncrementalResolver` |
| Store LLM verification verdicts | `FeedbackStore` |
| Auto-tune thresholds from labeled pairs | `ThresholdOptimizer` |
| ETL-time dedup by normalized signature | `CanonicalResolver` |
| Field-level text normalization | `AddressNormalizer`, `TokenNormalizer`, `PostalNormalizer` |
