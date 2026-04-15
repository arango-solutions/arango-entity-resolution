# UI Implementation — Multi-Subagent Execution Plan

**Reference:** [Entity Resolution UI Design](../architecture/ENTITY_RESOLUTION_UI.md)

This plan implements the UI in three waves of parallel subagents with strict file partitioning. Each subagent owns a non-overlapping set of files. No two subagents write to the same file.

---

## Wave 1 — Foundation (3 parallel subagents, no dependencies)

These three subagents run concurrently. They create the backend skeleton, frontend scaffold, and core library additions that all subsequent waves depend on.

---

### Subagent W1-A: Backend Foundation

**Owns:** `src/entity_resolution/ui/` (all files), `pyproject.toml`, `src/entity_resolution/cli.py` (add `ui` command only)

```
Create the FastAPI backend skeleton for the entity resolution UI.

CONTEXT:
The entity resolution library (v3.5.1) has Python services, a Click CLI (`arango-er`),
and an MCP server (`arango-er-mcp`). We are adding an optional web UI shipped as
`pip install "arango-entity-resolution[ui]"` and launched with `arango-er ui`.

The design doc is at docs/architecture/ENTITY_RESOLUTION_UI.md — read it first.

YOUR FILES (you may ONLY create/modify these):
- src/entity_resolution/ui/__init__.py
- src/entity_resolution/ui/app.py
- src/entity_resolution/ui/routes/__init__.py
- src/entity_resolution/ui/routes/collections.py
- src/entity_resolution/ui/routes/clusters.py
- src/entity_resolution/ui/routes/review.py
- src/entity_resolution/ui/routes/pipeline.py
- src/entity_resolution/ui/routes/golden.py
- src/entity_resolution/ui/routes/config.py
- src/entity_resolution/ui/routes/resolve.py
- src/entity_resolution/ui/routes/export.py
- src/entity_resolution/ui/routes/ws.py
- src/entity_resolution/ui/models/__init__.py
- src/entity_resolution/ui/models/schemas.py
- pyproject.toml (add "ui" optional extra and script entry point ONLY)
- src/entity_resolution/cli.py (add "ui" command ONLY — do not modify existing commands)

TASKS:

1. Read pyproject.toml and understand the existing extras and scripts.
   Add a `ui` optional extra:
   ```toml
   ui = [
       "fastapi>=0.115",
       "uvicorn[standard]>=0.34",
       "websockets>=14.0",
   ]
   ```
   Do NOT change any existing extras or dependencies.

2. Create src/entity_resolution/ui/app.py — FastAPI application factory:
   - `create_app(db, readonly=False) -> FastAPI` function
   - Accepts a python-arango database handle (same as MCP server and CLI use)
   - Mounts all route modules as APIRouter instances under `/api/`
   - Serves static files from `ui/static/` directory (for production builds)
   - If static/index.html exists, adds a catch-all route to serve it (SPA fallback)
   - CORS middleware: same-origin by default, configurable via `allowed_origins` param
   - If `readonly=True`, exclude mutation routes (review verdicts, pipeline run, merges)
   - Add a `/api/health` endpoint that returns {"status": "ok", "version": <library version>}

3. Create route modules. Each route file:
   - Creates an `APIRouter(prefix="/api/<domain>", tags=["<domain>"])`
   - Defines Pydantic request/response models in schemas.py
   - Calls existing library services — import and call the SAME functions that
     the MCP tools use. Do NOT duplicate logic.

   Route modules to create (with their endpoints):

   collections.py:
   - GET /api/collections — wraps list_collections logic from mcp/tools/entity.py
   - GET /api/collections/{name}/profile — wraps profile_dataset from mcp/tools/advisor.py
   - GET /api/collections/{name}/sample — wraps collection summary resource logic

   clusters.py:
   - GET /api/clusters/{collection} — wraps get_clusters, add limit/offset/min_size params
   - GET /api/clusters/{collection}/stats — wraps WCCClusteringService.get_statistics()
   - GET /api/clusters/{collection}/{key} — cluster detail with member documents
   - GET /api/clusters/{collection}/{key}/graph — returns {nodes: [...], edges: [...]}
     for React Flow visualization. Query similarity edges for the cluster members.

   review.py:
   - GET /api/review/{collection} — list verdicts from FeedbackStore, filterable
     by status (pending/match/no_match), score range, sortable by score
   - GET /api/review/{collection}/stats — verdict counts by decision
   - GET /api/review/{collection}/pair/{key_a}/{key_b} — full pair comparison
     using explain_match logic + document lookup
   - POST /api/review/{collection}/pair/{key_a}/{key_b}/verdict — accept
     {decision: "match"|"no_match", confidence?: float, notes?: string}
     and call FeedbackStore.record_human_correction()
   - POST /api/review/{collection}/optimize — trigger threshold optimization
   - GET /api/review/{collection}/thresholds — current low/high thresholds

   pipeline.py:
   - GET /api/pipeline/status/{collection} — wraps pipeline_status MCP tool
   - GET /api/pipeline/history — query _er_pipeline_runs collection
   - POST /api/pipeline/run — accepts ERPipelineConfig as JSON, runs pipeline
     in background task, returns run_id

   ws.py:
   - WS /ws/pipeline/{run_id} — WebSocket that streams pipeline progress events
     as JSON messages (stage_start, stage_progress, stage_complete, pipeline_complete)

   golden.py:
   - POST /api/golden/{collection}/preview — wraps merge_entities MCP tool
   - POST /api/golden/{collection}/merge — wraps GoldenRecordService
   - GET /api/golden/{collection}/{entity_key} — direct document lookup
   - GET /api/golden/{collection}/{entity_key}/provenance — source records

   config.py:
   - POST /api/config/validate — wraps ERPipelineConfig.validate()
   - POST /api/config/recommend — wraps recommend_resolution_strategy
   - POST /api/config/blocking — wraps recommend_blocking_candidates
   - POST /api/config/simulate — wraps simulate_pipeline_variants
   - POST /api/config/export — wraps export_recommended_config

   resolve.py:
   - POST /api/resolve/{collection} — wraps resolve_entity MCP tool
   - POST /api/resolve/cross — wraps resolve_entity_cross_collection

   export.py:
   - POST /api/export/{collection} — wraps ClusterExportService.export()
   - GET /api/export/{collection}/download/{filename} — serve exported file

4. Create schemas.py with Pydantic models for:
   - VerdictRequest, VerdictResponse
   - ClusterListResponse, ClusterDetailResponse, ClusterGraphResponse
   - PipelineRunRequest, PipelineRunResponse, PipelineStatusResponse
   - ReviewPairResponse, ReviewStatsResponse
   - GoldenRecordPreviewRequest, GoldenRecordResponse
   - ResolveRequest, ResolveResponse
   - ConfigValidateRequest, ConfigValidateResponse
   - CollectionInfo, CollectionProfileResponse

5. Add `ui` command to cli.py:
   - Add at the END of the file (do not modify any existing commands)
   - Uses the same @connection_options decorator as other commands
   - Options: --port (default 8787), --host (default 127.0.0.1), --open (auto-open browser),
     --dev (enable CORS for localhost:5173), --readonly
   - Imports conditionally: try/except ImportError with helpful message about pip install [ui]
   - Starts uvicorn with the FastAPI app

ACCEPTANCE CRITERIA:
- [ ] `pip install -e ".[ui]"` installs fastapi + uvicorn without touching other extras
- [ ] `arango-er ui --help` shows the new command with all options
- [ ] `arango-er --help` still shows all existing commands unchanged
- [ ] All route modules have proper APIRouter setup and endpoint stubs
- [ ] All endpoints call existing library services — NO duplicated resolution logic
- [ ] schemas.py has typed Pydantic models for all request/response shapes
- [ ] app.py serves static files when they exist, returns API responses when they don't
- [ ] /api/health returns version and status
- [ ] No linter errors in any new files
```

