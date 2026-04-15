# Entity Resolution UI — Design Document

**Status**: Implemented (Phase 1–3)  
**Created**: April 13, 2026  
**Authors**: Architecture Team

---

## Executive Summary

This document proposes adding an optional web UI to the ArangoDB Entity Resolution library. The UI provides a visual interface for the three workflows that most benefit from human interaction: **reviewing ambiguous matches**, **inspecting entity clusters**, and **monitoring pipeline execution**. It ships as an optional install (`pip install "arango-entity-resolution[ui]"`) and is launched with a single command (`arango-er ui`).

The UI does not introduce new resolution logic. It is a presentation layer over the existing Python services and MCP tool handlers, exposed through a lightweight FastAPI backend. This keeps the library's core resolution path unchanged while giving analysts, data stewards, and operators a practical visual interface.

---

## Motivation

### The Gap

The library currently exposes three interfaces: Python API, CLI (`arango-er`), and MCP server (`arango-er-mcp`). All three are effective for developers and AI agents. None of them serve the human analyst who needs to:

1. **Review ambiguous matches** — Pairs scoring 0.55–0.80 are routed to `AdaptiveLLMVerifier`, but the `record_human_correction()` API has no surface. There is no way for a non-developer to see these pairs, compare the records side-by-side, and render a judgment.

2. **Inspect clusters visually** — `get_clusters` returns quality metadata (`density`, `average_similarity`, `quality_score`), but understanding *why* records were grouped requires reading JSON and mentally reconstructing the graph. A visual cluster view with member records and similarity edges is dramatically more intuitive.

3. **Monitor pipeline runs** — Blocking reduction ratios, similarity distributions, LLM curation counts, and skipped blocks are logged or returned in result dicts, but there's no operational view that ties them together.

4. **Resolve golden record conflicts** — When sources disagree on a field value and `GoldenRecordService` flags a conflict, a human needs to see the competing values, their provenance, and pick a winner.

5. **Configure pipelines visually** — Building YAML configs for blocking strategies, similarity weights, and clustering backends is error-prone for non-developers. A guided config builder would lower the barrier.

### Why Now

The library already has the backend capabilities to support every screen described in this document. The MCP server's 14 tools and 2 resources, the services layer, and the `FeedbackStore`/`AdaptiveLLMVerifier` together form a complete API surface. The UI is a matter of wiring a presentation layer to existing code, not building new resolution logic.

The centralized ER service roadmap (v4.x) will eventually require an admin UI for tenant management, schema registry, and subscription monitoring. Starting with a focused library UI now establishes the frontend infrastructure, component patterns, and API conventions that the centralized service UI will extend.

---

## Architecture

### Deployment Model

```
┌─────────────────────────────────────────────────────────────┐
│                    User's Machine / Server                   │
│                                                             │
│  ┌────────────┐     ┌──────────────┐     ┌──────────────┐  │
│  │  Browser    │────▶│  FastAPI      │────▶│  ArangoDB    │  │
│  │  (React)    │◀────│  Backend      │◀────│              │  │
│  │  :5173      │     │  :8787        │     │  :8529       │  │
│  └────────────┘     └──────────────┘     └──────────────┘  │
│                            │                                 │
│                     ┌──────┴──────┐                          │
│                     │ ER Services │                          │
│                     │ (in-process)│                          │
│                     └─────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

**In production builds**, the React app is compiled to static assets and bundled into the Python package. FastAPI serves them directly — no separate frontend server needed. During development, Vite's dev server runs alongside FastAPI with hot reload.

### Technology Choices

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Backend** | FastAPI | Already referenced in DESIGN.md as the orchestration HTTP layer. Async, OpenAPI docs, Pydantic models — natural fit for a Python library. |
| **Frontend** | React 19 + TypeScript | Component-based, large ecosystem, easy to find contributors. TypeScript catches contract drift between frontend and backend early. |
| **UI Components** | shadcn/ui + Tailwind CSS | Copy-paste components (not a dependency), tree-shakeable, accessible, modern aesthetic. No heavy framework lock-in. |
| **State Management** | TanStack Query (React Query) | Server-state caching, background refetch, optimistic updates. Eliminates manual loading/error/cache logic. |
| **Charts** | Recharts | React-native charting on top of D3. Lightweight, composable. |
| **Graph Visualization** | React Flow or Cytoscape.js | Interactive node-edge diagrams for cluster graphs. React Flow for simpler cases; Cytoscape for dense graphs. |
| **Bundling** | Vite | Fast builds, HMR, trivial to bundle static output into a Python package. |

### Package Structure

```
src/entity_resolution/
├── ui/
│   ├── __init__.py
│   ├── app.py              # FastAPI application factory
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── collections.py  # Collection listing and profiling
│   │   ├── pipeline.py     # Pipeline execution and status
│   │   ├── clusters.py     # Cluster listing, detail, quality
│   │   ├── review.py       # Review queue and human corrections
│   │   ├── golden.py       # Golden record management
│   │   ├── config.py       # Config builder endpoints
│   │   └── ws.py           # WebSocket for live pipeline progress
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py      # Pydantic request/response models
│   └── static/             # Built React assets (populated by build step)
│       ├── index.html
│       ├── assets/
│       └── ...
│
ui/                          # Frontend source (not shipped in sdist)
├── package.json
├── tsconfig.json
├── vite.config.ts
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/                # Generated or hand-written API client
│   ├── components/
│   │   ├── layout/         # Shell, sidebar, navigation
│   │   ├── clusters/       # ClusterList, ClusterDetail, ClusterGraph
│   │   ├── review/         # ReviewQueue, PairComparison, VerdictPanel
│   │   ├── pipeline/       # PipelineRunner, PipelineStatus, StageProgress
│   │   ├── golden/         # GoldenRecordView, ConflictResolver
│   │   ├── config/         # ConfigBuilder, StrategySelector, WeightSliders
│   │   └── shared/         # DataTable, ScoreBadge, FieldDiff, SearchBar
│   ├── hooks/              # useReviewQueue, useClusters, usePipeline, etc.
│   ├── pages/              # Route-level page components
│   └── lib/                # Utilities, constants, types
├── public/
└── index.html
```

### CLI Integration

```bash
# Launch the UI (production mode — serves bundled assets)
arango-er ui --port 8787 --host 0.0.0.0

