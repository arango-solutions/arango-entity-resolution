# Comprehensive Project Review — ArangoDB Entity Resolution

**Date:** June 1, 2026
**Reviewed version:** `3.5.1`
**Scope:** Architecture, code quality (duplication / orphan / hardwiring), security, documentation consistency, PRD gaps, and the web UI.

---

## Scale snapshot

| Area | Files | LOC |
|------|------:|----:|
| Source (`src/entity_resolution/`) | 120 | ~35,700 |
| Tests (`tests/`) | 120 | ~37,160 |
| Web UI (`ui/src/`) | 85 | ~7,266 |
| Scripts (`scripts/`) | 45 | ~13,985 |

---

## Executive summary

A mature, ambitious, well-documented project with a genuinely strong v3 config-driven core, a clean service layer, and broad capability coverage (blocking, pluggable clustering backends, embeddings, LLM curation, MCP, web UI). The largest risks are **not** in the core algorithms — they are in the **security exposure of the new web/MCP surfaces**, **accumulated parallel/legacy implementations** that create the "hardwired" perception, and **frontend–backend contract drift** in the just-started UI.

| Dimension | Grade | Headline |
|---|---|---|
| Architecture & core design | Strong | Clean `ConfigurableERPipeline` + `ERPipelineConfig`; good service layering |
| "Hardwired" concern | Partly valid | v3 path is generic; legacy v1 + address + `utils/algorithms` embed person/customer schemas |
| Duplicate code | Moderate-High | Filter builders, WCC backends + dead legacy copies, parallel pipeline classes |
| Orphan code | Moderate | Enrichments, several strategies, async pipeline, GraphRAG not wired to core |
| Security | High risk | Unauthenticated UI/MCP with full DB creds; AQL injection gaps |
| Docs vs code | Good, minor drift | Tool counts, UI tech stack, a few unimplemented claims |
| PRD | Good, some gaps | Missing current-state security/UI requirements, observability, testing NFRs |
| Web UI | Promising scaffold, not production-ready | Solid structure; many broken API contracts |

---

## 1. Strengths

- **Clean v3 abstraction.** `ConfigurableERPipeline` + `ERPipelineConfig` are genuinely config/YAML-driven for collections, fields, weights, and the wired blocking strategies. Defaults are generic (`config/er_config.py:1043-1046`).
- **Pluggable clustering backends** with `auto` selection (`services/clustering_backends/`) — a real architectural strength.
- **One service layer behind three interfaces** (CLI, MCP, UI); the "no parallel resolution paths" principle is mostly honored.
- **Strong AQL-hardening foundation**: `utils/validation.py`, `utils/aql_builders.py`, `@@collection` bind variables, collection-name validation in `strategies/base_strategy.py:57-58`.
- **Heavy documentation and test investment** (~1:1 test-to-source LOC; 145 markdown docs).
- **Good secret hygiene at the core**: `.env` gitignored and untracked; `DatabaseConfig` refuses to start without a password (`utils/config.py:95-106`); arangoimport uses argv lists, not `shell=True`.

---

## 2. Code Quality

### 2a. "Hardwired for certain node types" — partly true

The complaint is legitimate but localized. There is no `vessel` type anywhere; the schema-coupling lives in three places:

- **Legacy v1 services hardcode a person/customer schema.** `services/blocking_service.py:218-255` bakes `first_name/last_name/email/phone/address/city/company` into the ArangoSearch view; `services/similarity_service.py:281-299` hardcodes `address`/`company` comparisons.
- **`utils/algorithms.py:164-227`** branches on canonical field *names* (`email`, `phone`, `first_name`, `address`, …) for normalization and feature extraction.
- **Address is a parallel domain stack.** `entity_type == 'address'` short-circuits the generic pipeline into `AddressERService` (`core/configurable_pipeline.py:184-186`), which ships US-postal defaults (`services/address_er_service.py:80-129`) and is exempted from generic validation (`config/er_config.py:1087-1092`).
- **Global config defaults** still assume `customers`/`persons` (`utils/config.py:151-152`).

**Net:** the *modern* path is generic; the *legacy + address + low-level normalization* paths are schema-bound. The perception comes from examples/demos and v1 services, not the v3 core.

### 2b. Duplication (Moderate-High)