---

### Subagent W1-B: Frontend Scaffold

**Owns:** `ui/` (entire directory — this is a new directory at the repo root)

```
Create the React + TypeScript frontend scaffold for the entity resolution UI.

CONTEXT:
The entity resolution library is adding a web UI. The backend (FastAPI) is being built
in parallel by another subagent at src/entity_resolution/ui/. Your job is the frontend.

The design doc is at docs/architecture/ENTITY_RESOLUTION_UI.md — read it for screen
layouts, navigation structure, and technology choices.

YOUR FILES (you may ONLY create files under):
- ui/ (entire directory — this is NEW, at the repo root next to src/)

DO NOT modify any Python files, pyproject.toml, or anything under src/.

TASKS:

1. Initialize a Vite + React + TypeScript project in ui/:
   ```
   ui/
   ├── package.json
   ├── tsconfig.json
   ├── tsconfig.app.json
   ├── tsconfig.node.json
   ├── vite.config.ts
   ├── tailwind.config.ts
   ├── postcss.config.js
   ├── index.html
   ├── public/
   └── src/
   ```

   In package.json, include these dependencies:
   - react, react-dom (v19)
   - react-router-dom (v7)
   - @tanstack/react-query (v5)
   - recharts (v2)
   - @xyflow/react (React Flow v12 — for cluster graph visualization)
   - tailwindcss, postcss, autoprefixer
   - clsx, tailwind-merge (utility for conditional classes)
   - lucide-react (icon library)

   Dev dependencies:
   - typescript, @types/react, @types/react-dom
   - vite, @vitejs/plugin-react
   - eslint, prettier (standard configs)

   In vite.config.ts:
   - Proxy /api/* and /ws/* to http://localhost:8787 during development
   - Output build to ../src/entity_resolution/ui/static/ so the Python package serves it

2. Create the application shell and routing:

   src/main.tsx — entry point, renders App with QueryClientProvider and BrowserRouter
   src/App.tsx — layout with sidebar + main content area using react-router-dom Outlet

   src/pages/ — one page component per screen:
   - DashboardPage.tsx
   - ReviewPage.tsx
   - ClustersPage.tsx
   - ClusterDetailPage.tsx (route: /clusters/:collection/:key)
   - PipelinePage.tsx
   - GoldenRecordsPage.tsx
   - GoldenRecordDetailPage.tsx (route: /golden/:collection/:key)
   - ResolvePage.tsx
   - ConfigPage.tsx
   - ExportPage.tsx

3. Create the layout components:

   src/components/layout/Sidebar.tsx:
   - Navigation items: Dashboard, Review (with badge), Clusters, Pipeline, Golden Records,
     Resolve, Config, Export
   - Global collection selector dropdown at the bottom
   - Uses lucide-react icons
   - Highlight active route
   - Collapsible on small screens

   src/components/layout/AppShell.tsx:
   - Sidebar + main content area
   - Header bar with breadcrumb and collection indicator

4. Create shared/reusable components:

   src/components/shared/DataTable.tsx — generic table with sorting, pagination
   src/components/shared/ScoreBadge.tsx — color-coded similarity score display
     (green ≥ 0.80, amber 0.55–0.80, red < 0.55)
   src/components/shared/FieldDiff.tsx — side-by-side field comparison with highlighting
   src/components/shared/SearchBar.tsx — filterable search input
   src/components/shared/StatCard.tsx — numeric stat with label (for dashboard)
   src/components/shared/LoadingSpinner.tsx — centered loading indicator
   src/components/shared/EmptyState.tsx — placeholder for empty data
   src/components/shared/ErrorBoundary.tsx — catches render errors gracefully
   src/components/shared/Badge.tsx — simple pill badge with variant colors

5. Create the API client layer:

   src/api/client.ts — base fetch wrapper with error handling
   src/api/collections.ts — getCollections(), getCollectionProfile(name), getCollectionSample(name)
   src/api/clusters.ts — getClusters(collection, params), getClusterDetail(collection, key),
     getClusterGraph(collection, key), getClusterStats(collection)
   src/api/review.ts — getReviewQueue(collection, filters), getReviewStats(collection),
     getReviewPair(collection, keyA, keyB), submitVerdict(collection, keyA, keyB, verdict),
     optimizeThresholds(collection), getThresholds(collection)
   src/api/pipeline.ts — getPipelineStatus(collection), getPipelineHistory(),
     runPipeline(config), connectPipelineWs(runId)
   src/api/golden.ts — previewGoldenRecord(collection, keys, strategy),
     mergeGoldenRecord(collection, keys, strategy), getGoldenRecord(collection, key),
     getProvenance(collection, key)
   src/api/resolve.ts — resolveEntity(collection, record, fields),
     resolveEntityCross(sourceCollection, targetCollection, fields)
   src/api/config.ts — validateConfig(config), recommendStrategy(profile),
     recommendBlocking(profile), simulateVariants(variants), exportConfig(recommendation, format)
   src/api/export.ts — exportClusters(collection, options), downloadExport(collection, filename)

6. Create React Query hooks:

   src/hooks/useCollections.ts — useCollections(), useCollectionProfile(name)
   src/hooks/useClusters.ts — useClusters(collection), useClusterDetail(collection, key),
     useClusterGraph(collection, key)
   src/hooks/useReview.ts — useReviewQueue(collection, filters), useReviewStats(collection),
     useSubmitVerdict()
   src/hooks/usePipeline.ts — usePipelineStatus(collection), usePipelineHistory()
   src/hooks/useCollection.ts — global collection state (context provider)

7. Create the global collection context:

   src/contexts/CollectionContext.tsx — provides selectedCollection, setSelectedCollection
   to the entire app. Persists to localStorage.

8. Implement the Dashboard page (first real screen):

   DashboardPage.tsx:
   - 4 StatCards at top: Documents, Clusters, Pending Reviews, Avg Quality Score
   - Cluster size distribution histogram (Recharts BarChart)
   - Similarity score distribution histogram (Recharts BarChart)
   - Recent pipeline runs table
   - All data fetched via React Query hooks

9. Create a basic global CSS:

   src/index.css — Tailwind directives (@tailwind base/components/utilities)
   Define a clean color palette suitable for a data-oriented application.
   Light theme only for now (dark mode is Phase 4).

ACCEPTANCE CRITERIA:
- [ ] `cd ui && npm install && npm run dev` starts Vite on :5173 without errors
- [ ] `npm run build` outputs to ../src/entity_resolution/ui/static/ successfully
- [ ] Browser shows the app shell with sidebar navigation and collection selector
- [ ] Dashboard page renders with placeholder/loading states for all 4 stat cards
- [ ] All routes navigate correctly (sidebar links → page components)
- [ ] API client functions exist for all backend endpoints
- [ ] React Query hooks exist for all data-fetching use cases
- [ ] Collection context persists selected collection across page navigation
- [ ] No TypeScript errors (`npm run typecheck` passes)
- [ ] All shared components (DataTable, ScoreBadge, FieldDiff, etc.) render correctly
- [ ] Vite proxy config routes /api/* to :8787
```