# Launch with auto-open browser
arango-er ui --open

# Launch in development mode (requires ui/ source + node_modules)
arango-er ui --dev
```

The `ui` command is added to `cli.py` alongside existing commands. It starts the FastAPI server with Uvicorn, connects to ArangoDB using the same `@connection_options` as other CLI commands, and optionally opens the browser.

---

## Backend API

The FastAPI backend wraps existing services. Every endpoint calls the same Python code that the MCP tools and CLI use — no parallel resolution paths.

### Endpoint Map

#### Collections

| Method | Path | Service | Notes |
|--------|------|---------|-------|
| `GET` | `/api/collections` | `list_collections` (MCP) | Returns name, type, count |
| `GET` | `/api/collections/{name}/profile` | `profile_dataset` (MCP advisor) | Field stats, null rates, heavy hitters |
| `GET` | `/api/collections/{name}/sample` | `arango://collections/{name}/summary` (MCP resource) | Schema + sample docs |

#### Pipeline

| Method | Path | Service | Notes |
|--------|------|---------|-------|
| `POST` | `/api/pipeline/run` | `ConfigurableERPipeline.run()` | Accepts config JSON; streams progress via WebSocket |
| `GET` | `/api/pipeline/status/{collection}` | `pipeline_status` (MCP) | Doc count, edge stats, cluster count |
| `GET` | `/api/pipeline/history` | New: pipeline run log | Timestamped run results stored in `_er_pipeline_runs` |
| `WS` | `/ws/pipeline/{run_id}` | New: live progress | Stage-by-stage progress events during a run |

#### Clusters

| Method | Path | Service | Notes |
|--------|------|---------|-------|
| `GET` | `/api/clusters/{collection}` | `get_clusters` (MCP) | Paginated list with quality metadata |
| `GET` | `/api/clusters/{collection}/{key}` | `arango://clusters/{collection}/{key}` (MCP resource) | Full cluster detail with member docs |
| `GET` | `/api/clusters/{collection}/{key}/graph` | New: cluster graph | Nodes (members) + edges (similarity) for visualization |
| `GET` | `/api/clusters/{collection}/stats` | `WCCClusteringService.get_statistics()` | Aggregate cluster statistics |

#### Review Queue

| Method | Path | Service | Notes |
|--------|------|---------|-------|
| `GET` | `/api/review/{collection}` | `FeedbackStore.all_verdicts()` | Pairs awaiting review, filtered by status |
| `GET` | `/api/review/{collection}/stats` | `FeedbackStore.stats()` | Verdict distribution, correction counts |
| `GET` | `/api/review/{collection}/pair/{key_a}/{key_b}` | `explain_match` (MCP) + doc lookup | Full comparison for a specific pair |
| `POST` | `/api/review/{collection}/pair/{key_a}/{key_b}/verdict` | `AdaptiveLLMVerifier.record_human_correction()` | Submit human verdict |
| `POST` | `/api/review/{collection}/optimize` | `AdaptiveLLMVerifier.optimize_thresholds()` | Trigger threshold re-optimization |
| `GET` | `/api/review/{collection}/thresholds` | `AdaptiveLLMVerifier.current_thresholds()` | Current low/high thresholds |

#### Golden Records