- **`_build_filter_conditions` copy-pasted** across `base_strategy.py:103-172`, `collect_blocking.py:204-273`, `geographic_blocking.py:335-380`, `graph_traversal_blocking.py:249-293`. `_estimate_blocks_processed` is identical in collect + geographic.
- **Dead legacy clustering inside the new service**: `WCCClusteringService._find_connected_components_aql` (`wcc_clustering_service.py:417+`) and `_find_connected_components_bulk` (`:505+`) — ~190 lines duplicating `aql_graph.py`/`python_dfs.py`, never called.
- **Parallel pipeline classes**: `configurable_pipeline.py` (primary) vs `entity_resolver.py` (deprecated v1, still used by 15+ scripts/demos) vs `async_pipeline.py` (tests only) vs `orchestrator.py` (examples only) vs `incremental_resolver.py` + `address_pipeline.py`.
- **Deprecated service pairs**: `BlockingService`↔strategies, `SimilarityService`↔`BatchSimilarityService`, `ClusteringService`↔`WCCClusteringService`.

### 2c. Orphan / unwired code (Moderate)

Library-complete but **not wired into the core pipeline or CLI**:
- **Enrichments** (`TypeCompatibilityFilter`, `AcronymExpansionHandler`, `RelationshipProvenanceSweeper`) — only in tests/examples.
- **Blocking strategies** `geographic`, `hybrid`, `graph_traversal`, `shard_parallel` — not selectable from `ConfigurableERPipeline.run_blocking()` (only exact/bm25/vector/lsh; `configurable_pipeline.py:530-617`).
- **`reasoning/graph_rag.py`, `async_pipeline.py`, `golden_record_persistence_service.py`, `node2vec_embedding_service.py`** — exports + tests only.

### 2d. Smells

- **Oversized modules**: `cli.py` (1411), `mcp/tools/advisor.py` (1320), `config/er_config.py` (1200), `address_er_service.py` (1123).
- **~120+ `except Exception`** blocks, including silent `except: pass` (`ui/routes/pipeline.py:50-51, 148-149`).
- Two validation modules (`utils/validation.py` active, `validation_utils.py` partly orphaned).
- Positive: **zero TODO/FIXME/HACK** in source — debt tracked via `DeprecationWarning`s.

---

## 3. Security (highest-priority area)

| Sev | Finding | Evidence |
|---|---|---|
| Critical | **No auth on any FastAPI UI route**, yet the app holds full ArangoDB credentials. Security == network binding only. | No `Depends`/auth in `ui/`; `app.py:68-71`, `collections.py:88-94` |
| Critical | **MCP server = root-equivalent DB access**; `find_duplicates` writes; no MCP-level auth. | `mcp/server.py:81-88`, `:117-181` |
| High | **AQL injection in `IncrementalResolver`** — user `fields` interpolated into AQL with no `validate_field_name`. Reachable via UI `/api/resolve` and MCP `resolve_entity`. | `core/incremental_resolver.py:120-121, 139` |
| High | **Computed-field expressions from config embedded verbatim** into AQL (`LET {var} = {expression}`), reachable via `POST /api/pipeline/run`. | `er_config.py:99-101`, `collect_blocking.py:287-289`, `pipeline.py:93-135` |
| Medium | String-interpolated filters (`method`, `older_than`) instead of bind vars. | `similarity_edge_service.py:364-367`, `cross_collection_matching_service.py:376` |
| Medium | `DataManager.sample_records` interpolates collection name + limit unvalidated. | `data_manager.py:251-257` |
| Medium | No rate limiting; `--readonly` guards only *some* mutations; WebSocket unauthenticated. | `ws.py:14-59` |
| Medium | Default passwords in `docker-compose.yml:7`, `env.example:3-6`, scripts (test-only, copy-paste risk). | — |
| Medium | LLM `base_url` config-controlled → SSRF surface if API exposed. | `llm_verifier.py:131-132` |

**PRD claim "Prevent AQL injection through validated identifiers and bind-variable usage" is only partially true** — strong on the main blocking path, weak on `IncrementalResolver`, computed-field expressions, edge-clear timestamp filters, and MCP entrypoints.

**Priority fixes:** (1) add an auth layer (API key / reverse proxy / mTLS) before any non-localhost bind; (2) validate field/collection identifiers in `IncrementalResolver` and MCP normalization, sandbox or disallow raw computed-AQL expressions; (3) bind-variable the interpolated filters; (4) strip default passwords from non-test compose/env.

---

## 4. Documentation vs Code Consistency

Mostly consistent. Concrete drift:

- **MCP tool count is inconsistent everywhere.** Code has **15** `@mcp.tool()` decorators (`mcp/server.py`); README body says **"14 tools"** (lines 58, 182); README *Project Structure* says **"7 tools, 2 resources"** (line 318); PRD says **"14 tools, 2 resources"**. Reconcile to the real number across all three.
- **UI tech stack drift.** `ENTITY_RESOLUTION_UI.md:70` and README:247 claim **shadcn/ui** and **React Flow**; the actual UI uses plain **Tailwind v4** (no shadcn) and **@xyflow/react**. The design doc also claims **optimistic updates** that aren't implemented.
- **UI design doc marked "Implemented (Phase 1–3)"** but several documented endpoints don't match the frontend contract (see §6), overstating readiness.
- **"No PII logging" / "AQL via bind variables"** security claims in the UI doc (`:767-769`) aren't fully borne out (see §3).
- Version is **consistent** (3.5.1 across `constants.py:309`, README, PRD).