---

### Subagent W1-C: Core Library Additions

**Owns:** `src/entity_resolution/reasoning/feedback.py` (add methods only), `src/entity_resolution/core/configurable_pipeline.py` (add `on_progress` param only), `tests/test_ui_core_additions.py` (new)

```
Add 4 small backward-compatible features to the entity resolution core library
that the UI backend needs. Do NOT create any UI or FastAPI code.

CONTEXT:
The entity resolution library is adding a web UI. The UI backend needs a few
small extensions to existing services. Your job is to add these extensions
without breaking any existing behavior.

YOUR FILES (you may ONLY modify/create these):
- src/entity_resolution/reasoning/feedback.py (ADD methods to FeedbackStore, do not remove/rename anything)
- src/entity_resolution/core/configurable_pipeline.py (ADD on_progress parameter, do not change existing behavior)
- tests/test_ui_core_additions.py (NEW — tests for your changes)

DO NOT modify cli.py, pyproject.toml, any MCP files, or create any files under ui/.

TASKS:

1. Read src/entity_resolution/reasoning/feedback.py thoroughly. Understand FeedbackStore,
   its save(), record_human_correction(), all_verdicts(), stats() methods.

2. Add these methods to FeedbackStore (do NOT modify existing methods):

   def query_verdicts(
       self,
       status: Optional[str] = None,        # "match", "no_match", "uncertain", "pending"
       score_min: Optional[float] = None,
       score_max: Optional[float] = None,
       source: Optional[str] = None,         # "llm", "human"
       sort_by: str = "score",               # "score", "created_at", "confidence"
       sort_order: str = "asc",              # "asc", "desc"
       limit: int = 50,
       offset: int = 0,
   ) -> Dict[str, Any]:
       """
       Paginated, filterable query over the feedback collection.
       Returns {"items": [...], "total": int, "limit": int, "offset": int}.
       Uses AQL with bind variables (no injection risk).
       """

   def count_by_status(self) -> Dict[str, int]:
       """
       Returns verdict counts grouped by decision: {"match": N, "no_match": N, ...}.
       Uses a single AQL COLLECT query.
       """

   def pending_review_count(self) -> int:
       """
       Returns count of verdicts where source='llm' and no human correction exists.
       This is the "pending review" count for the UI badge.
       """

3. Read src/entity_resolution/core/configurable_pipeline.py. Find the run() method.

4. Add an optional `on_progress` callback parameter to run():
   - Signature: on_progress: Optional[Callable[[Dict[str, Any]], None]] = None
   - At each stage transition (blocking, similarity, clustering, etc.), call
     on_progress({"type": "stage_start", "stage": "<name>", "timestamp": "..."})
   - After each stage completes, call
     on_progress({"type": "stage_complete", "stage": "<name>", "result": {...}, "timestamp": "..."})
   - At pipeline completion, call
     on_progress({"type": "pipeline_complete", "total_runtime_seconds": N, "summary": {...}})
   - If on_progress is None (default), behavior is identical to today — nothing changes.
   - This MUST be fully backward-compatible: all existing callers pass no on_progress
     argument and see zero change in behavior or return value.

5. Write tests in tests/test_ui_core_additions.py:

   Test FeedbackStore.query_verdicts:
   - Empty collection returns {"items": [], "total": 0, ...}
   - Filter by status works
   - Filter by score range works
   - Sorting works (score asc, score desc)
   - Pagination (limit/offset) works
   - Combined filters work

   Test FeedbackStore.count_by_status:
   - Empty collection returns empty dict or all zeros
   - Correct counts after inserting test verdicts

   Test FeedbackStore.pending_review_count:
   - Returns 0 when no verdicts
   - Returns correct count of LLM verdicts without human corrections

   Test on_progress callback:
   - run() without on_progress still works (backward compat)
   - run() with on_progress receives stage_start and stage_complete events
   - Events have correct structure (type, stage, timestamp keys)
   - pipeline_complete event is the last event

   Use pytest fixtures and mocks. Mock the ArangoDB connection. Do NOT require
   a running ArangoDB instance for these tests.

ACCEPTANCE CRITERIA:
- [ ] All existing tests still pass (run `python -m pytest tests/ -x -q`)
- [ ] query_verdicts returns paginated, filtered results
- [ ] count_by_status returns correct grouping
- [ ] pending_review_count returns correct count
- [ ] on_progress is called at each stage when provided
- [ ] on_progress=None (default) causes zero behavior change
- [ ] All new tests pass
- [ ] No linter errors
```