| Method | Path | Service | Notes |
|--------|------|---------|-------|
| `POST` | `/api/golden/{collection}/preview` | `merge_entities` (MCP) | Preview merge without persisting |
| `POST` | `/api/golden/{collection}/merge` | `GoldenRecordService.generate_golden_records()` | Execute merge with chosen strategy |
| `GET` | `/api/golden/{collection}/{entity_key}` | Direct ArangoDB lookup | Retrieve a golden record |
| `GET` | `/api/golden/{collection}/{entity_key}/provenance` | Direct ArangoDB lookup | Source records and field-level provenance |

#### Resolution

| Method | Path | Service | Notes |
|--------|------|---------|-------|
| `POST` | `/api/resolve/{collection}` | `resolve_entity` (MCP) | Submit a record for matching |
| `POST` | `/api/resolve/cross` | `resolve_entity_cross_collection` (MCP) | Cross-collection resolution |

#### Configuration

| Method | Path | Service | Notes |
|--------|------|---------|-------|
| `POST` | `/api/config/validate` | `ERPipelineConfig.validate()` | Validate a config and return errors |
| `POST` | `/api/config/recommend` | `recommend_resolution_strategy` (MCP advisor) | Get strategy recommendations |
| `POST` | `/api/config/blocking` | `recommend_blocking_candidates` (MCP advisor) | Get blocking key recommendations |
| `POST` | `/api/config/simulate` | `simulate_pipeline_variants` (MCP advisor) | Compare pipeline configurations |
| `POST` | `/api/config/export` | `export_recommended_config` (MCP advisor) | Export config as YAML/JSON |

#### Export

| Method | Path | Service | Notes |
|--------|------|---------|-------|
| `POST` | `/api/export/{collection}` | `ClusterExportService.export()` | Export clusters to JSON/CSV |
| `GET` | `/api/export/{collection}/download/{filename}` | Static file serve | Download exported artifacts |

### WebSocket Protocol

Pipeline runs stream progress events over WebSocket:

```json
{"type": "stage_start", "stage": "blocking", "timestamp": "..."}
{"type": "stage_progress", "stage": "blocking", "progress": 0.45, "detail": "Processing block 450/1000"}
{"type": "stage_complete", "stage": "blocking", "result": {"candidates_found": 12450, "reduction_ratio": 0.9987}}
{"type": "stage_start", "stage": "similarity", "timestamp": "..."}
{"type": "stage_complete", "stage": "similarity", "result": {"edges_created": 3200, "avg_score": 0.72}}
{"type": "stage_start", "stage": "clustering", "timestamp": "..."}
{"type": "stage_complete", "stage": "clustering", "result": {"clusters_found": 890, "largest_cluster": 12}}
{"type": "pipeline_complete", "total_runtime_seconds": 14.3, "summary": {...}}
```

This requires adding progress callback hooks to `ConfigurableERPipeline.run()` — a small, backward-compatible change (optional `on_progress: Callable` parameter).

---

## Screen Designs

### 1. Dashboard (Home)

The landing page shows an operational overview across all collections.

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│  Entity Resolution Dashboard                    [collection ▼] │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  12,450  │  │    890   │  │    47    │  │   0.87   │    │
│  │ Documents│  │ Clusters │  │ Pending  │  │ Avg Qual │    │
│  │          │  │          │  │ Reviews  │  │ Score    │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│                                                              │
│  ┌─────────────────────────┐  ┌─────────────────────────┐   │
│  │  Cluster Size Dist.     │  │  Similarity Score Dist.  │   │
│  │  ▁▃▅▇█▇▅▃▁             │  │  ▁▂▃▅▇█▇▅▃▂▁           │   │
│  │  (histogram)            │  │  (histogram)             │   │
│  └─────────────────────────┘  └─────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Recent Pipeline Runs                                │   │
│  │  ┌──────┬────────┬──────────┬────────────┬────────┐  │   │
│  │  │ Time │ Config │ Clusters │ Review Q   │ Status │  │   │
│  │  ├──────┼────────┼──────────┼────────────┼────────┤  │   │
│  │  │ 2h   │ prod   │ 890      │ 47 pending │   ✓    │  │   │
│  │  │ 1d   │ prod   │ 845      │ 0          │   ✓    │  │   │
│  │  └──────┴────────┴──────────┴────────────┴────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

**Data sources:** `pipeline_status`, `get_clusters` (aggregate stats), `FeedbackStore.stats()`, pipeline run history.

---

### 2. Review Queue

