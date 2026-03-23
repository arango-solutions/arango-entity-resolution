# Runtime Health CI Runbook

This runbook documents the Phase 0 runtime-health workflow for embedding runtime readiness.

It covers:
- collecting runtime diagnostics
- exporting telemetry snapshots
- storing/updating baselines
- comparing against baselines
- CI gating with optional fail-on-regression behavior
- benchmarking runtime setup latency and fallback behavior
- comparing quality metrics and integrating quality checks into gate flow

---

## Prerequisites

- A valid pipeline config file (YAML/JSON) with an `entity_resolution.embedding` section.
- CLI installed (`arango-er`).
- Access to the target database environment.

Optional:
- Existing baseline registry JSON file for compare/gate commands.

---

## Command Reference

### 1) Runtime diagnostics (no files written)

```bash
arango-er runtime-health -c config.yaml
```

Strict startup check:

```bash
arango-er runtime-health -c config.yaml --startup-mode strict
```

---

### 2) Export runtime diagnostics snapshot artifact

```bash
arango-er runtime-health-export \
  -c config.yaml \
  --output-dir artifacts/runtime \
  --filename-prefix runtime_health
```

---

### 3) Capture or update baseline in registry

```bash
arango-er runtime-health-baseline \
  -c config.yaml \
  --registry-file artifacts/runtime/runtime_registry.json \
  --label dev-mac
```

---

### 4) Compare current snapshot to baseline

```bash
arango-er runtime-health-compare \
  -c config.yaml \
  --registry-file artifacts/runtime/runtime_registry.json \
  --label dev-mac \
  --latency-regression-pct 20
```

Export compare artifacts (`json`, `md`, `csv`):

```bash
arango-er runtime-health-compare \
  -c config.yaml \
  --registry-file artifacts/runtime/runtime_registry.json \
  --label dev-mac \
  --output-dir artifacts/runtime/compare \
  --filename-prefix runtime_compare
```

---

### 5) One-shot CI gate (snapshot + compare + optional artifacts)

```bash
arango-er runtime-health-gate \
  -c config.yaml \
  --registry-file artifacts/runtime/runtime_registry.json \
  --label ci-linux \
  --latency-regression-pct 20 \
  --fail-on-regression
```

With report artifacts:

```bash
arango-er runtime-health-gate \
  -c config.yaml \
  --registry-file artifacts/runtime/runtime_registry.json \
  --label ci-linux \
  --output-dir artifacts/runtime/gate \
  --filename-prefix runtime_gate \
  --fail-on-regression
```

---

### 6) Benchmark runtime-health latency (repeat probes)

```bash
arango-er runtime-health-benchmark \
  -c config.yaml \
  --repeats 10
```

With persisted benchmark artifact:

```bash
arango-er runtime-health-benchmark \
  -c config.yaml \
  --profile ci-linux-cpu \
  --startup-mode strict \
  --warmup-runs 2 \
  --repeats 10 \
  --output-dir artifacts/runtime/benchmark \
  --filename-prefix runtime_benchmark
```

---

### 7) Initialize a benchmark corpus scaffold

```bash
arango-er runtime-quality-corpus-init \
  --output artifacts/quality/runtime_quality_corpus.json
```

---

### 8) Generate quality metrics from corpus

```bash
arango-er runtime-quality-benchmark \
  --corpus artifacts/quality/runtime_quality_corpus.json \
  --model-name all-MiniLM-L6-v2 \
  --device auto \
  --output-dir artifacts/quality \
  --filename-prefix current_metrics
```

---

### 9) Bootstrap/update stable baseline metrics (one command)

```bash
arango-er runtime-quality-baseline \
  --corpus artifacts/quality/runtime_quality_corpus.json \
  --model-name all-MiniLM-L6-v2 \
  --device auto \
  --output-dir artifacts/quality
```

This writes `artifacts/quality/baseline_metrics.json` by default.

---

### 10) Compare quality metrics against baseline

```bash
arango-er runtime-quality-compare \
  --current-metrics artifacts/quality/current_metrics.json \
  --baseline-metrics artifacts/quality/baseline_metrics.json \
  --cosine-drift-max 0.01 \
  --topk-overlap-min 0.95
```

Fail build on quality regression:

```bash
arango-er runtime-quality-compare \
  --current-metrics artifacts/quality/current_metrics.json \
  --baseline-metrics artifacts/quality/baseline_metrics.json \
  --fail-on-regression
```

---

## First-Run Baseline Bootstrap

For new environments with no baseline yet:

```bash
arango-er runtime-health-gate \
  -c config.yaml \
  --registry-file artifacts/runtime/runtime_registry.json \
  --label ci-linux \
  --bootstrap-baseline
```

This writes a baseline when no matching key exists and returns `baseline_bootstrapped: true`.

---

## Exit Codes (gate command)

- `0`: success (or no gated regressions)
- `1`: command/runtime failure
- `2`: regression detected when `--fail-on-regression` is enabled

When quality inputs are supplied (`--quality-current-metrics` or `--quality-corpus`),
`--fail-on-regression` still exits `0` unless `quality_gate.regressions.quality_regression`
is true.

