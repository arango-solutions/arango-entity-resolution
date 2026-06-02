# Remediation Plan - Comprehensive Review Follow-up

Date: June 1, 2026
Source review: COMPREHENSIVE_PROJECT_REVIEW_2026-06-01.md
Baseline version: 3.5.1
Proposed release version after this work: 3.6.0 (minor bump - new auth surface + de-hardwiring default changes)

## Guiding principles

- Security first, sequenced by blast radius (injection + auth before anything else).
- No behavior change without a test. Every fix lands with a regression test.
- Backward compatible: auth defaults to off for localhost; identifier validation only rejects genuinely invalid input.
- Small, reviewable PRs (one workstream per PR, ideally one sub-phase per PR).
- ASCII-only code and docs per docs/development/CLAUDE.md.

## Locked decisions

1. Auth: static API key / bearer token via env (ER_UI_AUTH_TOKEN / ER_MCP_AUTH_TOKEN) + CLI flag.
   Off for localhost; hard guard against public bind without a token unless --insecure passed.
2. UI contracts: change the frontend to match the backend; the one exception is the genuine
   backend review-queue bug, which is fixed server-side.
3. Pipeline progress: add real on_progress callbacks to ConfigurableERPipeline.run() and emit
   stage_* events over WebSocket.
4. Address ER: keep AddressERService as a documented domain pack; remove baked-in US defaults
   unless country=US.
5. Unwired modules: move to an experimental/ namespace, documented as not-yet-wired.

---

## Workstream 1 - Security (highest priority)

### 1A. Close AQL injection paths (High)

| Target | Fix | Evidence |
|--------|-----|----------|
| IncrementalResolver | Call validate_field_names(fields) in __init__; field interpolation in _fetch_candidates then safe. Collection already uses @@col bind var. | core/incremental_resolver.py:52-54, 120-121 |
| Computed-field expressions | Add an allowlist validator for computed_fields expressions (whitelist functions/operators; reject subqueries and INSERT/UPDATE/REMOVE/LET injection). Disabled unless explicitly opted-in via config flag. | config/er_config.py:99-101, collect_blocking.py:287-289 |
| SimilarityEdgeService.clear_edges | Replace string interpolation of method / older_than with bind vars. | services/similarity_edge_service.py:364-367 |
| CrossCollectionMatchingService | Bind-var the older_than filter. | cross_collection_matching_service.py:376 |
| DataManager.sample_records | validate_collection_name(collection); bind-var the limit. | data_manager.py:251-257 |
| MCP normalization | Run validate_collection_name / validate_field_name on inbound identifiers. | mcp/normalization.py:239-241 |

Deliverable: tests/security/test_aql_injection.py feeding malicious payloads to each entry point.

### 1B. Add auth to the FastAPI UI (Critical)