The highest-value screen. Shows pairs that need human judgment, ordered by confidence (most uncertain first).

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│  Review Queue                    47 pending │ 312 resolved   │
├──────────────────────────────────────────────────────────────┤
│  Filter: [All ▼]  [0.55-0.65 ▼]  [LLM disagree ▼]  🔍     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Pair #47  │  Score: 0.62  │  LLM: match (0.71)       │  │
│  ├─────────────────────┬──────────────────────────────────┤  │
│  │  Record A           │  Record B                        │  │
│  ├─────────────────────┼──────────────────────────────────┤  │
│  │  Name: Acme Corp    │  Name: ACME Corporation         │  │
│  │  Addr: 123 Main St  │  Addr: 123 Main Street, Ste 4   │  │
│  │  City: Springfield  │  City: Springfield               │  │
│  │  Phone: 555-0123    │  Phone: (555) 012-3456           │  │
│  │  Email: info@acme   │  Email: —                        │  │
│  ├─────────────────────┴──────────────────────────────────┤  │
│  │  Field Scores:                                         │  │
│  │  name  ████████░░ 0.82   addr ██████░░░░ 0.64          │  │
│  │  phone ████░░░░░░ 0.41   email ░░░░░░░░░ N/A           │  │
│  ├────────────────────────────────────────────────────────┤  │
│  │  LLM Reasoning: "Company names are clearly the same    │  │
│  │  entity with different formatting. Address differs by   │  │
│  │  suite number which suggests same building..."          │  │
│  ├────────────────────────────────────────────────────────┤  │
│  │         [ ✓ Match ]    [ ✗ Not Match ]    [ Skip ]     │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Pair #46  │  Score: 0.58  │  LLM: no_match (0.55)    │  │
│  │  ...                                                   │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

**Key interactions:**
- **Match / Not Match** calls `POST /api/review/{collection}/pair/{key_a}/{key_b}/verdict` → `AdaptiveLLMVerifier.record_human_correction()`
- **Field diff highlighting** — fields with low similarity scores are highlighted in amber/red; exact matches in green
- **LLM reasoning** — if the pair was previously verified by LLM, show its reasoning to help the human decide
- **Keyboard shortcuts** — `M` for match, `N` for not match, `S` for skip, arrow keys to navigate
- **Threshold banner** — shows current low/high thresholds with "Optimize" button that triggers `optimize_thresholds()`
- **Bulk actions** — select multiple pairs and approve/reject in batch

**Data sources:** `FeedbackStore.all_verdicts()` (filtered to pending/uncertain), `explain_match` for field-level breakdown, document lookups for full record display.

---

### 3. Cluster Browser

Browse entity clusters with quality scores, drill into member records, and visualize the similarity graph.

**List View:**
```
┌──────────────────────────────────────────────────────────────┐
│  Clusters — companies                   890 total clusters   │
├──────────────────────────────────────────────────────────────┤
│  Sort: [Quality ▼]  Filter: [Size ≥ 3 ▼]  🔍 Search        │
├──────────────────────────────────────────────────────────────┤
│  ┌────────┬────────┬─────────┬──────────┬─────────┬───────┐ │
│  │ ID     │ Size   │ Quality │ Avg Sim  │ Density │ View  │ │
│  ├────────┼────────┼─────────┼──────────┼─────────┼───────┤ │
│  │ c_001  │ 5      │ 0.94    │ 0.89     │ 0.80    │  →    │ │
│  │ c_002  │ 3      │ 0.91    │ 0.85     │ 1.00    │  →    │ │
│  │ c_003  │ 8      │ 0.67    │ 0.72     │ 0.43    │  ⚠→   │ │
│  │ ...    │        │         │          │         │       │ │
│  └────────┴────────┴─────────┴──────────┴─────────┴───────┘ │
│                                                              │
│  Showing 1-20 of 890          [← Prev]  [Next →]            │
└──────────────────────────────────────────────────────────────┘
```

**Detail View (drill-down):**
```
┌──────────────────────────────────────────────────────────────┐
│  Cluster c_001  │  5 members  │  Quality: 0.94              │
├────────────────────────────┬─────────────────────────────────┤
│  Members                   │  Cluster Graph                  │
│                            │                                 │
│  ┌──────────────────────┐  │      (A)───0.92───(B)          │
│  │ A: Acme Corp         │  │       │  ╲         │           │
│  │    123 Main St       │  │      0.89  0.85  0.91          │
│  │    Source: CRM       │  │       │      ╲     │           │
│  ├──────────────────────┤  │      (C)───0.88──(D)           │
│  │ B: ACME Corporation  │  │              │                  │
│  │    123 Main St #4    │  │            0.78                 │
│  │    Source: ERP        │  │              │                  │
│  ├──────────────────────┤  │             (E)                 │
│  │ C: Acme Corp Inc     │  │                                 │
│  │    123 Main Street   │  │  Edge weights = similarity      │
│  │    Source: Compliance │  │  Node color = source system     │
│  ├──────────────────────┤  │                                 │
│  │ D: ACME Corp.        │  │                                 │
│  │    124 Main St       │  │                                 │
│  │    Source: Vendors    │  │                                 │
│  ├──────────────────────┤  │                                 │
│  │ E: Acme              │  │                                 │
│  │    Springfield, IL   │  │                                 │
│  │    Source: Sales      │  │                                 │
│  └──────────────────────┘  │                                 │
│                            │                                 │
│  [View Golden Record]  [Explain Edge]  [Split Cluster]      │
└────────────────────────────┴─────────────────────────────────┘
```