---

## Suggested CI Pattern

1. Bootstrap once per environment/label:
   - run gate with `--bootstrap-baseline`
2. Normal CI runs:
   - run gate with `--fail-on-regression`
3. Release/nightly jobs:
   - run gate with `--output-dir` to publish compare artifacts
   - run benchmark command with `--output-dir` to publish latency/fallback trend artifacts

---

## CoreML Runtime Recommendations (Apple Silicon)

Use these as starting points for `entity_resolution.embedding` when `runtime: onnxruntime`.

`dev-mac` (interactive local development):

```yaml
embedding:
  runtime: onnxruntime
  provider: coreml
  startup_mode: permissive
  coreml_use_basic_optimizations: true
  coreml_warmup_runs: 10
  coreml_max_p95_latency_ms: 80.0
  coreml_warmup_batch_size: 8
  coreml_warmup_seq_len: 128
```

Why:
- keeps local startup resilient while still preferring CoreML
- allows a looser warmup threshold to reduce unnecessary fallback during development

`ci-mac` (gating and reproducible checks):

```yaml
embedding:
  runtime: onnxruntime
  provider: coreml
  startup_mode: strict
  coreml_use_basic_optimizations: true
  coreml_warmup_runs: 10
  coreml_max_p95_latency_ms: 65.0
  coreml_warmup_batch_size: 8
  coreml_warmup_seq_len: 128
```

Why:
- enforces stricter CoreML readiness and catches degraded partitioning early
- keeps warmup policy aligned with benchmark thresholds used in CI reports

Operational notes:
- If `coreml_warmup_p95_latency_ms` repeatedly exceeds threshold, the backend falls back to CPU and records `last_fallback_reason`.
- Tune `coreml_max_p95_latency_ms` using your own baseline artifacts (`dev-mac` and `ci-mac` should keep separate baselines).
- Keep `coreml_use_basic_optimizations: true` unless you are explicitly testing optimization-level experiments.

Quick check (CoreML telemetry fields only):

```bash
arango-er runtime-health -c config.yaml | jq '{
  runtime,
  requested_provider,
  resolved_provider,
  health: {
    provider: .health.provider,
    active_session_providers: .health.active_session_providers,
    session_optimization_level: .health.session_optimization_level,
    coreml_warmup_p95_latency_ms: .health.coreml_warmup_p95_latency_ms,
    coreml_max_p95_latency_ms: .health.coreml_max_p95_latency_ms,
    fallback_count: .health.fallback_count,
    last_fallback_reason: .health.last_fallback_reason
  },
  telemetry: {
    provider_used: .telemetry.provider_used,
    fallback_count: .telemetry.fallback_count,
    fallback_occurred: .telemetry.fallback_occurred,
    last_fallback_reason: .telemetry.last_fallback_reason,
    coreml_warmup_p95_latency_ms: .telemetry.coreml_warmup_p95_latency_ms,
    coreml_max_p95_latency_ms: .telemetry.coreml_max_p95_latency_ms,
    session_optimization_level: .telemetry.session_optimization_level
  }
}'
```

---

## End-to-End Example (Single Reference Flow)

```bash
# 1) Capture baseline (first-time or intentional re-baseline)
arango-er runtime-health-baseline \
  -c config.yaml \
  --registry-file artifacts/runtime/runtime_registry.json \
  --label ci-linux

# 2) Compare against baseline and export compare report artifacts
arango-er runtime-health-compare \
  -c config.yaml \
  --registry-file artifacts/runtime/runtime_registry.json \
  --label ci-linux \
  --latency-regression-pct 20 \
  --output-dir artifacts/runtime/compare \
  --filename-prefix runtime_compare

# 3) Enforce CI gate
arango-er runtime-health-gate \
  -c config.yaml \
  --registry-file artifacts/runtime/runtime_registry.json \
  --label ci-linux \
  --latency-regression-pct 20 \
  --fail-on-regression

# 3a) Generate current quality metrics from benchmark corpus
arango-er runtime-quality-benchmark \
  --corpus artifacts/quality/runtime_quality_corpus.json \
  --model-name all-MiniLM-L6-v2 \
  --device auto \
  --output-dir artifacts/quality \
  --filename-prefix current_metrics

# 3a.1) Bootstrap/update stable baseline metrics from corpus (first time or re-baseline)
arango-er runtime-quality-baseline \
  --corpus artifacts/quality/runtime_quality_corpus.json \
  --model-name all-MiniLM-L6-v2 \
  --device auto \
  --output-dir artifacts/quality

# 3b) Enforce CI gate with quality metrics included
arango-er runtime-health-gate \
  -c config.yaml \
  --registry-file artifacts/runtime/runtime_registry.json \
  --label ci-linux \
  --quality-current-metrics artifacts/quality/current_metrics.json \
  --quality-baseline-metrics artifacts/quality/baseline_metrics.json \
  --quality-cosine-drift-max 0.01 \
  --quality-topk-overlap-min 0.95 \
  --fail-on-regression

# 3b.1) Alternative: compute current quality metrics inline from corpus
arango-er runtime-health-gate \
  -c config.yaml \
  --registry-file artifacts/runtime/runtime_registry.json \
  --label ci-linux \
  --quality-corpus artifacts/quality/runtime_quality_corpus.json \
  --quality-model-name all-MiniLM-L6-v2 \
  --quality-device auto \
  --quality-batch-size 32 \
  --quality-baseline-metrics artifacts/quality/baseline_metrics.json \
  --quality-cosine-drift-max 0.01 \
  --quality-topk-overlap-min 0.95 \
  --fail-on-regression

# 4) Record benchmark trend artifact
arango-er runtime-health-benchmark \
  -c config.yaml \
  --profile ci-linux-cpu \
  --startup-mode strict \
  --warmup-runs 2 \
  --repeats 10 \
  --output-dir artifacts/runtime/benchmark \
  --filename-prefix runtime_benchmark
```