---

## Wave 2 — Core Screens (3 parallel subagents, depends on Wave 1)

These run after Wave 1 completes. Each subagent builds one complete screen (frontend components + page wiring). The backend routes are already created in Wave 1.

---

### Subagent W2-A: Review Queue Screen

**Owns:** `ui/src/components/review/`, `ui/src/pages/ReviewPage.tsx`

```
Build the Review Queue screen — the highest-value UI screen for entity resolution.

CONTEXT:
Read docs/architecture/ENTITY_RESOLUTION_UI.md section "2. Review Queue" for the
exact layout and interaction design.

The FastAPI backend routes already exist at /api/review/*. The React Query hooks
already exist in ui/src/hooks/useReview.ts. The API client functions already exist
in ui/src/api/review.ts. Shared components (DataTable, ScoreBadge, FieldDiff, Badge)
already exist in ui/src/components/shared/.

YOUR FILES (you may ONLY create/modify these):
- ui/src/components/review/ReviewQueue.tsx
- ui/src/components/review/PairComparison.tsx
- ui/src/components/review/VerdictPanel.tsx
- ui/src/components/review/ReviewFilters.tsx
- ui/src/components/review/ThresholdBanner.tsx
- ui/src/components/review/FieldScoreBar.tsx
- ui/src/components/review/index.ts
- ui/src/pages/ReviewPage.tsx (replace placeholder content)

DO NOT modify files outside ui/src/components/review/ and ReviewPage.tsx.

TASKS:

1. ReviewQueue.tsx — the main list of pairs awaiting review:
   - Uses useReviewQueue(collection, filters) hook
   - Renders a vertical list of PairComparison cards
   - Filter bar at top (ReviewFilters) for status, score range, source
   - Shows count: "47 pending | 312 resolved"
   - Pagination at bottom
   - Loading/empty states using shared components

2. PairComparison.tsx — a single pair card showing two records side-by-side:
   - Left column: Record A fields, Right column: Record B fields
   - Uses FieldDiff component to highlight matching/differing values
   - Field color coding: green for high similarity (≥0.80), amber (0.55-0.80), red (<0.55)
   - Shows overall similarity score with ScoreBadge
   - Shows LLM verdict (if available) with reasoning text
   - VerdictPanel at the bottom for human decision

3. VerdictPanel.tsx — the action bar for each pair:
   - Three buttons: "Match" (green), "Not Match" (red), "Skip" (gray)
   - Calls useSubmitVerdict() mutation hook
   - Shows confirmation feedback (brief green/red flash on submit)
   - Keyboard shortcuts: M = match, N = not match, S = skip
   - useEffect for keydown listener (only when this pair is focused/active)
   - Optional notes textarea that expands on click

4. ReviewFilters.tsx — filter controls:
   - Status dropdown: All, Pending, Match, No Match
   - Score range: two number inputs (min/max) or a dual-range slider
   - Source filter: All, LLM Only, Human Only
   - Apply button or auto-apply on change

5. ThresholdBanner.tsx — shows at the top of the page:
   - "Current thresholds: Low 0.55 | High 0.80"
   - "Optimize Thresholds" button → calls optimizeThresholds mutation
   - Shows a brief explanation: "Pairs below low are auto-rejected.
     Pairs above high are auto-accepted. Between = review queue."
   - Refreshes threshold display after optimization

6. FieldScoreBar.tsx — horizontal bar showing a single field's similarity:
   - Label (field name), filled bar proportional to score, numeric score
   - Color matches the score range (green/amber/red)

7. Wire ReviewPage.tsx:
   - Renders ThresholdBanner at top
   - Renders ReviewQueue as main content
   - Uses global collection context for the active collection

ACCEPTANCE CRITERIA:
- [ ] Review page shows a list of pairs with side-by-side record comparison
- [ ] Field-level similarity scores are visually displayed with color coding
- [ ] Match/Not Match/Skip buttons submit verdicts via the API
- [ ] Keyboard shortcuts (M/N/S) work for quick review
- [ ] Filters update the displayed list
- [ ] Threshold banner shows current values and optimize button
- [ ] Loading and empty states display correctly
- [ ] No TypeScript errors
```