- Optional API-key/bearer dependency wired in create_app on the API router (skip SPA/static and /api/health).
- Config: --auth-token CLI flag + ER_UI_AUTH_TOKEN env. If set, all /api/* and /ws/* require it;
  if unset, behavior unchanged (localhost dev) but log a loud warning when binding to a non-loopback host.
- Apply auth to the WebSocket (query-param or subprotocol token).
- Tighten --readonly to cover all mutating verbs; refuse to start on 0.0.0.0 without a token unless
  --insecure is passed explicitly.

### 1C. Add auth to the MCP SSE transport (High)

- For --transport sse, require a bearer token (env ER_MCP_AUTH_TOKEN); stdio stays trusted-host.
  Keep default bind 127.0.0.1.

### 1D. Default-credential hygiene (Medium)

- Remove hardcoded passwords from docker-compose.yml / env.example defaults (require env injection);
  keep test-only passwords confined to docker-compose.test.yml and tests/conftest.py.
- Update SECURITY.md to match actual config.py behavior.

Sequencing: 1A -> 1B -> 1C -> 1D. PRs: 2 (injection; auth+creds).

---

## Workstream 2 - UI contract fixes + OpenAPI types

### 2A. Establish a contract source of truth (first)

- Add openapi-typescript to ui devDependencies; script npm run gen:api -> ui/src/api/schema.ts.
- CI step: boot app, dump OpenAPI, regenerate types, fail if git diff non-empty.

### 2B. Fix the P0 mismatches (frontend matches backend; review-queue bug fixed server-side)

| Flow | Fix |
|------|-----|
| Review verdict | FE send decision not verdict; reconcile skip value. api/review.ts, VerdictPanel.tsx vs schemas.py:16-19 |
| Review queue | Backend bug: fix review.py:47-67 to call query_verdicts(status=, score_min=, score_max=) and return a list; align FE keys. |
| Review stats | Backend returns {by_decision,total}; derive pending/resolved in FE (StatsGrid, Sidebar). |
| Golden preview | FE send entity_keys; map golden_record response. |
| Export | Rewrite api/export.ts + ExportCenter to ExportRequest / output_files. |
| Resolve | Map bare-list + _key to display shape. |
| Pipeline progress | Real stage_* events (see Workstream 2 / PR5). |
| PipelineRunner setState-in-render | Move to useEffect. |
| Dashboard charts | Wire GET /api/clusters/{collection}/stats (already exists). |

### 2C. UI hardening (P1/P2)

- Mount ErrorBoundary around the router outlet.
- Add ESLint + Prettier + Vitest + React Testing Library; smoke test per page + fetchApi unit tests.
- Migrate ad-hoc fetch (golden/export/config/resolve) onto React Query hooks.
- Accessibility + responsive sidebar as a follow-up.

Sequencing: 2A -> 2B -> 2C. PRs: 3.

---

## Workstream 3 - Code consolidation

### 3A. Dead code removal (low risk)

- Delete WCCClusteringService._find_connected_components_aql / _find_connected_components_bulk
  (wcc_clustering_service.py:417+, 505+) - superseded by backends, never called.

### 3B. De-duplicate filter builders (medium)

- Make collect/geographic/graph_traversal strategies use base_strategy._build_filter_conditions
  (parameterize the doc-variable prefix d. / node.). Collapse identical _estimate_blocks_processed.

### 3C. Quarantine legacy v1 (medium - 15+ referencing scripts)

- Move BlockingService / SimilarityService / EntityResolutionPipeline behind a legacy subpackage
  or mark with loud deprecation + removal version; migrate in-repo scripts/demo to v3 incrementally.

### 3D. Experimental namespace for unwired modules

- Move enrichments, geographic/hybrid/graph_traversal/shard_parallel strategies, graph_rag,
  async_pipeline to experimental/ with not-yet-wired docs.

Sequencing: 3A -> 3B -> 3D -> 3C. PRs: 3-4.

---

## Workstream 4 - Address the "hardwired" perception

### 4A. Address ER as a domain pack

- Keep AddressERService; remove baked-in US postal defaults unless country=US; document explicitly
  as the one supported domain pack.

### 4B. Config-driven normalization

- Replace hardcoded field-name branches in utils/algorithms.py:164-227 with a config-driven
  transformer registry (reuse the existing v3 field-transformer mechanism).

### 4C. Genericize defaults

- Change utils/config.py:151-152 (customers/persons) to neutral defaults or require explicit config;
  update examples to show a non-person entity type.

Sequencing: 4B -> 4C -> 4A. PRs: 2.

---

## Workstream 5 - Docs / PRD reconciliation

### 5A. Fix the MCP tool count (factual error)

- Code has 15 @mcp.tool() decorators; README says 14 (x2) and also 7 (project-structure block);
  PRD says 14. Establish the true count and update README (both spots), PRD, and the UI doc.

### 5B. Correct UI tech-stack claims

- README / ENTITY_RESOLUTION_UI.md: shadcn/ui -> Tailwind v4 (no component library);
  React Flow -> @xyflow/react; remove optimistic-updates claim until implemented; downgrade
  "Implemented (Phase 1-3)" to reflect contract status.

### 5C. Add present-tense PRD requirements

- New FRs/NFRs for current-state security (auth, identifier validation, rate-limit posture),
  Web UI (shipped screens + success metrics), testing/coverage gate, and observability/audit.
  Qualify "production-ready."

Sequencing: 5A/5B immediately (pure doc fixes), 5C after Workstream 1 lands. PRs: 1-2.

---

## Workstream 6 - PyPI release (final)

Build and publish a new release once Workstreams 1-5 land and CI is green.

### 6A. Pre-release

- Decide final version (proposed 3.6.0) and bump src/entity_resolution/utils/constants.py __version__.
- Update CHANGELOG.md with security fixes, UI contract fixes, de-hardwiring, and doc changes.
- Confirm package metadata and console scripts in pyproject.toml.
- make test (full suite) green; make lint; make typecheck.
- Verify entrypoints start: arango-er, arango-er-mcp, arango-er-mcp --demo, arango-er ui.
- Rebuild UI assets (cd ui && npm run build) so static bundle ships in the wheel.
- make build (sdist + wheel); inspect dist/ contents include ui/static.

### 6B. Publish (per RELEASE_CHECKLIST.md)

- Create and push the git tag (e.g., 3.6.0).
- Create a GitHub Release from that tag.
- GitHub Release triggers .github/workflows/publish.yml (tag push alone does NOT publish).
- Verify the version on PyPI and that pip install arango-entity-resolution==3.6.0 succeeds.

### 6C. Post-release

- Update README version badge and PRD "Last Updated" / current-release fields.
- Update RELEASE_CHECKLIST.md target release to the next version.

---

## Suggested PR order and rough effort

| PR | Content | Effort |
|----|---------|--------|
| 1 | W1A injection fixes + tests | 1-2 days |
| 2 | W1B/1C/1D auth + cred hygiene | 2-3 days |
| 3 | W2A OpenAPI types + CI gate | 1 day |
| 4 | W2B P0 contract fixes (incl. backend review-queue bug) | 3-4 days |
| 5 | W2B real pipeline progress callbacks | 1-2 days |
| 6 | W3A/3B dead code + dedupe | 1-2 days |
| 7 | W4 de-hardwiring | 2-3 days |
| 8 | W3D experimental namespace + W3C legacy quarantine | 2-3 days |
| 9 | W2C UI hardening | 2-3 days |
| 10 | W5 docs/PRD reconciliation | 0.5-1 day |
| 11 | W6 PyPI release 3.6.0 | 0.5 day |

Doc quick-fixes (W5A/5B) can land immediately, independent of code.