### Platform Matrix Workflow

This repository includes a dedicated runtime matrix workflow:
- workflow: `.github/workflows/runtime-platform-matrix.yml`
- default lanes on push/PR: `linux-cpu`
- optional self-hosted lanes via manual dispatch: `apple-silicon`, `linux-gpu`

To run self-hosted lanes manually:
1. open GitHub Actions -> `Runtime Platform Matrix`
2. click `Run workflow`
3. set `enable_self_hosted=true`

Expected self-hosted labels:
- Apple Silicon runner: `self-hosted`, `macOS`, `ARM64`
- Linux GPU runner: `self-hosted`, `linux`, `x64`, `gpu`, `nvidia`

Workflow behavior notes:
- matrix runs are configured with branch-level concurrency (newer runs cancel older in-progress runs on the same ref)
- each matrix lane has a `30` minute timeout guard
- push/PR triggers are path-filtered to runtime benchmark/gate workflow, code, tests, and runbook files
- runtime matrix artifacts are best-effort (`if-no-files-found: ignore`) with `7` day retention
- each lane writes `artifacts/runtime/runtime_env_<platform>.json` with platform/runtime evidence (`python_version`, system/machine, torch availability + cuda/mps flags, and onnxruntime providers)
- quality-gate thresholds and pinned corpus/baselines are sourced from `ci/runtime-quality/quality_gate_policy.json`
- default `linux-cpu` lane executes corpus-driven `runtime-health-gate` with pinned artifacts and emits `artifacts/quality/quality_gate_linux-cpu.json`
- workflow fails fast if policy profiles are missing or if referenced corpus/baseline files do not exist
- runtime matrix unit checks include policy validator tests (`test_runtime_quality_policy_service.py`, `test_runtime_quality_policy_ci.py`)
- linux-cpu quality-gate lane generates an ephemeral ArangoDB password at runtime (no hardcoded credential in repository)
- prefer `ARANGO_ROOT_PASSWORD` as canonical for Docker-root auth; `ARANGO_PASSWORD` is supported only as a fallback alias

`runtime-health-gate` quality output includes `quality_gate.current_source`:
- `metrics_file` when using `--quality-current-metrics`
- `corpus_benchmark` when using `--quality-corpus`
- `--quality-baseline-metrics` is required whenever either quality current source is provided
- specify only one current source (`--quality-current-metrics` or `--quality-corpus`) per invocation
- corpus tuning flags (`--quality-model-name`, `--quality-device`, `--quality-batch-size`) require `--quality-corpus`

---

## Baseline Rotation Procedure

Use this flow for intentional runtime/quality re-baselines:

1. **Open a dedicated baseline PR**
   - include only baseline artifact updates and runbook/policy updates
   - do not bundle feature changes
2. **Approval signal**
   - require explicit reviewer acknowledgement in the PR (for example comment: `baseline-rotation-approved`)
   - merge only after this acknowledgement is present
3. **Artifact naming convention**
   - keep promoted stable files under `ci/runtime-quality/baselines/<profile>.json`
   - attach timestamped evidence artifacts in CI as `artifacts/quality/quality_gate_<profile>.json`
   - if storing historical baseline snapshots, use `baseline_<profile>_<YYYYMMDD>.json`
4. **Policy sync**
   - update `ci/runtime-quality/quality_gate_policy.json` only when thresholds or baseline paths intentionally change
   - record rationale in PR description (model/runtime change, platform drift, or corpus change)

---

## Notes

- `startup_mode=strict` is recommended for pre-release validation and CI gates.
- Use stable labels (for example `ci-linux`, `dev-mac`, `prod-apple-silicon`) for consistent baseline keys.
- Use `--profile` to tag benchmark artifacts by workload class (for example `ci-linux-cpu`, `ci-linux-gpu`, `dev-mac`).
- Re-baseline deliberately after expected runtime stack changes (driver/toolchain/model updates).
- Prefer `--warmup-runs` > 0 in CI benchmarks to reduce one-time initialization noise.
- Benchmark artifacts include `metadata.startup_mode` and `metadata.profile` for downstream grouping.
- Benchmark artifacts include `metadata.config.config_path` to trace the exact config used by each run.

