# Comprehensive Project Review — June 2026

**Scope:** Full review of the arango-entity-resolution project (v3.5.1): core ER pipeline, AI/ML capabilities, UI, engineering quality, and a gap analysis against the 2025–2026 state of the art (Splink, Zingg, Senzing, Quantexa, Tamr, AWS Entity Resolution, recent LLM-ER research).

**Verdict in one paragraph:** This is a genuinely strong, well-engineered system — the blocking architecture, ArangoDB-native integration, MCP server, and configurability are competitive with or better than open-source peers. Its three biggest liabilities are: (1) the matching core is **rule-based with hardcoded weights** — there is no parameter learning (EM), no calibration, and no learned models, which is the defining capability gap vs Splink/Zingg; (2) the **feedback/review loop doesn't close where it matters** — human verdicts can re-tune LLM routing thresholds, but never change edges or clusters; (3) the **UI is functional but utilitarian** — it lacks the threshold-tuning-with-live-metrics, cluster editing (merge/split), and steward-workflow features that define best-in-class ER tools. The project's largest untapped advantage is the one thing competitors can't copy: it lives inside a graph database, yet it does not use graph context (relationships, collective resolution, same-engine analytics) as match evidence.

---

## 1. Strengths

### Core pipeline
- **Multi-strategy blocking orchestration** ([orchestrator.py](../src/entity_resolution/core/orchestrator.py)) is excellent: clean `BlockingStrategy` interface, union/intersection merge semantics, per-pair provenance (`sources`), consistent stats. Eight strategies (exact/COLLECT, BM25, vector/ANN, LSH, geographic, graph-traversal, shard-parallel, hybrid) is broader coverage than Splink or Zingg offer.
- **Batch similarity service** is well optimized: batched document fetches cut query counts from 100K+ to dozens ([batch_similarity_service.py:176-183](../src/entity_resolution/services/batch_similarity_service.py)); realistic ~100K pairs/sec throughput.
- **Pluggable clustering backends** (union-find, DFS, scipy sparse, AQL graph, GAE) with auto-selection by edge count — a thoughtful scalability story.
- **Config system** ([er_config.py](../src/entity_resolution/config/er_config.py)) is type-safe, validated, supports computed fields with AQL-injection guards, YAML/JSON.
- **Cross-collection matching and incremental single-record resolution** exist — many OSS competitors have neither.

### AI/ML
- **Embedding service** is production-grade: multi-resolution (coarse+fine) two-tier blocking, lazy model loading, device fallback (cuda→mps→cpu), OOM guards, deterministic tuple serialization, rich metadata for reproducibility.
- **Native vector index posture is correct**: strict ArangoDB 3.12+ `APPROX_NEAR_COSINE` with auto-derived IVF params and clear errors instead of silent brute-force fallback ([ann_adapter.py](../src/entity_resolution/similarity/ann_adapter.py)).
- **LLM verification design is sound**: only calls the LLM in the uncertain band (0.55–0.80), multi-provider via litellm, graceful fallback on API failure, batch mode.
- **MCP server** (15 tools, versioned response envelopes, bearer-token auth for SSE) is a real differentiator — almost no ER system has first-class AI-agent integration; Senzing only shipped theirs in 2026.

### UI
- Solid modern stack: React 19, TanStack Query, Tailwind 4, strict TypeScript (`noUncheckedIndexedAccess` on), xyflow graph visualization, WebSocket pipeline streaming with live stage progress, keyboard shortcuts (M/N/S) in the review queue, error boundaries, consistent empty/loading states.

### Engineering
- ~35K SLOC src with ~37K SLOC tests (1:1 ratio, 83 test files); robust conftest (env isolation, Docker container discovery); modern pyproject.toml packaging with clean optional extras; pre-commit secret scanning and pre-push test gate; environment-based credentials with constant-time token comparison; no AQL injection found (names validated, expressions sanitized).

---