---

### Subagent W2-B: Cluster Browser Screen

**Owns:** `ui/src/components/clusters/`, `ui/src/pages/ClustersPage.tsx`, `ui/src/pages/ClusterDetailPage.tsx`

```
Build the Cluster Browser — list view and detail view with graph visualization.

CONTEXT:
Read docs/architecture/ENTITY_RESOLUTION_UI.md sections "3. Cluster Browser"
(both List View and Detail View) for the exact layout and interaction design.

The backend routes exist at /api/clusters/*. React Query hooks exist in
ui/src/hooks/useClusters.ts. Shared components exist in ui/src/components/shared/.

YOUR FILES (you may ONLY create/modify these):
- ui/src/components/clusters/ClusterList.tsx
- ui/src/components/clusters/ClusterTable.tsx
- ui/src/components/clusters/ClusterDetail.tsx
- ui/src/components/clusters/ClusterGraph.tsx
- ui/src/components/clusters/ClusterMembers.tsx
- ui/src/components/clusters/ExplainMatchModal.tsx
- ui/src/components/clusters/ClusterFilters.tsx
- ui/src/components/clusters/index.ts
- ui/src/pages/ClustersPage.tsx (replace placeholder content)
- ui/src/pages/ClusterDetailPage.tsx (replace placeholder content)

TASKS:

1. ClusterList / ClusterTable — paginated table of clusters:
   - Columns: ID, Size, Quality Score, Avg Similarity, Density, View button
   - Sort by any column (click header)
   - Filter by min size, quality range
   - Quality score color coding (green ≥ 0.80, amber 0.55-0.80, red < 0.55)
   - Warning icon on low-quality clusters
   - Click row or View button → navigate to /clusters/{collection}/{key}
   - Pagination controls

2. ClusterDetail.tsx — the detail page layout:
   - Header: cluster ID, member count, quality score
   - Two-column layout: ClusterMembers (left), ClusterGraph (right)
   - Action buttons: "View Golden Record", "Explain Edge" (opens modal)

3. ClusterGraph.tsx — interactive similarity graph using @xyflow/react (React Flow):
   - Each cluster member = a node (show abbreviated record info)
   - Each similarity edge = an edge (label with score)
   - Node colors by source system (assign colors from a palette)
   - Edge colors by similarity: green ≥ 0.80, amber 0.55-0.80, red < 0.55
   - Edge thickness proportional to similarity score
   - Click an edge → open ExplainMatchModal with field-level breakdown
   - Uses useClusterGraph(collection, key) hook for data
   - Automatic layout (dagre or force-directed)
   - Zoom/pan controls

4. ClusterMembers.tsx — vertical list of member records:
   - Each member: card with key fields displayed
   - Source system label
   - Click a member to highlight it in the graph

5. ExplainMatchModal.tsx — modal showing field-level similarity:
   - Triggered by clicking an edge in the graph or "Explain Edge" button
   - Shows Record A vs Record B fields side-by-side
   - Each field: name, value A, value B, similarity score with FieldScoreBar
   - Overall score at top
   - Close button and click-outside-to-close

6. ClusterFilters.tsx — filter controls for the list view:
   - Min cluster size (number input)
   - Quality score range
   - Search by member record content

ACCEPTANCE CRITERIA:
- [ ] Cluster list page shows paginated table with quality indicators
- [ ] Clicking a cluster navigates to the detail page
- [ ] Detail page shows members list and interactive React Flow graph
- [ ] Graph nodes are colored by source, edges colored by similarity
- [ ] Clicking an edge opens the explain match modal
- [ ] Modal shows field-level similarity breakdown
- [ ] Sorting and filtering work on the list page
- [ ] No TypeScript errors
```

---

### Subagent W2-C: Pipeline Runner + Dashboard Wiring

**Owns:** `ui/src/components/pipeline/`, `ui/src/pages/PipelinePage.tsx`, `ui/src/pages/DashboardPage.tsx` (enhance from placeholder), `ui/src/hooks/usePipelineWs.ts`