**Key interactions:**
- **Click any edge** → calls `explain_match` and shows field-level similarity breakdown in a modal
- **View Golden Record** → calls `merge_entities` preview and shows the fused record with field provenance
- **Split Cluster** (future) → manual override to separate incorrectly grouped records
- **Color-coding** — nodes colored by source system, edges colored by similarity strength (green ≥ 0.80, amber 0.55–0.80, red < 0.55)
- **Low-quality warning** — clusters with `quality_score` below threshold show a warning icon with explanation

**Data sources:** `get_clusters` for list, `arango://clusters/{collection}/{key}` for detail, direct AQL for edge data to build the graph.

---

### 4. Pipeline Runner

Configure and execute pipeline runs with live progress tracking.

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│  Run Pipeline                                                │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Collection: [companies ▼]    Config: [Upload YAML] or      │
│                                       [Build Config →]       │
│                                                              │
│  ┌─ Pipeline Progress ──────────────────────────────────┐   │
│  │                                                       │   │
│  │  ● Blocking        ████████████████████  Done (2.1s)  │   │
│  │    → 12,450 candidates from 500K pairs (97.5% reduction)  │
│  │                                                       │   │
│  │  ● Similarity      ████████████░░░░░░░░  67% (4.2s)  │   │
│  │    → 2,100 / 3,200 edges created                      │   │
│  │                                                       │   │
│  │  ○ LLM Curation    ░░░░░░░░░░░░░░░░░░░  Waiting      │   │
│  │                                                       │   │
│  │  ○ Clustering      ░░░░░░░░░░░░░░░░░░░  Waiting      │   │
│  │                                                       │   │
│  │  ○ Golden Records  ░░░░░░░░░░░░░░░░░░░  Waiting      │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  [Cancel Run]                                                │
└──────────────────────────────────────────────────────────────┘
```

**After completion**, the progress section transitions to a results summary with links:
- "View 890 clusters →" links to Cluster Browser
- "47 pairs need review →" links to Review Queue
- "Export results" triggers `ClusterExportService`

**Data sources:** `ConfigurableERPipeline.run()` with progress callbacks streamed over WebSocket.

---

### 5. Config Builder

A guided, visual alternative to writing YAML. Organized into pipeline stages that mirror the config schema.

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│  Pipeline Config Builder                                     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─ 1. Collection ──────────────────────────────────────┐   │
│  │  Entity Type: [company ▼]                             │   │
│  │  Collection:  [companies ▼]  (12,450 docs)            │   │
│  │  [Profile Dataset] → shows field stats inline         │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─ 2. Blocking ────────────────────────────────────────┐   │
│  │  Strategy: [BM25 ▼]                                   │   │
│  │  Fields:   [+ Add Field]                              │   │
│  │    name (weight: 0.40) [×]                            │   │
│  │    address (weight: 0.30) [×]                         │   │
│  │  Max Block Size: [1000]                               │   │
│  │  [Get Recommendations] → calls advisor tools          │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─ 3. Similarity ──────────────────────────────────────┐   │
│  │  Algorithm: [Jaro-Winkler ▼]                          │   │
│  │  Threshold: ──────●────── 0.80                        │   │
│  │  Field Weights:                                       │   │
│  │    name     ──────────●── 0.40                        │   │
│  │    address  ────────●──── 0.30                        │   │
│  │    phone    ──────●────── 0.20                        │   │
│  │    email    ────●──────── 0.10                        │   │
│  │  [Estimate Weights from Labels]                       │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─ 4. Clustering ──────────────────────────────────────┐   │
│  │  Backend: [auto ▼]     Min Cluster Size: [2]          │   │
│  │  Store Results: [✓]                                   │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─ 5. LLM Curation (optional) ────────────────────────┐   │
│  │  [✓] Enable     Provider: [ollama ▼]                  │   │
│  │  Model: [llama3.1:8b]    Low: [0.55]  High: [0.80]   │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  [Validate]  [Simulate Variants]  [Export YAML]  [Run →]    │
└──────────────────────────────────────────────────────────────┘
```

**Key interactions:**
- **Profile Dataset** calls the `profile_dataset` advisor tool and shows field quality inline
- **Get Recommendations** calls `recommend_blocking_candidates` and `recommend_resolution_strategy` and presents options
- **Estimate Weights** calls `estimate_feature_weights` if labeled data is available
- **Simulate Variants** calls `simulate_pipeline_variants` to compare the current config against alternatives
- **Validate** calls `ERPipelineConfig.validate()` and highlights errors
- **Export YAML** calls `export_recommended_config` and offers download
- **Run** navigates to Pipeline Runner with the config pre-loaded

---

### 6. Entity Resolver (Interactive)