---

## 5. PRD Gap Analysis

The PRD is well-structured and the v4.x roadmap is thorough. Gaps:

1. **No current-state security requirements.** Auth/authz, rate limiting, multi-tenant isolation appear only as *future* v4 items (FR-12, NFR-13), but UI/MCP already expose a live DB today with no auth. Add a present-tense security FR for the shipped surfaces.
2. **UI absent from the PRD.** A shipped web UI has no FRs, success metrics, or NFRs in the PRD — only in a separate architecture doc.
3. **No testing/quality NFR.** Despite ~37K test LOC, there's no stated coverage target, CI gate, or quality bar.
4. **No observability/operability NFR** (logging, metrics, health, audit) for the *current* product — audit only appears as future FR-19.
5. **Data privacy/PII handling** is a `.cursorrules` mandate and a UI-doc claim but not a PRD requirement.
6. **"Production-ready" claim vs reality.** PRD line 11 says "production-ready"; given unauthenticated surfaces and broken UI contracts, qualify it (e.g., "production-ready for embedded/library use behind a trusted boundary").
7. **Enrichments & non-wired strategies** are shipped code but not represented as requirements — promote to FRs or mark experimental.

---

## 6. Web UI Review & How to Improve It

A coherent, well-organized scaffold (feature-based components, React Query for core domains, strict TypeScript, Vite→FastAPI static bundling) but **not production-ready**, primarily due to frontend–backend contract drift. There are **no UI tests, no ESLint/Prettier**, and `ErrorBoundary` exists but is never mounted.

### P0 — Broken/misleading flows (fix first)
- **Review verdict mismatch**: frontend sends `{verdict: match|no_match|skip}`; backend expects `{decision: match|no_match}` (`api/review.ts:47-50` vs `models/schemas.py:16-19`) → 422.
- **Review queue likely throws at runtime**: route calls `query_verdicts(decision=, min_score=, max_score=)` but store expects `status/score_min/score_max` and returns a dict, not a list (`review.py:47-67` vs `feedback.py:171-218`).
- **Golden preview body mismatch**: sends `{keys}`, backend wants `{entity_keys}`; response (`golden_record`) ≠ expected (`fields/provenance/conflicts`).
- **Export contract entirely different** (`api/export.ts` vs `export.py` `ExportRequest`).
- **Resolve** returns a bare list with `_key`; UI expects `{matches,total}` with `m.record`/`m.key`.
- **Pipeline progress is fake**: backend WS emits only `status_change`/terminal events; UI waits for `stage_*` events, so all five stages stay "waiting" (`usePipelineWs.ts:109-176` vs `ws.py:39-59`).
- **React bug**: `PipelineRunner.tsx:48-51` calls `setState` during render.
- **Dashboard charts are hardcoded sample data** (`DistributionChart.tsx:14-35`) — a real `/api/clusters/{collection}/stats` endpoint exists and is unused.

### P1 — Quality
- **Generate types from FastAPI OpenAPI** (`/api/openapi.json`) + CI typecheck — eliminates the entire class of contract drift and removes `as unknown as` shims.
- Mount `ErrorBoundary` around the router outlet; migrate golden/export/config/resolve off ad-hoc `fetch` onto React Query hooks.
- Add **ESLint + Vitest + React Testing Library**; the UI has zero tests.

### P2 — Polish
- Accessibility pass (zero `aria-*`/`role` today; modal lacks focus trap).
- Responsive/mobile nav (fixed `w-60` sidebar, no collapse).
- Shared `Button`/`Input`/`Select`/`Modal` primitives; remove dead `DataTable` + unused API functions.

---

## 7. Recommended priority order

1. **Security**: auth on UI/MCP before any non-localhost exposure; close the `IncrementalResolver` + computed-expression AQL injection paths.
2. **UI contract fixes** (P0 list) + OpenAPI type generation.
3. **Code consolidation**: delete dead WCC methods, unify filter builders, decide the fate of v1 `BlockingService`/`SimilarityService`/`EntityResolutionPipeline` and the unwired strategies/enrichments.
4. **Address the "hardwired" perception**: fold address ER into the generic config path or document it as the one supported domain pack; move field-name normalization in `utils/algorithms.py` to config.
5. **Doc/PRD reconciliation**: fix the MCP tool count (3 conflicting numbers), correct UI tech-stack claims, add present-tense security/UI/testing/observability requirements.