```
Build the Pipeline Runner screen with WebSocket progress and wire up the Dashboard.

CONTEXT:
Read docs/architecture/ENTITY_RESOLUTION_UI.md sections "1. Dashboard" and
"4. Pipeline Runner" for the exact layouts and interaction design.

Backend routes exist at /api/pipeline/* and /ws/pipeline/{run_id}. The Dashboard
page was created as a placeholder in Wave 1. Enhance it with real charts and
pipeline history.

YOUR FILES (you may ONLY create/modify these):
- ui/src/components/pipeline/PipelineRunner.tsx
- ui/src/components/pipeline/StageProgress.tsx
- ui/src/components/pipeline/PipelineHistory.tsx
- ui/src/components/pipeline/PipelineResults.tsx
- ui/src/components/pipeline/ConfigUploader.tsx
- ui/src/components/pipeline/index.ts
- ui/src/components/dashboard/StatsGrid.tsx
- ui/src/components/dashboard/DistributionChart.tsx
- ui/src/components/dashboard/RecentRuns.tsx
- ui/src/components/dashboard/index.ts
- ui/src/hooks/usePipelineWs.ts
- ui/src/pages/PipelinePage.tsx (replace placeholder)
- ui/src/pages/DashboardPage.tsx (enhance from placeholder)

TASKS:

1. usePipelineWs.ts — custom hook for WebSocket pipeline progress:
   - Connects to /ws/pipeline/{runId}
   - Parses JSON messages into typed events
   - Maintains state: stages (array of {name, status, progress, result, timing})
   - Handles reconnection and error states
   - Returns: { stages, isConnected, isComplete, error, summary }

2. PipelineRunner.tsx — the main pipeline execution screen:
   - Collection selector (from global context)
   - Config input: ConfigUploader (upload YAML) or link to Config Builder
   - "Run Pipeline" button → POST /api/pipeline/run → returns run_id
   - Once running: show StageProgress components for each stage
   - After completion: show PipelineResults summary

3. StageProgress.tsx — a single pipeline stage row:
   - Stage name (Blocking, Similarity, LLM Curation, Clustering, Golden Records)
   - Status icon: waiting (gray circle), running (spinning), done (green check), error (red x)
   - Progress bar (if stage reports progress percentage)
   - Timing (elapsed seconds)
   - Result summary when complete (e.g., "12,450 candidates, 97.5% reduction")

4. PipelineResults.tsx — shown after pipeline completes:
   - Total runtime
   - Stage-by-stage summary cards
   - Action links: "View N clusters →", "N pairs need review →", "Export results"
   - Links navigate to Clusters and Review pages with the collection pre-selected

5. ConfigUploader.tsx:
   - Drag-and-drop or click-to-upload for YAML/JSON config files
   - Parses and displays the config summary (entity type, collection, strategy)
   - Validate button → calls /api/config/validate
   - Shows validation errors inline

6. Dashboard enhancements (DashboardPage.tsx):

   StatsGrid.tsx — 4 StatCard components in a row:
   - Documents (from pipeline_status)
   - Clusters (from pipeline_status)
   - Pending Reviews (from review stats pending_review_count)
   - Avg Quality Score (from cluster stats)

   DistributionChart.tsx — two Recharts histograms:
   - Cluster size distribution (bar chart)
   - Similarity score distribution (bar chart)
   Uses cluster stats data.

   RecentRuns.tsx — table of recent pipeline runs:
   - Columns: Time (relative), Config, Clusters, Review Queue, Status
   - Fetches from /api/pipeline/history

7. PipelineHistory.tsx — full pipeline run history (linked from dashboard):
   - Expandable rows showing per-stage details
   - Time, duration, status, result summary

ACCEPTANCE CRITERIA:
- [ ] Dashboard shows 4 stat cards with real data from the API
- [ ] Dashboard shows cluster size and similarity distribution charts
- [ ] Dashboard shows recent pipeline runs table
- [ ] Pipeline page accepts YAML config upload
- [ ] Running a pipeline shows real-time stage progress via WebSocket
- [ ] Each stage shows status icon, progress bar, and timing
- [ ] Completion shows summary with links to clusters and review
- [ ] No TypeScript errors
```

---

## Wave 3 — Remaining Screens (3 parallel subagents, depends on Wave 1)