A "try it now" screen for testing single-record resolution without running a full pipeline.

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│  Resolve Entity                                              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Collection: [companies ▼]                                   │
│                                                              │
│  ┌─ Input Record ───────────────────────────────────────┐   │
│  │  Name:    [                                        ] │   │
│  │  Address: [                                        ] │   │
│  │  City:    [                    ]  State: [        ] │   │
│  │  Phone:   [                    ]                     │   │
│  │  Email:   [                                        ] │   │
│  │                                        [Resolve →]   │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─ Matches (3 found) ─────────────────────────────────┐   │
│  │  #1  Score: 0.94  │  Acme Corporation               │   │
│  │      123 Main St, Springfield IL                     │   │
│  │      [View Detail] [Explain Match]                   │   │
│  │                                                       │   │
│  │  #2  Score: 0.78  │  Acme Holdings LLC               │   │
│  │      456 Oak Ave, Springfield IL                      │   │
│  │      [View Detail] [Explain Match]                   │   │
│  │                                                       │   │
│  │  #3  Score: 0.61  │  Acme Industries                 │   │
│  │      789 Pine Rd, Shelbyville IL                     │   │
│  │      [View Detail] [Explain Match]                   │   │
│  └───────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

**Data sources:** `resolve_entity` (MCP) for matching, `explain_match` (MCP) for field-level detail.

---

### 7. Golden Record Manager

View and manage golden records, resolve field-level conflicts.

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│  Golden Record — Acme Corporation (c_001)                    │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─ Merged Fields ─────────────────────────────────────┐    │
│  │  Field     │ Value              │ Source     │ Conf. │    │
│  ├───────────┼────────────────────┼────────────┼───────┤    │
│  │  Name      │ Acme Corporation   │ Compliance │ 1.00  │    │
│  │  Address   │ 123 Main St        │ CRM        │ 0.95  │    │
│  │  City      │ Springfield        │ (consensus)│ 1.00  │    │
│  │  State     │ IL                 │ (consensus)│ 1.00  │    │
│  │  Phone     │ 555-0123       ⚠  │ CRM        │ 0.70  │    │
│  │  Email     │ info@acme.com      │ Sales      │ 0.90  │    │
│  └───────────┴────────────────────┴────────────┴───────┘    │
│                                                              │
│  ⚠ Phone: Conflict between sources                          │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  CRM:        555-0123        (updated 2026-03-15)      │  │
│  │  ERP:        555-012-3456    (updated 2026-02-28)      │  │
│  │  Vendors:    (555) 012-3456  (updated 2025-11-01)      │  │
│  │                                                        │  │
│  │  [Use CRM]  [Use ERP]  [Manual Override: [_________]] │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ Source Records (5) ────────────────────────────────┐    │
│  │  Source      │ Record Key  │ Ingested   │ Confidence │    │
│  │  CRM         │ CRM-12345   │ 2026-03-15 │ 0.94       │    │
│  │  ERP         │ ERP-67890   │ 2026-02-28 │ 0.91       │    │
│  │  Compliance  │ KYC-11111   │ 2026-01-10 │ 0.89       │    │
│  │  Vendors     │ VND-22222   │ 2025-11-01 │ 0.85       │    │
│  │  Sales       │ SLS-33333   │ 2025-09-20 │ 0.78       │    │
│  └─────────────┴─────────────┴────────────┴────────────┘    │
│                                                              │
│  Strategy: [most_complete ▼]  [Re-merge]  [Export]          │
└──────────────────────────────────────────────────────────────┘
```

**Data sources:** `merge_entities` (MCP) for preview/merge, direct ArangoDB lookups for source records and provenance.

---

## Navigation Structure

```
┌─────────────┐
│  Sidebar     │
│              │
│  📊 Dashboard│ ← Home / overview
│  📋 Review   │ ← Review queue (badge: pending count)
│  🔗 Clusters │ ← Cluster browser
│  ▶️ Pipeline  │ ← Run / monitor
│  🏆 Golden   │ ← Golden records
│  🔍 Resolve  │ ← Interactive resolver
│  ⚙️ Config   │ ← Config builder
│  📤 Export   │ ← Export center
│              │
│  ─────────── │
│  Collection: │
│  [companies▼]│ ← Global collection selector
└─────────────┘
```

The sidebar's **collection selector** is global — changing it updates all screens. The **Review** item shows a badge with the pending review count.

---

## API-to-Service Mapping

Every backend endpoint maps directly to existing library code. No new resolution logic is introduced.

| Backend Route | Library Entry Point | New Code Required |
|---------------|--------------------|--------------------|
| `GET /api/collections` | `list_collections` handler in `mcp/tools/entity.py` | Thin FastAPI wrapper |
| `GET /api/collections/{name}/profile` | `profile_dataset` handler in `mcp/tools/advisor.py` | Thin FastAPI wrapper |
| `POST /api/pipeline/run` | `ConfigurableERPipeline.run()` in `core/configurable_pipeline.py` | Progress callback hooks |
| `GET /api/pipeline/status/{collection}` | `pipeline_status` handler in `mcp/tools/entity.py` | Thin FastAPI wrapper |
| `GET /api/clusters/{collection}` | `get_clusters` handler in `mcp/tools/entity.py` | Thin FastAPI wrapper |
| `GET /api/clusters/{collection}/{key}` | `arango://clusters` resource in `mcp/resources/collections.py` | Thin FastAPI wrapper |
| `GET /api/clusters/{collection}/{key}/graph` | Direct AQL to query similarity edges | ~20 lines AQL |
| `GET /api/review/{collection}` | `FeedbackStore.all_verdicts()` in `reasoning/feedback.py` | Filter/sort wrapper |
| `POST /api/review/.../verdict` | `AdaptiveLLMVerifier.record_human_correction()` in `reasoning/feedback.py` | Thin FastAPI wrapper |
| `POST /api/review/.../optimize` | `AdaptiveLLMVerifier.optimize_thresholds()` | Thin FastAPI wrapper |
| `POST /api/golden/{collection}/preview` | `merge_entities` handler in `mcp/tools/entity.py` | Thin FastAPI wrapper |
| `POST /api/resolve/{collection}` | `resolve_entity` handler in `mcp/tools/entity.py` | Thin FastAPI wrapper |
| `POST /api/config/validate` | `ERPipelineConfig.validate()` in `config/er_config.py` | Thin FastAPI wrapper |
| `POST /api/config/recommend` | `recommend_resolution_strategy` in `mcp/tools/advisor.py` | Thin FastAPI wrapper |
| `POST /api/config/simulate` | `simulate_pipeline_variants` in `mcp/tools/advisor.py` | Thin FastAPI wrapper |
| `POST /api/config/export` | `export_recommended_config` in `mcp/tools/advisor.py` | Thin FastAPI wrapper |
| `POST /api/export/{collection}` | `ClusterExportService.export()` in `services/cluster_export_service.py` | Thin FastAPI wrapper |

