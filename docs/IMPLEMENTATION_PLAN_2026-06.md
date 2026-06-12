# Implementation Plan — Path to Best-in-Class ER on ArangoDB

**Companion to:** [PROJECT_REVIEW_2026-06.md](PROJECT_REVIEW_2026-06.md)
**Baseline:** v3.5.1 · June 2026

## Goals and principles

1. **Trust before features.** Phase 0 fixes every place the system claims to do something it doesn't (closed-loop review, probabilistic scoring, golden records, GraphRAG provenance). Nothing in later phases is credible while these are broken.
2. **Metrics before tuning.** The evaluation harness (Phase 1) lands before the UI threshold tuner (Phase 2) because the tuner displays the metrics the harness computes. Every subsequent improvement gets a number.
3. **Build on what exists.** Several "missing" capabilities are partially implemented (`ThresholdOptimizer` with isotonic regression in [feedback.py:261](../src/entity_resolution/reasoning/feedback.py#L261), `validate_clusters` and `_compute_cluster_quality` in [wcc_clustering_service.py](../src/entity_resolution/services/wcc_clustering_service.py), A/B evaluation harness, node2vec service). The plan wires them in and extends them rather than rebuilding.
4. **Each phase ships independently** behind config flags, with its own release (3.6 → 3.7 → 3.8 → 4.0), so value lands continuously.

Sizing: **S** ≤ 2 days · **M** ≈ 3–7 days · **L** ≈ 2–4 weeks of focused work.

---

## Phase 0 — Correctness and Trust (target: v3.6.0)

### 0.1 Close the feedback loop (M) — *the keystone fix*

**Problem:** Human/LLM verdicts persist in `FeedbackStore` but never change edges, clusters, or thresholds (review §2.2).

**Design:** New `FeedbackApplicationService` in `src/entity_resolution/services/feedback_application_service.py`:

- `apply_verdict(pair, verdict)`:
  - `no_match` → mark the similarity edge `suppressed: true, suppressed_by, suppressed_at` (never hard-delete; audit trail) via `SimilarityEdgeService` (deterministic keys at [similarity_edge_service.py:419](../src/entity_resolution/services/similarity_edge_service.py#L419) make the edge addressable from the pair).
  - `match` on a pair below threshold → upsert a confirmed edge with `confirmed: true, confidence: 1.0`.
- `recluster_component(member_key)`: incremental, scoped re-cluster — fetch the affected component via AQL traversal (excluding suppressed edges), re-run WCC on just that subgraph, rewrite only the affected cluster docs. Add `FILTER edge.suppressed != true` to every clustering backend's edge query (`clustering_backends/*.py`).
- Wire into the UI: `POST /api/review/verdict` ([ui/routes/review.py](../src/entity_resolution/ui/routes/review.py)) calls apply + recluster; response includes `clusters_changed` so the frontend can invalidate React Query caches and show "Cluster #42 split into 2" feedback.
- Wire `ThresholdOptimizer` output into pipeline config: add `active_learning.auto_apply_thresholds: bool` to `ActiveLearningConfig` ([er_config.py:733](../src/entity_resolution/config/er_config.py#L733)); when set, `ConfigurableERPipeline` calls `optimize()` at run start and records applied thresholds in run stats.

**Acceptance:** integration test: build 3-record chain cluster A–B–C; human rejects B–C; cluster splits into {A,B} and {C}; re-running the pipeline does not resurrect the suppressed edge; verdict + cluster change visible in UI.

### 0.2 Honest probabilistic scoring (M)

**Problem:** importance multiplier corrupts the LLR sum; confidence is an arbitrary formula (review §2.1).

**Changes in [similarity_service.py:571-652](../src/entity_resolution/services/similarity_service.py#L571):**
- Split into two explicit methods: `_compute_fellegi_sunter_score` (pure LLR sum, no importance multiplier) and `_compute_weighted_heuristic_score` (current behavior, renamed honestly). Config selects via `similarity.scoring_method: fellegi_sunter | weighted_heuristic`; default stays `weighted_heuristic` until 1.x of Phase 1 lands EM (no silent behavior change for existing users).
- Replace the ad-hoc confidence with the proper FS posterior: `P(match|γ) = λ·∏m / (λ·∏m + (1−λ)·∏u)` where prior `λ` is configurable (default from candidate-set match rate estimate). Field-level partial agreement: map similarity to agreement levels (configurable bands) instead of a single binary threshold.
- Document in the API/docstrings which numbers are calibrated probabilities and which are heuristic scores; the UI `ScoreBadge` should label them accordingly.

**Acceptance:** unit tests verifying FS score equals hand-computed LLR sums; posterior in [0,1] and monotone in score; legacy mode bit-identical to current outputs.

### 0.3 Remove the silent-failure golden record path (S)

- Delete `GoldenRecordService` (the `return []` skeleton, [golden_record_service.py:134](../src/entity_resolution/services/golden_record_service.py#L134)) or replace its body with a `DeprecationWarning` + delegation to `GoldenRecordPersistenceService`; remove from `entity_resolution/__init__.py` exports; sweep examples/docs for references.
- Port its one good idea — named survivorship strategies (`most_complete`, `most_recent`, `source_priority`, `field_voting`) — into `GoldenRecordPersistenceService` as a `merge_strategy` parameter (currently the persistence service has no per-field survivorship). This also unblocks the UI's inert `MergeStrategySelector`/`ConflictResolver` (Phase 2.3).

### 0.4 Fix GraphRAG provenance edges (S)

[graph_rag.py:244-246](../src/entity_resolution/reasoning/graph_rag.py#L244): edges must run **document → entity**. Add a `document_collection` to the linker; `_from = document_collection/source_doc_key`, `_to = entity_collection/matched_key`. Migration script to repair existing self-loop edges (they carry `source_doc` as an attribute, so they're recoverable). Integration test traversing doc → extracted entities.

### 0.5 LLM hardening: parsing, cost, budget (M)

In [llm_verifier.py](../src/entity_resolution/reasoning/llm_verifier.py):
- **Parse failures:** one structured re-prompt retry ("Return only JSON matching {schema}"); on second failure return `decision: "error"` and route the pair to the human review queue — never fabricate a verdict from the raw score. Fix fence-stripping to use a regex tolerant of empty/nested blocks.
- **Cost tracking:** accumulate `litellm.completion_cost()` + token counts per call; expose `llm_stats: {calls, tokens_in, tokens_out, cost_usd}` in pipeline results and UI run summary.
- **Budget enforcement:** `LLMProviderConfig.max_cost_usd` / `max_calls` per run; on breach, stop calling the LLM, mark remaining uncertain pairs `pending_review`, log prominently. Pre-run estimate: `(pairs in uncertain band) × avg tokens × price` printed before execution.
- **Optional PII masking** (`llm.mask_fields: [ssn, dob, ...]`) replacing configured field values with stable hashes before the prompt is built.

### 0.6 Hygiene batch (S)

- `git rm --cached coverage.json detailed_coverage_analysis_*.json`; extend `.gitignore`.
- `docker-compose.test.yml`: `ARANGO_ROOT_PASSWORD: ${ARANGO_TEST_PASSWORD:?set ARANGO_TEST_PASSWORD}`.
- Consolidate `VERSION_HISTORY.md` + `VERSION_SUMMARY.md` into `CHANGELOG.md`; delete the stray `~/` directory; delete `tests/archive_broken/`.
- Default `apply_weights=True` in `TupleEmbeddingSerializer` when field weights are configured (or remove the parameter) — currently configured weights are silently inert.

**Phase 0 exit criteria:** review queue verdicts visibly change clusters; no exported API silently returns empty/fabricated results; LLM spend is bounded and reported.

---

## Phase 1 — A Matching Core That Learns (target: v3.7.0)

### 1.1 EM parameter estimation for m/u probabilities (L) — *highest-leverage item*

New `src/entity_resolution/learning/em_estimator.py` (new `learning/` package):

- **Input:** sampled comparison vectors. Sample candidate pairs from blocking output (cap ~1M pairs, reservoir sampling), compute per-field agreement levels using existing comparators from `similarity_service`.
- **Algorithm:** classic FS EM — initialize m/u from current defaults; E-step computes match posteriors; M-step re-estimates per-field/per-level m, u and prior λ; iterate to convergence (tol 1e-5, max 50 iters). Pure numpy; no new heavy deps.
- **Term-frequency adjustments** (Splink's second pillar): for high-cardinality fields (name, city), scale u-probability by relative value frequency — computed with one AQL `COLLECT ... WITH COUNT` per field, stored in a `_er_term_frequencies` collection at pipeline start.
- **Integration:** `similarity.estimation: {method: em, sample_size, max_iterations}` in `SimilarityConfig`; `ConfigurableERPipeline` runs estimation between blocking and scoring when enabled; learned parameters persisted to `_er_model_params` (versioned, timestamped, with the config hash) so runs are reproducible and the UI can display them. CLI: `arango-er estimate --config ...`.
- Flip default `scoring_method` to `fellegi_sunter` once this lands.

**Acceptance:** on a synthetic dataset with known m/u, EM recovers parameters within tolerance; on Febrl/WDC test data, F1 with learned parameters ≥ F1 with hand-tuned defaults.

### 1.2 Evaluation harness as a first-class feature (M)

Extend [ab_evaluation_harness.py](../src/entity_resolution/services/ab_evaluation_harness.py) into `EvaluationService`:

- **Labeled evaluation:** given a ground-truth pair collection, compute precision/recall/F1 **across the full threshold sweep** (the curve, not one point) plus confusion counts at the configured threshold. This output is exactly what the Phase 2 threshold tuner renders.
- **Unsupervised cluster metrics** (labels rarely exist in production): per-cluster density, intra-cluster mean/min edge score, bridge-edge detection (single low-score edge joining two dense subgraphs), size distribution. Builds directly on `_compute_cluster_quality` ([wcc_clustering_service.py:447](../src/entity_resolution/services/wcc_clustering_service.py#L447)).
- **Benchmark runner:** `scripts/benchmarks/run_public_benchmarks.py` against WDC Products (hard splits) and OpenSanctions Pairs; results committed to `docs/benchmarks/` per release. This is also the marketing artifact.
- New API route `ui/routes/metrics.py`: `GET /api/metrics/threshold-sweep`, `GET /api/metrics/cluster-quality`.

### 1.3 Cluster repair (M)

New `ClusterRepairService` consuming 1.2's unsupervised metrics:

- Flag clusters with `min_intra_score < τ` or detected bridge edges; auto-split when removing the weakest edge(s) disconnects the component and both halves are denser than the original (configurable `clustering.repair: {enabled, min_coherence, auto_split}`); otherwise queue for human review (Phase 2.2 consumes this queue).
- Extend `validate_clusters` ([wcc_clustering_service.py:251](../src/entity_resolution/services/wcc_clustering_service.py#L251)) from sample-based detection to full detection + repair hand-off; respect suppressed/confirmed edges from 0.1 (confirmed edges are never split points).

### 1.4 Schema-agnostic defaults (M)

New `FieldProfiler` (`learning/field_profiler.py`): sample N docs from the collection, classify each field (email/phone/person-name/org-name/address/date/numeric/id/free-text) via regex + statistics (cardinality, length distribution, token counts), and emit a generated similarity config (comparator + agreement bands + initial m/u priors per detected type). CLI `arango-er profile --collection X --emit-config`, MCP tool `profile_dataset` upgrade, and the data backing Phase 2.4's profiling screen. EM (1.1) then refines the priors — profiling chooses *comparators*, EM learns *weights*: together they remove the hand-written weights dict entirely.

### 1.5 Phonetic upgrade (S)

Add Metaphone/Double Metaphone and NYSIIS alongside Soundex (pure-Python implementations or the `jellyfish` lib as an optional extra) in `similarity_service`; expose as comparator options; default person-name profile uses Double Metaphone.

**Phase 1 exit criteria:** a user can point the system at an unlabeled collection, run profile → estimate → resolve, and get calibrated match probabilities plus a threshold-sweep report — zero hand-written weights. Published benchmark numbers in repo.

---

## Phase 2 — UI: From Results Viewer to Steward Workbench (target: v3.8.0)

Ordered so each screen consumes backend capabilities that already exist by the time it's built.

### 2.1 Threshold tuning with live preview (M) — *flagship UI feature*

New "Tuning" page:
- Dual-handle slider for low/high thresholds over a score-distribution histogram (`GET /api/metrics/score-distribution` — one AQL `COLLECT` over similarity edges, cheap).
- Live deltas as the handles move: pairs/clusters gained/lost (client-side from the histogram + threshold-sweep data, no per-drag API calls); when ground truth or accumulated verdicts exist, overlay live precision/recall/F1 from 1.2.
- "Pairs near boundary" panel sampling 10 pairs within ±0.05 of the handle (reuses `PairComparison`), so the user *sees* what a threshold means.
- "Apply" writes to config + optionally triggers re-cluster of affected edges only.

### 2.2 Cluster editing with audit trail (M)

On `ClusterDetailPage`/`ClusterGraph`:
- **Remove member** (select node → "doesn't belong") → suppress its edges via 0.1, re-cluster component.
- **Merge clusters** (from cluster list multi-select or detail page) → create confirmed edge between exemplars.
- **Split cluster** → UI surfaces the weakest-edge suggestion from 1.3; user confirms or drag-selects a partition.
- Every action writes an `_er_audit_log` doc `{actor, action, before, after, timestamp}`; new "History" tab on cluster detail renders it. Backend: new `ui/routes/curation.py`.
- Review-repair queue: clusters flagged by 1.3 appear in the Review page as a second tab ("Suspect clusters") beside the pair queue.

### 2.3 Review workflow depth (M)

- **Bulk actions:** filter-scoped "accept all LLM matches ≥ X confidence", "send band to LLM", CSV export of pending pairs. Backend batch endpoint applies 0.1 per pair.
- **Attribution:** reviewer identity on each verdict (from auth token name or a session prompt), timestamps surfaced in UI; optional verdict-confidence capture in `VerdictPanel`.
- **Flow:** auto-advance to next unreviewed after verdict; `?` shortcut help modal; pagination preserved across filter changes.
- **Golden records:** wire `ConflictResolver`/`MergeStrategySelector` to 0.3's survivorship parameters with preview → apply → audit.

### 2.4 Data profiling screen (S–M)

Renders `FieldProfiler` (1.4) output: per-field completeness, cardinality, type badges, sample values; "Generate config" button pre-fills the ConfigBuilder. Becomes the natural first screen for a new collection (onboarding fix).

### 2.5 UI foundation hardening (M, parallelizable with 2.1–2.4)

- **Tests:** Vitest + React Testing Library for components/hooks; Playwright smoke flow (load dashboard → run pipeline against docker ArangoDB → review a pair → verdict applied). Wire into CI.
- **Contract:** generate the API client from `openapi.json` (openapi-typescript + fetch wrapper), delete hand-written duplicate types, remove the `pairs|verdicts|items` / `record_a|doc_a` defensive shims by fixing the backend response models.
- **Performance:** batch endpoint for pair details (kills 10-requests-per-page in `PairComparison`); `@tanstack/react-virtual` on cluster/review tables.
- **Access:** aria labels on interactive elements, focus traps in modals, non-color status indicators; dark mode via Tailwind `dark:` + theme toggle (design tokens already centralized enough to make this cheap).
- **API:** restrict CORS methods/headers, add simple rate limiting middleware, request size limits.

**Phase 2 exit criteria:** a data steward can profile a collection, tune thresholds against live metrics, review pairs in bulk with attribution, repair clusters, and publish golden records — all in the UI, all audited.

---

## Phase 3 — Graph-Native Differentiation (target: v4.0)

The capabilities no competitor (open-source) has; sequenced after Phases 0–2 because each needs the closed loop, calibrated scores, and evaluation metrics to demonstrate its value.

### 3.1 Relationship features in similarity scoring (L)

New `GraphContextSimilarity` (`similarity/graph_context.py`):
- Per candidate pair, compute graph evidence via AQL k-hop traversal: shared-neighbor count/Jaccard over configured edge collections (shared employer, address, device, phone), shortest-path existence ≤ k through non-similarity edges.
- Enters the FS model as additional comparison fields with their own EM-learned m/u — so graph evidence is calibrated, not bolted on.
- Config: `similarity.graph_context: {edge_collections, max_hops, features}`.
- **Explainability payoff:** `explain_match` (MCP + UI `ExplainMatchModal`) gains path evidence — "both linked to Acme Corp (employer) and 12 Main St (address)" — rendered as a mini-graph. This is the path-based explanation modality Splink structurally cannot offer.

### 3.2 Collective / iterative resolution (L)

Building on 3.1: after each clustering pass, merged entities change the graph (cluster members share neighbors) → re-score candidate pairs whose graph features changed → new edges → incremental re-cluster → repeat until fixpoint or max-rounds. Implemented as an optional pipeline stage `collective: {enabled, max_rounds}` using the scoped re-clusterer from 0.1. Benchmark vs single-pass on relationship-rich datasets; publish the delta.

### 3.3 Incremental cluster maintenance (M–L)

Extend `IncrementalResolver` from "resolve one record" to "maintain clusters": new/updated record → block → score (with graph context) → join/create/merge clusters via the 0.1 machinery, honoring human-confirmed/suppressed edges as hard constraints (Zingg Enterprise's "living clusters", Senzing's sequence-neutrality). Ship as `arango-er watch` (poll or changes-API driven) and a `resolve_and_commit` MCP tool.

### 3.4 Graph-embedding blocking (M)

Productize `Node2VecEmbeddingService` as a real blocking strategy: embeddings written to records, ANN via the existing vector index, evaluated through the A/B harness against attribute-embedding blocking. Document the scale envelope honestly (current implementation is O(n²)-memory; acceptable for ≤100K-node graphs, with GraphSAGE/ArangoGraphML as the scale path). Publishable as a novel-capability writeup — no cited prior work uses graph embeddings for blocking.

**Phase 4.0 framing:** v4.0 = "the ER system that uses your graph as evidence" — collective resolution + path explanations + incremental maintenance, with benchmark numbers proving the graph lift.

---

## Phase 4 — Production Operations (continuous, no release gate)

| Item | Size | Notes |
|---|---|---|
| CI gates: `--cov-fail-under=70`, mypy, flake8, bandit in GitHub Actions | S | Makefile targets exist; wire into workflow |
| Integration-test CI job with dockerized ArangoDB | S | `scripts/run_tests_with_temp_arango.sh` already does this locally |
| Dockerfile + published image for UI/MCP server; compose service entry | S–M | closes the "library-only" deployment gap |
| Structured JSON logging option + Prometheus `/metrics` on the UI server (runs, durations, LLM cost, queue depth) | M | extend `utils/logging.py`; `prometheus-client` optional extra |
| Schema versioning: `_er_meta` collection with schema version + idempotent migration runner | M | needed before 3.x→4.0 collection changes (audit log, model params, term frequencies) |
| Scripts cull: keep CI/Makefile-referenced + benchmarks; archive the rest under `scripts/archive/` with a README | S | |
| docs/archive consolidation; README badges; align requirements.txt with extras (or delete it) | S | |

---

## Dependency map and suggested order

```
0.1 feedback loop ──┬─→ 2.2 cluster editing ──→ 3.2 collective ER
0.2 honest scoring ─┼─→ 1.1 EM ──→ (default FS scoring) ──→ 3.1 graph features
0.3 golden records ─┼─→ 2.3 review workflow (golden record apply)
0.5 LLM hardening ──┘
1.2 evaluation ──→ 2.1 threshold tuner, 1.3 cluster repair ──→ 2.2 repair queue
1.4 profiler ──→ 2.4 profiling screen
0.1 + 1.1 ──→ 3.3 incremental maintenance
2.5 UI foundation: parallel with all of Phase 2
Phase 4: parallel with everything
```

Recommended execution: **Phase 0 as one milestone** (it's mostly S/M items and every later phase depends on it), then 1.1+1.2 together, then split effort between Phase 2 (UI) and remaining Phase 1, then Phase 3 as the v4.0 headline.

## Risks

- **EM on real-world skew (1.1):** EM can converge to degenerate solutions on highly imbalanced candidate sets. Mitigation: Splink-style per-field estimation passes, sane priors from the profiler, and the evaluation harness as a regression gate.
- **Scoped re-clustering correctness (0.1):** component-local WCC must produce identical results to global re-runs. Mitigation: property-based test comparing scoped vs full re-cluster on random graphs.
- **UI scope creep (Phase 2):** the tuner and cluster editing are each demo-defining; resist polishing past "works and is audited" until Phase 3 ships.
- **Behavior changes for existing users (0.2, 1.1):** keep `weighted_heuristic` available and config-selectable through 4.0; document migration in `MIGRATION_GUIDE_V4.md`.