These can run after Wave 1 (they don't depend on Wave 2 screens).

---

### Subagent W3-A: Config Builder + Entity Resolver

**Owns:** `ui/src/components/config/`, `ui/src/components/resolve/`, `ui/src/pages/ConfigPage.tsx`, `ui/src/pages/ResolvePage.tsx`

```
Build the Config Builder (visual pipeline configuration) and Entity Resolver
(interactive single-record resolution) screens.

CONTEXT:
Read docs/architecture/ENTITY_RESOLUTION_UI.md sections "5. Config Builder"
and "6. Entity Resolver" for layouts and interactions.

YOUR FILES:
- ui/src/components/config/ConfigBuilder.tsx
- ui/src/components/config/BlockingSection.tsx
- ui/src/components/config/SimilaritySection.tsx
- ui/src/components/config/ClusteringSection.tsx
- ui/src/components/config/LLMSection.tsx
- ui/src/components/config/CollectionSection.tsx
- ui/src/components/config/WeightSlider.tsx
- ui/src/components/config/index.ts
- ui/src/components/resolve/EntityResolver.tsx
- ui/src/components/resolve/RecordInputForm.tsx
- ui/src/components/resolve/MatchResult.tsx
- ui/src/components/resolve/index.ts
- ui/src/pages/ConfigPage.tsx
- ui/src/pages/ResolvePage.tsx

TASKS:

1. ConfigBuilder.tsx — accordion/step-based config editor:
   - 5 collapsible sections matching ERPipelineConfig structure
   - CollectionSection: entity type dropdown, collection selector, "Profile Dataset" button
   - BlockingSection: strategy dropdown, field list with add/remove, max_block_size input,
     "Get Recommendations" button (calls /api/config/blocking)
   - SimilaritySection: algorithm dropdown, threshold slider (0-1),
     field weight sliders (WeightSlider for each field), "Estimate Weights" button
   - ClusteringSection: backend dropdown (auto/python_union_find/etc), min_cluster_size input,
     store_results checkbox
   - LLMSection: enable toggle, provider dropdown, model input, low/high threshold inputs
   - Bottom action bar: [Validate] [Simulate Variants] [Export YAML] [Run →]

2. WeightSlider.tsx — a labeled slider with field name, current value, and numeric display:
   - Range 0.0 to 1.0, step 0.05
   - Shows value as both slider position and number
   - Delete button (×) to remove the field

3. Actions:
   - Validate → POST /api/config/validate, show errors inline next to offending sections
   - Simulate Variants → POST /api/config/simulate (needs at least 2 configs —
     current config + a "default" variant), show comparison table
   - Export YAML → POST /api/config/export, trigger download
   - Run → navigate to Pipeline page with config as state

4. EntityResolver.tsx — interactive resolution form:
   - Collection selector
   - RecordInputForm: dynamic field inputs based on collection schema
     (fetch schema from /api/collections/{name}/sample)
   - "Resolve" button → POST /api/resolve/{collection}
   - Results: list of MatchResult cards sorted by score

5. RecordInputForm.tsx:
   - Given field names from the collection schema, render one input per field
   - Text inputs for all fields
   - Clear all button

6. MatchResult.tsx — a single match result card:
   - Score badge, record key, key field values
   - "Explain Match" button → calls /api/review/{collection}/pair/{key_a}/{key_b}
     and shows field breakdown in a modal (reuse ExplainMatchModal from clusters)

ACCEPTANCE CRITERIA:
- [ ] Config builder renders all 5 sections with appropriate inputs
- [ ] Weight sliders update values smoothly
- [ ] Validate shows errors inline
- [ ] Export downloads a YAML file
- [ ] Entity resolver accepts field inputs and shows matching results
- [ ] Match results show scores and explain-match detail
- [ ] No TypeScript errors
```

---

### Subagent W3-B: Golden Record Manager + Export

**Owns:** `ui/src/components/golden/`, `ui/src/components/export/`, `ui/src/pages/GoldenRecordsPage.tsx`, `ui/src/pages/GoldenRecordDetailPage.tsx`, `ui/src/pages/ExportPage.tsx`

```
Build the Golden Record Manager and Export Center screens.

CONTEXT:
Read docs/architecture/ENTITY_RESOLUTION_UI.md sections "7. Golden Record Manager".

YOUR FILES:
- ui/src/components/golden/GoldenRecordView.tsx
- ui/src/components/golden/ConflictResolver.tsx
- ui/src/components/golden/ProvenanceTable.tsx
- ui/src/components/golden/SourceRecords.tsx
- ui/src/components/golden/MergeStrategySelector.tsx
- ui/src/components/golden/index.ts
- ui/src/components/export/ExportCenter.tsx
- ui/src/components/export/ExportOptions.tsx
- ui/src/components/export/index.ts
- ui/src/pages/GoldenRecordsPage.tsx
- ui/src/pages/GoldenRecordDetailPage.tsx
- ui/src/pages/ExportPage.tsx

TASKS:

1. GoldenRecordsPage.tsx — list of golden records:
   - Uses cluster list data with "View Golden Record" action per cluster
   - Or links from cluster detail page

2. GoldenRecordView.tsx — main golden record display:
   - Table: Field | Value | Source | Confidence
   - Conflict indicators (⚠) on fields where sources disagree
   - Click a conflicted field → expand ConflictResolver inline

3. ConflictResolver.tsx — shows competing values for a field:
   - Each source's value, source name, update timestamp
   - Button per source to select that value
   - "Manual Override" text input for custom value
   - Submit updates the golden record preview

4. ProvenanceTable.tsx — full provenance for the golden record:
   - Which source contributed each field value
   - Strategy used (consensus, source_preference, conflict_resolution)

5. SourceRecords.tsx — expandable list of source records:
   - Source system, record key, ingestion date, match confidence
   - Click to expand and show full original record

6. MergeStrategySelector.tsx — dropdown for merge strategy:
   - Options: most_complete, newest, first
   - "Re-merge" button to recompute with selected strategy
   - Preview updates in real time via /api/golden/{collection}/preview

7. ExportCenter (ExportPage.tsx):
   - Collection selector
   - Export format: JSON, CSV
   - Options: include golden records, include source provenance
   - "Export" button → POST /api/export/{collection}
   - Download link appears after export completes
   - Export history (recent exports)

ACCEPTANCE CRITERIA:
- [ ] Golden record page shows merged fields with source provenance
- [ ] Conflicted fields show competing values and resolution UI
- [ ] Strategy selector changes the merge preview
- [ ] Source records are viewable per golden record
- [ ] Export center triggers export and provides download
- [ ] No TypeScript errors
```

---

### Subagent W3-C: Tests + Integration Wiring

**Owns:** `tests/test_ui_routes.py` (new), `tests/test_ui_schemas.py` (new)

```
Write integration tests for the FastAPI UI backend routes.

CONTEXT:
The FastAPI backend is at src/entity_resolution/ui/. Route modules are in
src/entity_resolution/ui/routes/. Pydantic schemas are in
src/entity_resolution/ui/models/schemas.py.

YOUR FILES (you may ONLY create these):
- tests/test_ui_routes.py
- tests/test_ui_schemas.py

DO NOT modify any source files. Tests should mock the ArangoDB connection.

TASKS:

1. test_ui_schemas.py — test Pydantic models:
   - Each request/response model can be instantiated with valid data
   - Required fields raise ValidationError when missing
   - Optional fields default correctly
   - Enum/literal fields reject invalid values

2. test_ui_routes.py — test FastAPI routes using TestClient:
   - Import create_app and create a test client with a mock db
   - Test each endpoint category:

   Health:
   - GET /api/health returns 200 with status and version

   Collections:
   - GET /api/collections returns list of collection info
   - GET /api/collections/{name}/profile returns profile data

   Clusters:
   - GET /api/clusters/{collection} returns paginated list
   - GET /api/clusters/{collection}/{key} returns cluster detail
   - GET /api/clusters/{collection}/{key}/graph returns nodes and edges

   Review:
   - GET /api/review/{collection} returns verdict list
   - GET /api/review/{collection}/stats returns counts
   - POST /api/review/{collection}/pair/{a}/{b}/verdict accepts valid verdict
   - POST /api/review/{collection}/pair/{a}/{b}/verdict rejects invalid decision

   Pipeline:
   - GET /api/pipeline/status/{collection} returns status
   - POST /api/pipeline/run accepts valid config

   Golden:
   - POST /api/golden/{collection}/preview returns preview

   Config:
   - POST /api/config/validate returns validation result

   Resolve:
   - POST /api/resolve/{collection} returns matches

   Mock all ArangoDB calls. Use pytest-mock fixtures. Verify:
   - Correct HTTP status codes
   - Response JSON matches schema
   - Service functions are called with correct arguments

ACCEPTANCE CRITERIA:
- [ ] All schema tests pass
- [ ] All route tests pass with mocked DB
- [ ] Tests cover happy path + at least one error case per endpoint category
- [ ] No test requires a running ArangoDB instance
- [ ] Tests can be run independently: `pytest tests/test_ui_routes.py tests/test_ui_schemas.py -v`
```

---

## Wave 4 — Final Integration (1 subagent, depends on Waves 1-3)

---

### Subagent W4-A: Integration, Docs, Polish

**Owns:** `README.md` (add UI section), `docs/architecture/ENTITY_RESOLUTION_UI.md` (update status), `CHANGELOG.md`, `.gitignore`

```
Final integration, documentation, and polish for the entity resolution UI.

CONTEXT:
The UI backend (FastAPI), frontend (React), and core library additions have all
been implemented by prior subagents. Your job is to tie everything together:
verify it all works, update documentation, and handle loose ends.

YOUR FILES:
- README.md (add UI section — do not rewrite existing content)
- CHANGELOG.md (add UI entry)
- .gitignore (add ui/node_modules, ui/dist, etc.)
- docs/architecture/ENTITY_RESOLUTION_UI.md (change Status from "Proposal" to "Implemented")

TASKS:

1. Add to .gitignore:
   - ui/node_modules/
   - ui/dist/
   - src/entity_resolution/ui/static/ (built assets, not committed)

2. Add UI section to README.md (after the "MCP Tools" section, before "Configuration"):
   - Brief description: optional web UI for reviewing matches, browsing clusters,
     running pipelines, and managing golden records
   - Install: pip install "arango-entity-resolution[ui]"
   - Launch: arango-er ui
   - List the 7 screens with one-line descriptions
   - Screenshot placeholder: "See docs/architecture/ENTITY_RESOLUTION_UI.md for screen designs"

3. Add entry to CHANGELOG.md for the UI feature (under next release):
   - "Added optional web UI (`[ui]` extra) with Review Queue, Cluster Browser,
     Pipeline Runner, Config Builder, Entity Resolver, Golden Record Manager,
     and Export Center"

4. Update ENTITY_RESOLUTION_UI.md:
   - Change Status from "Proposal" to "Implemented (Phase 1-3)"
   - Add "Implementation Notes" section documenting any deviations from the design

5. Run a verification pass:
   - `pip install -e ".[ui,test]"` succeeds
   - `arango-er ui --help` shows the command
   - `cd ui && npm install && npm run build` succeeds
   - `python -m pytest tests/test_ui_routes.py tests/test_ui_schemas.py tests/test_ui_core_additions.py -v` passes
   - No linter errors in src/entity_resolution/ui/

ACCEPTANCE CRITERIA:
- [ ] README includes UI section with install/launch instructions
- [ ] CHANGELOG has the UI feature entry
- [ ] .gitignore covers node_modules and built assets
- [ ] Design doc status is updated
- [ ] All UI-related tests pass
- [ ] npm run build succeeds
- [ ] arango-er ui --help works
```

---

## Execution Summary

| Wave | Subagents | Parallel? | Depends On | Estimated Duration |
|------|-----------|-----------|------------|-------------------|
| **1** | W1-A (Backend), W1-B (Frontend), W1-C (Core) | Yes (3 parallel) | Nothing | 30-45 min |
| **2** | W2-A (Review), W2-B (Clusters), W2-C (Pipeline+Dashboard) | Yes (3 parallel) | Wave 1 | 30-45 min |
| **3** | W3-A (Config+Resolve), W3-B (Golden+Export), W3-C (Tests) | Yes (3 parallel) | Wave 1 | 30-45 min |
| **4** | W4-A (Integration) | Solo | Waves 1-3 | 15-20 min |

**Total: 4 waves, 10 subagents, ~2 hours wall-clock time.**

File partitioning ensures zero conflicts between concurrent subagents within a wave.

---

**Last Updated:** April 13, 2026