**New code required in the core library:**
1. **Progress callbacks** in `ConfigurableERPipeline.run()` — optional `on_progress` parameter
2. **Pipeline run history** — store run metadata in an `_er_pipeline_runs` collection
3. **Cluster graph query** — AQL to return nodes + edges for a given cluster (for visualization)
4. **Review queue filtering** — extend `FeedbackStore` with filter/sort/pagination helpers

All four are small, backward-compatible additions.

---

## Implementation Phases

### Phase 1: Foundation + Review Queue (4–6 weeks)

**Goal:** Ship the highest-value screen (Review Queue) with the minimal backend infrastructure.

**Backend:**
- FastAPI app factory with ArangoDB connection management
- Routes: `/api/collections`, `/api/review/*`, `/api/clusters/{collection}` (list only)
- `arango-er ui` CLI command
- Static asset serving for production builds

**Frontend:**
- React app scaffold with routing, layout shell, sidebar navigation
- Review Queue screen (pair comparison, field diff, verdict submission)
- Cluster list screen (table with quality scores, pagination)
- Dashboard screen (summary stats)

**Library changes:**
- Add `FeedbackStore` filter/sort/pagination helpers
- Add `ui` optional extra to `pyproject.toml` (FastAPI, uvicorn)

**Deliverables:**
- `pip install "arango-entity-resolution[ui]"` works
- `arango-er ui` launches the app
- Analysts can review ambiguous pairs and submit verdicts
- Cluster list is browsable with quality indicators

### Phase 2: Cluster Detail + Pipeline Runner (3–4 weeks)

**Goal:** Add cluster drill-down with graph visualization and live pipeline execution.

**Backend:**
- Routes: `/api/clusters/{collection}/{key}`, `/api/clusters/{collection}/{key}/graph`
- Routes: `/api/pipeline/run`, `/ws/pipeline/{run_id}`
- Pipeline progress callback hooks

**Frontend:**
- Cluster detail screen with member list and interactive graph (React Flow)
- Explain Match modal (field-level similarity breakdown)
- Pipeline Runner screen with WebSocket-driven progress bars
- Pipeline history on dashboard

**Library changes:**
- Add `on_progress` callback parameter to `ConfigurableERPipeline.run()`
- Add pipeline run history storage

### Phase 3: Golden Records + Config Builder (3–4 weeks)

**Goal:** Complete the golden record management and config building workflows.

**Backend:**
- Routes: `/api/golden/*`, `/api/config/*`, `/api/resolve/*`, `/api/export/*`

**Frontend:**
- Golden Record view with conflict resolution UI
- Config Builder with advisor tool integration
- Entity Resolver (interactive resolution)
- Export center

**Library changes:**
- None — all services already exist

### Phase 4: Polish + Centralized Service Prep (2–3 weeks)

**Goal:** Production hardening and groundwork for centralized service admin UI.

- Authentication/authorization hooks (pluggable — JWT, API key, or none for local use)
- Role-based access (viewer, reviewer, admin)
- Keyboard navigation and accessibility
- Responsive layout for smaller screens
- Dark mode
- Tenant management screen (stub for v4.x)
- Performance optimization (virtualized lists, lazy loading, request deduplication)

