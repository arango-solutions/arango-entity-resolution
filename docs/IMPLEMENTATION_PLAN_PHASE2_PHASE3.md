# Detailed Implementation Plan — Phase 2 (UI Steward Workbench) & Phase 3 (Graph-Native)

**Companion to:** [IMPLEMENTATION_PLAN_2026-06.md](IMPLEMENTATION_PLAN_2026-06.md) · **Baseline:** Phases 0–1 complete and on `main`.
**Status:** Open questions resolved (2026-06-26 review). **Phase 2.0 in progress.** Phases 2.1+ and Phase 3 remain to be built.

### Resolved decisions (2026-06-26 review)

1. **Reviewer identity** — Ship named-token + free-text session name now; real auth deferred to Phase 4. Attribution only — the audit `actor` is not an access-control identity. (Confirms Decision #1.)
2. **Charting** — Use **Recharts** (already a dependency, used by the dashboard) for the tuner histogram; no new charting lib. (Supersedes the "bundled SVG" default in Decision #2 / Open Q2.)
3. **Fellegi-Sunter default** — Keep `scoring_method=fellegi_sunter` **opt-in** until 2.1's band migration ships and the tuner has been used on real data. (Confirms Decision #7 / Open Q3.)
4. **Phase scope** — **Phase 2 is the committed deliverable**; **Phase 3 is optional**, gated on the 1.2 benchmark showing real F1 lift before the L-effort items (3.1/3.2) are built. (Open Q4.)
5. **Benchmarks** — Run the 1.2 harness (Febrl/OpenSanctions) and publish to `docs/benchmarks/` **before** committing to 3.1 (it is the gate), tracked separately from the build. (Open Q5.)

---

## What already exists (so we build on it, not around it)

Backend capabilities Phase 2/3 consume — all shipped and validated:

- **Feedback loop** — `FeedbackApplicationService` (`apply_and_recluster`, suppress/confirm edges via merge-UPSERT, scoped re-cluster, per-component `er_locks`); `POST /api/review/{collection}/pair/{a}/{b}/verdict` already returns `clusters_changed`.
- **Cluster repair** — `ClusterRepairService` (bridge split / queue to `er_repair_queue`); `arango-er repair-clusters`.
- **Golden records** — `GoldenRecordPersistenceService` with per-field survivorship (`field_voting|most_complete|most_recent|source_priority`) + `sourceClusterHash`/`stale` staleness.
- **Metrics** — `EvaluationService` + `GET /api/metrics/{collection}/threshold-sweep` and `/cluster-quality`.
- **Learning** — `ModelParameterEstimator` (`er_model_params`), `FieldProfiler` (`arango-er profile --emit-config`), `FellegiSunterScorer`, `er_term_frequencies`.
- **Schema versioning** — `MigrationRunner` + `er_meta`; registry currently at version 4. **New collections in this plan are added as migrations #5+.**
- **UI** — React 19 + TanStack Query + Tailwind 4 + xyflow. Pages: Dashboard, Clusters, ClusterDetail, Review, GoldenRecords(+Detail), Config, Pipeline, Resolve, Export. API clients generated into `ui/src/api/schema.ts` from `ui/openapi.json`. Optional bearer-token auth (`ER_UI_AUTH_TOKEN`). Existing-but-inert components to wire: `golden/ConflictResolver.tsx`, `golden/MergeStrategySelector.tsx`, `clusters/ClusterGraph.tsx`, `review/ThresholdBanner.tsx`.

**Gaps Phase 2 must respect:** zero frontend tests, no user/identity model (single shared token), no audit trail, response-shape drift handled defensively in components.

---

## Decisions I made (override any of these — they're not asked, just defaulted)

1. **Reviewer identity = named tokens + session name, not real auth.** A `ER_UI_REVIEWERS` env/config maps `token → display name`; if absent, the UI prompts once for a free-text reviewer name held in `localStorage` and sent as `X-Reviewer` header. Full multi-user auth stays out of scope (Phase 4). *Rationale: attribution is needed for audit; real auth is a deployment project.*
2. **Audit log is a new collection `er_audit_log` (migration #5),** written by a new `CurationService`; every cluster mutation and golden-record apply writes `{actor, action, collection, before, after, ts}`.
3. **Threshold tuner computes deltas client-side** from one score-distribution histogram + the 1.2 threshold-sweep payload — no per-drag API calls. New cheap endpoint `GET /api/metrics/{collection}/score-distribution` (one AQL `COLLECT` bucket query).
4. **Cluster edits route through existing `FeedbackApplicationService`** (remove-member = suppress its edges; merge = confirmed edge; split = suppress bridge) so the audit/suppression model stays single-sourced. The new `curation.py` route is a thin orchestrator over it + `CurationService`.
5. **Frontend test stack = Vitest + React Testing Library + Playwright** (none installed today). Playwright smoke run drives a real dockerized ArangoDB, mirroring the backend integration pattern.
6. **Graph context (3.1) enters scoring as extra FS fields with their own EM-learned m/u** — not a bolted-on score. Computed batched per-record (never per-pair), hop cap 2, cached per run.
7. **`fellegi_sunter` stays opt-in** until the band migration (carried over from 1.1) ships; Phase 2's tuner is what lets a user pick posterior-scale thresholds, so the **band migration is folded into 2.1**.
8. **Each sub-phase is its own branch + merge** (your solo fast-forward workflow), backend-before-frontend within each item, every backend change validated on real ArangoDB before the UI consumes it.

---

## Phase 2 — UI: From Results Viewer to Steward Workbench (target v3.8.0)

Ordered so each screen consumes backend capability that exists by the time it's built. **2.0 is new** (prerequisite plumbing surfaced by the decisions above).

### 2.0 Curation + attribution plumbing (S–M) — *new prerequisite*

**Backend:**
- Migration **#5** `create_er_audit_log`.
- `CurationService` (`services/curation_service.py`): `record(actor, action, collection, before, after)` → `er_audit_log`; `history(collection, entity_or_cluster_key, limit)`.
- `ui/auth.py`: resolve reviewer identity — `X-Reviewer` header, or `token→name` from `ER_UI_REVIEWERS`, else `"anonymous"`. Expose `request.state.reviewer` (the review route already reads `getattr(request.state, "reviewer", ...)`).
- Wire `request.state.reviewer` in app middleware so 0.1's verdict endpoint records the real actor.

**Frontend:**
- `ui/src/api/curation.ts` client; `ui/src/hooks/useReviewer.ts` (localStorage name prompt).
- Small "reviewer" chip in `layout/` header.

**Acceptance:** a verdict records `actor` = the resolved reviewer in both the feedback store and `er_audit_log`; `GET /api/curation/{collection}/history/{key}` returns the entries. Integration test on real ArangoDB.

### 2.1 Threshold tuning with live preview (M) — *flagship*

**Backend:**
- `GET /api/metrics/{collection}/score-distribution` → histogram buckets `[{lo, hi, count}]` from one AQL `COLLECT FLOOR(e.similarity/0.05) ...` over non-suppressed edges (cheap; respects suppression).
- `POST /api/metrics/{collection}/apply-threshold` → writes chosen low/high thresholds to the run config (and, when scoring_method=fellegi_sunter, runs the **band migration**: map configured band edges through the score↔posterior curve, or re-derive from accumulated verdicts). Optionally triggers scoped re-cluster of affected edges only.

**Frontend (new page `TuningPage.tsx` + `components/tuning/`):**
- `ThresholdSlider.tsx` — dual-handle (low/high) over the score-distribution histogram (Recharts/inline SVG; CSP-safe, no CDN).
- Live deltas as handles move: pairs/clusters gained-lost computed **client-side** from histogram + threshold-sweep data; when ground truth or accumulated verdicts exist, overlay live P/R/F1 from `/threshold-sweep`.
- `BoundaryPairs.tsx` — samples 10 pairs within ±0.05 of a handle (reuses `review/PairComparison.tsx`), so the user *sees* what a threshold means.
- "Apply" → `apply-threshold` (+ audit entry).

**Acceptance:** moving handles updates counts with no network call; "Apply" persists thresholds and (FS mode) migrates bands; Playwright: load → drag → apply → assert config changed.

### 2.2 Cluster editing with audit trail (M)

**Backend (`ui/routes/curation.py`, thin over `FeedbackApplicationService` + `CurationService`):**
- `POST /api/curation/{collection}/cluster/{key}/remove-member` `{member_key}` → suppress that member's intra-cluster edges, re-cluster, audit.
- `POST /api/curation/{collection}/merge` `{cluster_keys[] | exemplar pairs}` → confirmed edge(s) between exemplars, re-cluster, audit.
- `POST /api/curation/{collection}/cluster/{key}/split` `{edge | partition}` → suppress bridge (reuse 1.3 suggestion) or apply a drag-selected partition, audit.
- `GET /api/curation/{collection}/history/{key}` → audit entries.

**Frontend:**
- `ClusterDetailPage`/`ClusterGraph`: node-select → "doesn't belong" (remove-member); multi-select clusters → merge; "split" surfaces 1.3's weakest-edge suggestion or drag-partition.
- New "History" tab rendering `er_audit_log`.
- Review page gains a **"Suspect clusters"** tab fed by `er_repair_queue` (1.3 already populates it) → links to ClusterDetail for action.
- Invalidate React Query caches on `clusters_changed`.

**Acceptance:** remove/merge/split each mutate clusters and write audit rows; suppressed/confirmed honored on re-run; Playwright covers remove-member end to end.

### 2.3 Review workflow depth (M)

**Backend:**
- Batch endpoint `POST /api/review/{collection}/batch-verdict` (filter-scoped "accept all LLM matches ≥ X", "send band to LLM"); applies 0.1 per pair under one response.
- Verdict records reviewer + timestamp (from 2.0) + optional confidence.
- CSV export of pending pairs (extend `export.py`).

**Frontend:**
- `ReviewQueue`: bulk actions, reviewer attribution + timestamps surfaced, optional confidence capture in `VerdictPanel`, auto-advance to next unreviewed, `?` shortcut-help modal, pagination preserved across filter changes.
- Wire `golden/ConflictResolver` + `MergeStrategySelector` to 0.3 survivorship params with preview → apply → audit (golden records become editable).

**Acceptance:** bulk-accept applies N verdicts + N audit rows in one call; golden record conflict resolution persists via survivorship strategy; verdicts carry reviewer/timestamp.

### 2.4 Data profiling screen (S–M)

**Backend:** `GET /api/profile/{collection}` wrapping `FieldProfiler.profile()` and `?emit_config=true` → `emit_similarity_config()` (already built in 1.4; just expose over HTTP). MCP `profile_dataset` tool upgrade to same.

**Frontend:** `ProfilePage.tsx` — per-field type badges, completeness, cardinality, sample values; "Generate config" pre-fills `config/ConfigBuilder`. Natural first screen for a new collection (onboarding).

**Acceptance:** profile renders detected types matching `FieldProfiler`; "Generate config" round-trips into the config builder.

### 2.5 UI foundation hardening (M, parallel with 2.1–2.4)

- **Tests:** Vitest + RTL for components/hooks; Playwright smoke (dashboard → run pipeline vs docker ArangoDB → review a pair → verdict applied). Wire into CI (`.github/workflows/ui-contract.yml` already exists — extend it).
- **Contract:** regenerate client from `openapi.json`; delete hand-written duplicate types; remove `pairs|verdicts|items` / `record_a|doc_a` defensive shims by fixing backend response models.
- **Perf:** batch pair-detail endpoint (kills 10-requests-per-page in `PairComparison`); `@tanstack/react-virtual` on cluster/review tables.
- **Access:** aria labels, focus traps in modals, non-color status; dark mode via Tailwind `dark:` + toggle.
- **API hardening:** restrict CORS methods/headers for configured origins, simple rate-limit middleware, request size limits.

**Phase 2 exit:** a steward can profile a collection, tune thresholds against live metrics, review pairs in bulk with attribution, repair/merge/split clusters, and publish golden records — all in the UI, all audited.

---

## Phase 3 — Graph-Native Differentiation (target v4.0)

Sequenced after Phase 2 because each needs the closed loop, calibrated FS scores, and the eval harness to *prove* its lift.

### 3.1 Relationship features in similarity scoring (L)

**New `similarity/graph_context.py` (`GraphContextSimilarity`):**
- Per candidate pair, graph evidence: shared-neighbor count/Jaccard over configured edge collections (shared employer/address/device/phone), shortest-path existence ≤ k through non-similarity edges.
- **Batched, never per-pair:** one neighbor-set fetch per *record* in the candidate set (AQL traversal, hops capped at 2), cached per run; pair features joined in memory. (Carries the perf design + risk note from the main plan.)
- **Enters the FS model as additional comparison fields with their own EM-learned m/u** — graph evidence is calibrated, not bolted on. `ModelParameterEstimator` already learns per-field m/u; graph features become extra fields in the comparison vector.
- Config `similarity.graph_context: {edge_collections, max_hops, features}`.
- **Explainability payoff:** `run_explain_match` (MCP) + `ExplainMatchModal` (UI) gain path evidence — "both linked to Acme Corp (employer) and 12 Main St (address)" — rendered as a mini-graph.

**Acceptance:** on a relationship-rich dataset, F1 with graph features ≥ F1 without (measured via 1.2); throughput benchmark recorded *before* committing to the v4.0 headline (per the main plan's risk).

### 3.2 Collective / iterative resolution (L)

- Optional pipeline stage `collective: {enabled, max_rounds}`: after each clustering pass, merged entities change the graph → re-score candidate pairs whose graph features changed → new edges → incremental re-cluster (reuse 0.1's scoped re-clusterer) → repeat to fixpoint or max-rounds.
- Benchmark vs single-pass on relationship-rich data; publish the delta.

**Acceptance:** convergence within max-rounds; measured F1 delta vs single-pass; no oscillation (fixpoint detection test).

### 3.3 Incremental cluster maintenance (M–L)

- Extend `core/incremental_resolver.py` from "resolve one record" to "maintain clusters": new/updated record → block → score (with graph context) → join/create/merge clusters via 0.1 machinery, honoring confirmed/suppressed edges as hard constraints (Zingg "living clusters" / Senzing sequence-neutrality).
- Ship `arango-er watch` (poll or changes-API driven) + a `resolve_and_commit` MCP tool.

**Acceptance:** adding a record updates only the affected cluster; sequence-neutral (same final clusters regardless of insert order) — property test.

### 3.4 Graph-embedding blocking (M)

- Productize `Node2VecEmbeddingService` (exists) as a real `BlockingStrategy`: embeddings written to records, ANN via the existing vector index, evaluated through the A/B harness against attribute-embedding blocking.
- Document the scale envelope honestly (current node2vec is O(n²)-memory; fine ≤100K nodes, GraphSAGE/ArangoGraphML as the scale path).

**Acceptance:** registered as a blocking strategy selectable in config; A/B harness shows recall/reduction vs baseline; scale envelope documented.

**v4.0 framing:** "the ER system that uses your graph as evidence" — collective resolution + path explanations + incremental maintenance, with benchmark numbers proving the graph lift.

---

## New collections / migrations introduced

| Migration | Collection | Phase |
|---|---|---|
| #5 | `er_audit_log` | 2.0 |
| (existing #4) | `er_repair_queue` | already shipped (1.3) |
| — | none new | 3.x reuses existing edge/cluster/model collections |

---

## Dependency map & suggested order

```
2.0 curation+attribution ──┬─→ 2.2 cluster editing (audit, suspect-cluster queue)
                           ├─→ 2.3 review workflow (attribution, golden apply)
score-distribution + band  └─→ 2.1 threshold tuner  ──→ (enables flipping FS default)
1.4 FieldProfiler ─────────────→ 2.4 profiling screen
2.5 UI foundation: parallel with all of 2.x
2.1 (calibrated thresholds) + 1.1 (EM) ──→ 3.1 graph features ──→ 3.2 collective ──→ 3.3 incremental
1.2 eval harness ──→ benchmark numbers for 3.1/3.2/3.4
node2vec (exists) ──→ 3.4 graph-embedding blocking
```

Recommended execution: **2.0 → 2.1 → 2.2 → 2.3 → 2.4**, with **2.5 continuous**; then **3.1 → 3.2 → 3.3**, **3.4** anytime after 2.x.

---

## Sizing & rough effort

| Item | Size | Backend | Frontend |
|---|---|---|---|
| 2.0 curation/attribution | S–M | audit svc, auth, migration #5 | reviewer chip, hook |
| 2.1 threshold tuner | M | 2 endpoints + band migration | new page, slider, boundary pairs |
| 2.2 cluster editing | M | curation route (thin) | graph editing, history tab, suspect queue |
| 2.3 review workflow | M | batch verdict, CSV | bulk actions, golden apply, shortcuts |
| 2.4 profiling screen | S–M | expose profiler | profile page |
| 2.5 foundation | M | response models, CORS/rate-limit | test stack, virtualization, a11y, dark mode |
| 3.1 graph features | L | graph_context + FS fields + explain | mini-graph in ExplainMatch |
| 3.2 collective | L | iterative stage | benchmark view (optional) |
| 3.3 incremental | M–L | watcher + MCP tool | — |
| 3.4 graph-embedding blocking | M | strategy + A/B eval | — |

---

## Open questions for your review (answer only what you care about; I'll default the rest per §Decisions)

1. **Reviewer identity** — OK to ship named-tokens + free-text session name now and defer real auth to Phase 4? (Decision #1.)
2. **Charting lib** — inline SVG/Recharts (CSP-safe, bundled) for the tuner histogram, or do you already have a preferred lib? (I'll default to a tiny bundled SVG component, zero deps.)
3. **FS default flip** — once 2.1's band migration lands, flip `scoring_method` default to `fellegi_sunter`, or keep opt-in indefinitely? (Decision #7 keeps it opt-in until you say.)
4. **Phase 3 priority** — is the v4.0 graph-native story the goal, or would you rather stop after Phase 2 (a complete steward workbench) and treat Phase 3 as optional? This changes whether 3.1's perf benchmark gate is worth the L-effort.
5. **Benchmarks** — want me to run the 1.2 harness on Febrl/OpenSanctions and publish numbers (`docs/benchmarks/`) as part of this, or separately?
```