## 2. Critical Findings (correctness bugs and broken promises)

These are concrete defects verified in the code, ordered by severity.

### 2.1 The "Fellegi-Sunter" scorer is not actually probabilistic
[similarity_service.py:571-652](../src/entity_resolution/services/similarity_service.py#L571-L652)

The per-field log-likelihood ratios are correct, but:
- An ad-hoc `importance` multiplier is applied to each field's LLR (lines 608–611), which has no Bayesian justification — true FS sums unweighted LLRs.
- `m_prob`/`u_prob` are **hardcoded defaults** (0.8 / 0.05) per field. There is no EM estimation from data — the core feature that makes Splink work unsupervised.
- The `confidence` value (lines 625–630) is an arbitrary linear scaling, not a posterior probability, yet it is surfaced to the UI and review queue as if it were calibrated. (The LLM uncertain band routes on the raw similarity score — a second uncalibrated number — so neither routing input is a probability.)

**Impact:** match decisions are heuristic similarity scores wearing a probabilistic label. On datasets with different match prevalence, thresholds won't transfer and accuracy claims can't be defended.

### 2.2 The human/LLM feedback loop closes for thresholds only — never for edges or clusters
[feedback.py](../src/entity_resolution/reasoning/feedback.py)

Verdicts (LLM and human corrections) are persisted, queryable, and counted, and one consumer does exist: `ThresholdOptimizer` ([feedback.py:261](../src/entity_resolution/reasoning/feedback.py#L261)) is a real implementation — isotonic regression with a percentile fallback — that derives new LLM low/high thresholds from accumulated verdicts, exposed via `POST /api/review/{collection}/optimize` and auto-refreshed by `AdaptiveLLMVerifier`. But that is the loop's only closed arc, and it tunes *future LLM routing*, not existing results. A human marking a pair "not a match" does not suppress the similarity edge, does not trigger re-clustering, and changes nothing the user can see. The review UI therefore still creates the *appearance* of human-in-the-loop ER without the substance where it matters most: the resolved data itself.

### 2.3 Legacy `GoldenRecordService` is a skeleton still exported in the public API
[golden_record_service.py:134](../src/entity_resolution/services/golden_record_service.py#L134) — `_retrieve_cluster_records` is `return []  # Placeholder`.

The functional path is `GoldenRecordPersistenceService` (generic, idempotent, well-designed). But both are exported from `entity_resolution/__init__.py`, and the legacy one silently produces empty golden records rather than failing. Anyone following older docs/examples gets garbage with no error. The legacy class should be deleted or made to raise.

### 2.4 GraphRAG creates self-loop edges — provenance is lost
[graph_rag.py:244-246](../src/entity_resolution/reasoning/graph_rag.py#L244-L246)

```python
"_from": f"{self.entity_collection}/{matched_key}",
"_to":   f"{self.entity_collection}/{matched_key}",   # self-loop
```

Extracted-entity link edges point from the matched entity to itself; the source document is only a string attribute. The knowledge graph cannot be traversed from documents to entities — the core GraphRAG promise.

### 2.5 No cluster repair / transitive-closure control
Clustering is pure WCC transitive closure. If A≈B and B≈C, then A–C are co-clustered even when A and C are clearly different entities. There is no intra-cluster coherence check, no cluster splitting, and no edge-confidence weighting at cluster time. This is the classic precision killer for WCC-based ER, and SOTA systems all mitigate it.

### 2.6 Smaller verified defects
- **LLM JSON parse fallback silently fabricates a verdict** from the raw score when the LLM returns non-JSON ([llm_verifier.py:256-266](../src/entity_resolution/reasoning/llm_verifier.py)) — should retry or escalate, not guess. (An empty fenced block doesn't crash fence-stripping, but it falls into the same fabrication path.)
- **Tuple serializer field weights are inert**: `apply_weights` defaults to False and is never enabled anywhere, so configured embedding field weights do nothing ([tuple_embedding_serializer.py:239-246](../src/entity_resolution/services/tuple_embedding_serializer.py)).
- **No LLM cost controls anywhere**: no token counting, budgets, or cost estimation. A 10M-record run with a wide uncertain band can rack up thousands of dollars invisibly.
- **docker-compose.test.yml hardcodes a password** (line 9) instead of `${ARANGO_ROOT_PASSWORD:?}`.

---

## 3. Gap Analysis vs State of the Art

Benchmarked against the 2025–2026 capability bar (Splink 4/5, Zingg 0.6 + Enterprise, Senzing v4, Quantexa, Tamr Curator Hub, AWS ER, current LLM-ER research).

| # | Capability | SOTA holder | This project |
|---|-----------|-------------|--------------|
| 1 | Unsupervised EM training of m/u + term-frequency adjustments | Splink | ❌ hardcoded weights |
| 2 | Learned/verified blocking | Zingg blocking trees | ⚠️ many strategies, none learned; A/B harness exists but manual |
| 3 | Active-learning labeling loop | Zingg, dedupe | ⚠️ verdicts re-tune LLM thresholds (isotonic); edges/clusters never change (§2.2) |
| 4 | Threshold tuning vs live precision/recall | Splink charts | ❌ none |
| 5 | Cluster QA without ground truth (graph metrics, coherence) | Splink `compute_graph_metrics` | ❌ none; no cluster repair (§2.5) |
| 6 | Cluster visualization dashboard | Splink Cluster Studio, Linkurious | ⚠️ good per-cluster graph; no corpus-level QA view |
| 7 | Steward queue: merge/split, survivorship overrides, audit trail | Reltio, Tamr | ⚠️ review queue exists; no cluster editing, no audit, single-user |
| 8 | WHY / WHY-NOT explainability per decision | Senzing | ⚠️ field score breakdown + LLM text; no structured why-not, no waterfall view |
| 9 | Incremental, sequence-neutral resolution with cluster updates | Senzing; Zingg Enterprise | ⚠️ single-record resolve exists; no incremental cluster merge/unmerge |
| 10 | Entity-centric matching (records vs entities, not records vs records) | Senzing, Quantexa, Tilores | ❌ record-pairwise only |
| 11 | **Relationship/collective matching using graph context** | Getoor lineage; TigerGraph kits | ❌ **the graph-native differentiator, unused** |
| 12 | Same-engine post-ER analytics (fraud rings, householding) | Neo4j, TigerGraph | ⚠️ possible in ArangoDB, not productized |
| 13 | LLM matcher tier with cost engineering (batching, model routing) | ComEM, AnyMatch, libem | ⚠️ LLM verify exists, zero cost control |
| 14 | ER-for-GraphRAG (resolver inside KG construction) | neo4j-graphrag-python, Senzing ERKG | ⚠️ exists but buggy (§2.4) and prototype-grade |
| 15 | Privacy: PII masking before LLM calls, erasure propagation | Senzing | ❌ records sent verbatim to external LLMs |
| 16 | Evaluation on standard benchmarks (WDC Products hard splits, OpenSanctions Pairs) | research norm | ❌ no published accuracy numbers |

**Strategic whitespace this project is uniquely positioned to own** (verified: no major OSS/commercial player has these):
1. **Collective/iterative graph-context resolution** — using shared neighbors, relationship paths, and prior merges as match evidence. Only Senzing has this commercially; no OSS tool does. ArangoDB is the natural home for it.
2. **Graph-embedding blocking** — node2vec/GraphSAGE embeddings + attribute embeddings in one engine for blocking; no widely-cited prior work exists.
3. **Path-based explainability** — "matched because both share device D and address A" is an explanation modality Splink structurally cannot offer.

---

## 4. UI Review (your specific concern)

The UI is **architecturally healthy but product-thin**: a solid v0.x foundation that reads as an admin panel rather than a data-steward workbench. Specifics:

### What's holding it back most
1. **It's read-only where it matters.** Clusters cannot be edited — no "remove this record from cluster," no "merge these two clusters," no outlier flagging. The ConflictResolver component renders but its callback is a stub ([GoldenRecordsPage.tsx](../ui/src/pages/GoldenRecordsPage.tsx)); merge preview has no apply/commit. For an ER product, cluster curation is the product.
2. **No what-if threshold tuning.** Thresholds live in config; there is no slider with live "47 more matches / 12 likely false positives at 0.70" preview. This is Splink's most-loved feature and the highest-impact single addition.
3. **Review queue lacks workflow depth**: no bulk actions ("accept all LLM-confident matches"), no audit trail (who/when), no reviewer assignment, no "jump to next unreviewed," confidence not captured on human verdicts.
4. **Verdicts don't change the data** (backend gap §2.2 surfacing in UI) — users will review pairs and see no effect on edges or clusters, which destroys trust in the tool.

### Quality/polish gaps
- **Zero frontend tests** (no unit, no E2E) and zero backend route tests for the UI API.
- **Zero accessibility work**: no aria attributes anywhere in `ui/src`, color-only status signaling, no focus management in modals.
- **No dark mode, minimal responsiveness** (4 `sm:` breakpoints total; fixed sidebar; no mobile nav).
- **Performance**: no virtualization on cluster/review tables; `PairComparison` fires one API call per visible pair (10 calls per page) instead of batch fetching.
- **API contract drift**: components defensively handle `pairs|verdicts|items` and `record_a|doc_a` response shapes ([ReviewQueue.tsx:62-63](../ui/src/components/review/ReviewQueue.tsx)) — the generated OpenAPI schema exists but isn't the single source of truth.
- **API hardening is thin**: CORS origins default to same-origin (empty allowlist), but `allow_methods`/`allow_headers` are `*` for any configured origin; auth is a single optional shared bearer token with no user identity (and the frontend has no concept of it); no rate limiting.

### Missing screens a best-in-class ER UI would have
- Data quality profiling (field completeness/distributions → blocking-field recommendations)
- Corpus-level cluster QA dashboard (size distribution, low-coherence clusters surfaced for review)
- Lineage view: blocking → scoring → clustering → review decisions per entity
- Global record search across clusters/verdicts/golden records
- Config presets ("strict person matching", "fuzzy company matching"), config diff/versioning per run, YAML import
- Settings page, shortcuts help (`?`), onboarding for empty states

**Design maturity: ~6–7/10.** The right move is not a visual reskin — it's adding the three or four interactive workflows (threshold tuning, cluster editing, closed-loop review, profiling) that make the UI an ER tool rather than a results viewer.

---

## 5. Engineering & Operations Findings

**Good:** modern packaging, 1:1 test ratio, secret hygiene, deprecation discipline, GitHub Actions unit-test CI.

**Needs work:**
- **CI gates are soft**: no coverage threshold, no mypy, no lint, no bandit in CI (lint and mypy exist as Makefile targets but aren't wired in; coverage and bandit targets don't exist at all). Coverage claims (67%) are point-in-time, not protected.
- **No deployment story for the service itself**: docker-compose deploys only ArangoDB; there is no Dockerfile for the FastAPI UI / MCP server, no K8s manifests.
- **No observability**: stdout logging only — no JSON logs, no Prometheus metrics, no OpenTelemetry.
- **No schema/migration versioning** for the ArangoDB collections the system creates.
- **Repo clutter**: `coverage.json` (269KB) tracked in git; three overlapping version files (CHANGELOG / VERSION_HISTORY / VERSION_SUMMARY); 52 scripts in `scripts/` of which a large fraction are one-off bootstrap/audit artifacts; 48 archived audit docs; 39 broken tests in `tests/archive_broken/`; stray `~/` directory in repo root.
- **Dual legacy/new code paths** (blocking_service vs strategies/, GoldenRecordService vs PersistenceService, EntityResolutionPipeline vs ConfigurableERPipeline) — deprecations exist but the legacy paths are still exported and documented in places.

---

## 6. What "Best" Requires — Prioritized Recommendations

### Tier 0 — Fix what's broken (correctness, trust)
1. **Close the feedback loop**: human "not a match" → remove/zero the edge → incrementally re-cluster the affected component → reflect in UI. This single change makes the review queue real.
2. **Fix the FS scorer**: drop the importance multiplier from the LLR sum (or document it as a separate heuristic mode); make confidence an honest calibrated probability (isotonic/Platt on labeled or EM-estimated data).
3. **Delete or hard-fail the skeleton `GoldenRecordService`**; make `GoldenRecordPersistenceService` the only exported path.
4. **Fix the GraphRAG self-loop edge** (document → entity provenance edges).
5. **Harden LLM verify**: retry-on-parse-failure, per-run token/cost budget with abort, cost reporting in pipeline results.

### Tier 1 — Close the SOTA gap in the matching core
6. **EM parameter estimation** for m/u probabilities (Splink-style, unsupervised) + term-frequency adjustments. This is the highest-leverage algorithmic addition; it converts the system from "manually tuned" to "self-tuning."
7. **Cluster QA + repair**: intra-cluster coherence metrics, automatic flagging of low-coherence clusters, splitting via edge-confidence thresholds; expose Splink-style graph metrics without ground truth.
8. **Evaluation harness as a first-class feature**: precision/recall/F1 across all thresholds against labeled pairs; benchmark runs on WDC Products hard splits / OpenSanctions Pairs and publish numbers.
9. **Schema-agnostic defaults**: field-type detection → default comparators and weights, so new datasets work without hand-writing a weights dict.

### Tier 2 — Make the UI a steward workbench
10. **Threshold tuning with live preview** (slider + immediate match-count/metric deltas; pairs near boundary shown).
11. **Cluster editing**: split/merge/remove-member with audit trail, wired to the closed feedback loop from Tier 0.
12. **Review workflow**: bulk actions, reviewer attribution + timestamps, next-unreviewed navigation, verdict confidence capture.
13. **Data profiling screen** + corpus-level cluster QA dashboard.
14. **Foundation work**: frontend tests (Playwright + component), accessibility pass, batch pair fetching, table virtualization, dark mode, generated-client enforcement to kill response-shape drift.

### Tier 3 — Own the graph-native whitespace (differentiation)
15. **Collective/relationship-based matching**: shared-neighbor and path features as similarity signals; iterative re-resolution where merges create new evidence. No OSS competitor has this; it's the reason to choose a graph DB for ER.
16. **Incremental cluster maintenance**: new records join/merge/split existing clusters (sequence-neutral), instead of full re-clustering.
17. **Path-based explanations** in `explain_match` and the UI ("both share address A and device D").
18. **Graph-embedding blocking** productized (node2vec exists; integrate as a blocking strategy with eval).

### Tier 4 — Production operations
19. CI gates (coverage ≥70%, mypy, lint, bandit), Dockerfile + container image for UI/MCP server, Prometheus metrics + JSON logging, schema versioning/migrations, PII masking option before LLM calls, repo cleanup (tracked artifacts, version-file consolidation, scripts cull).

---

## 7. Suggested Sequencing

If the goal is "best ER system on a graph database," the order that maximizes compounding value:

1. **Tier 0 entirely** (small, surgical, restores trust) →
2. **EM estimation + evaluation harness** (Tier 1 #6, #8 — gives you the metrics to prove every later improvement) →
3. **UI threshold tuning + cluster editing + closed-loop review** (Tier 2 #10–12 — now powered by real metrics) →
4. **Collective graph matching + incremental clustering** (Tier 3 — the differentiator, marketed with benchmark numbers from step 2).

Tier 4 items can run continuously in parallel as engineering hygiene.