---

## Packaging and Distribution

### PyPI Extra

```toml
[project.optional-dependencies]
ui = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "websockets>=12.0",
]
```

The built React assets are included in the sdist/wheel under `src/entity_resolution/ui/static/`. The `ui/` frontend source directory is excluded from the published package (listed in `MANIFEST.in` exclude).

### Build Pipeline

```bash
# Development
cd ui && npm install && npm run dev     # Vite dev server on :5173
arango-er ui --dev                      # FastAPI on :8787, proxies to :5173

# Production build
cd ui && npm run build                  # Outputs to src/entity_resolution/ui/static/
pip install -e ".[ui]"                  # Install with UI extra
arango-er ui                            # Serves bundled assets on :8787

# CI
npm run build && python -m build        # Build wheel with assets included
```

### Docker

```dockerfile
FROM python:3.12-slim
RUN pip install "arango-entity-resolution[ui,mcp,llm,ml]"
EXPOSE 8787
CMD ["arango-er", "ui", "--host", "0.0.0.0"]
```

---

## Security Considerations

- **No default authentication** — the UI is intended for local or internal network use, matching the current CLI/MCP model. Authentication is opt-in via a pluggable auth backend.
- **AQL injection prevention** — all database queries use bind variables (consistent with existing library practice).
- **CORS** — restrictive by default (same-origin only); configurable for remote deployments.
- **No PII logging** — record content is never logged by the backend; only aggregate stats appear in server logs.
- **Read-only mode** — a `--readonly` flag disables all mutation endpoints (review verdicts, pipeline runs, merges), useful for demo or monitoring deployments.

---

## Relationship to Existing Architecture

This proposal follows the **roadmap principle** from the PRD:

> Future additions should extend the current pipeline, CLI, MCP, and reporting surfaces rather than creating parallel systems.

The UI backend calls the same Python functions as the MCP server and CLI. The three interfaces share a common service layer:

```
┌─────────┐  ┌─────────┐  ┌──────────┐
│  CLI    │  │  MCP    │  │  Web UI  │
│ (click) │  │(FastMCP)│  │(FastAPI) │
└────┬────┘  └────┬────┘  └────┬─────┘
     │            │            │
     └────────────┼────────────┘
                  │
     ┌────────────┴────────────┐
     │    Services Layer       │
     │  (Pipeline, Clustering, │
     │   Feedback, Export, ...) │
     └────────────┬────────────┘
                  │
     ┌────────────┴────────────┐
     │      ArangoDB           │
     └─────────────────────────┘
```

No new resolution logic. No parallel data paths. The UI is a presentation layer.

---

## Success Criteria

The UI is successful when:

1. **Review throughput** — a non-developer analyst can review 50+ ambiguous pairs per hour through the Review Queue
2. **Cluster comprehension** — users can identify and explain cluster membership through the visual graph in under 30 seconds per cluster
3. **Zero new dependencies for core users** — `pip install arango-entity-resolution` (without `[ui]`) remains unchanged
4. **Pipeline execution** — users can configure, run, and monitor a pipeline without touching YAML or CLI
5. **Golden record trust** — field-level provenance and conflict resolution are visible and actionable
6. **Same results** — the UI produces identical resolution outcomes to CLI and MCP because it calls the same code

---

## Open Questions

1. **HTMX vs React?** — HTMX would eliminate the Node.js build step entirely and keep the stack pure Python. Trade-off: less interactive graph visualization, harder to build the config builder's drag-and-drop. Recommendation: React for the cluster graph and config builder value, with the understanding that it adds a frontend build step.

2. **Separate repository?** — Keeping the UI in-repo simplifies versioning (UI version always matches library version) and development (single PR for backend + frontend changes). A separate repo would be warranted only if the UI team and library team diverge significantly.

3. **ArangoDB Graph Visualizer integration?** — The library already has a skill for customizing the ArangoDB Graph Visualizer. Should the cluster detail view link out to the visualizer for advanced graph exploration, or replicate it? Recommendation: link to it as an "Advanced View" option, don't replicate.

4. **Mobile / tablet support?** — The review queue is a strong candidate for tablet use (reviewing pairs on-the-go). Should Phase 1 include responsive layout? Recommendation: defer to Phase 4 unless there's immediate demand.

---

## Related Documents

- [System Design](DESIGN.md) — current architecture
- [PRD](../PRD.md) — product requirements and roadmap
- [Centralized ER Service](CENTRALIZED_ER_SERVICE.md) — v4.x service design
- [API Reference](../api/API_REFERENCE.md) — CLI, MCP, and Python API
- [Advanced Modules Guide](../guides/ADVANCED_MODULES_GUIDE.md) — LLM verifier, feedback, active learning

---

**Last Updated:** April 13, 2026
