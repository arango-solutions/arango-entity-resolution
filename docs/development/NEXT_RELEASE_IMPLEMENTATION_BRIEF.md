# Next Release Implementation Brief

> Reconstructed from a prior planning discussion and captured here as a durable repo document.
> This is a forward-looking implementation brief, not the current shipped product contract.
> For the current shipped surface, see `README.md`, `docs/PRD.md`, and `VERSION_HISTORY.md`.

**Date:** 2026-03-08
**Status:** Draft — ready for implementation
**Scope:** Planned work beyond `v3.2.3`

---

## Overview

This brief specifies the changes needed for the next three releases of the project. It covers:

- cross-platform GPU-accelerated embedding inference for ONNX workloads (`cpu`, `coreml`, `cuda`, `tensorrt`)
- pluggable clustering backends (`python_union_find`, `python_sparse`, `aql_graph`, `gae_wcc`, `auto`)
- first-class local LLM support via `Ollama`

Each release section includes the current code state, exact diffs, new files, migration rules, and test locations so an implementer can start work without further research.

---

## Goals

- Add practical hardware acceleration where it materially helps: ONNX embeddings and future vector workflows.
- Formalize clustering as a backend-selectable capability instead of a binary implementation flag.
- Add first-class local LLM support for privacy-sensitive review workflows.
- Keep CPU, non-GAE, and hosted-LLM paths as stable defaults.
- Keep runtime selection explicit, observable, and reversible via feature flags.

---

## Architecture Decisions

### Hardware Acceleration Scope

Hardware acceleration should target embedding and vector-heavy workloads first.

Not a priority for:
- exact or BM25 blocking
- field transformers and string cleanup
- classical string similarity
- typical WCC clustering workloads

### Mac / Apple Silicon Support

This roadmap is a `hardware acceleration` plan, not a CUDA-only plan.

Supported runtime provider values:
- `cpu` — universal fallback
- `coreml` — Apple Silicon/macOS GPU acceleration path
- `cuda` — Linux NVIDIA GPU path
- `tensorrt` — optional Linux NVIDIA acceleration for selected high-volume models

`provider="auto"` resolves by platform:
- macOS Apple Silicon: `coreml` -> `cpu`
- Linux NVIDIA: `tensorrt` -> `cuda` -> `cpu`
- other platforms: `cpu`

> **Default change is deferred.** The default value for embedding execution remains CPU in
> `3.3.0`. `provider='auto'` is introduced as an opt-in value first. The default can be
> promoted only after Apple Silicon and Linux parity tests are confirmed passing in CI.
> Changing the default silently in `3.3.0` would alter runtime behavior for all users.

### Embedding Runtime Decision

- `3.3.0`: introduce an explicit embedding runtime/provider abstraction; add ONNX Runtime support as opt-in for ONNX models.
- `3.4.0`: promote ONNX Runtime as the primary runtime for ONNX workloads after compatibility and quality gates.
- `3.5.0`: add selective TensorRT optimization for high-throughput Linux NVIDIA workloads.

Rationale:
- current and planned models include ONNX-native paths (for example ColBERT and BERT ONNX variants)
- ONNX Runtime provides one API with platform-specific providers
- Apple Silicon support is strongest via CoreML execution provider
- Linux NVIDIA support is strongest via CUDA execution provider, with TensorRT as an optional optimization layer
- a single provider abstraction keeps fallback behavior and observability consistent across platforms

### Clustering Strategy

Clustering should move from a binary `use_bulk_fetch` flag to a named pluggable backend.

Supported backend values:
- `python_dfs` — existing bulk-fetch DFS implementation (default through 3.3.0)
- `python_union_find` — new portable local backend (introduced in 3.3.0, becomes default in 3.4.0)
- `python_sparse` — optional local sparse backend using scipy (new in 3.4.0)
- `aql_graph` — server-side AQL traversal (existing)
- `gae_wcc` — optional enterprise GAE (new in 3.5.0)
- `auto` — heuristic selection (new in 3.4.0, becomes default in 3.5.0)

> **Default changes are staged across releases.** `python_dfs` remains the effective
> default in `3.3.0` (via the `wcc_algorithm='python_dfs'` deprecation mapping) so
> existing cluster outputs are not altered. `python_union_find` becomes the explicit
> default only after parity tests pass. `backend='auto'` becomes the default only in
> `3.5.0` after both local backends are proven stable.

### Local LLM Decision

`Ollama` is already supported by `litellm` using model strings of the form `ollama/model_name`. The goal for `3.3.0` is to make this explicit, documented, and tested — not to add a new dependency. The proposed `LLMProviderConfig` gives users a structured way to express provider, model, and connection details without relying on implicit model-string conventions.

---

## Cross-Platform GPU Implementation Brief (Apple Silicon + Linux)

This section defines the implementation plan for GPU support on Apple Silicon macOS and Linux, aligned to active roadmap work and model priorities (GraphML, ColBERT, BERT ONNX).

### Scope and Non-Scope

In scope:
- ONNX embedding inference acceleration for Apple Silicon and Linux
- provider selection, fallback, observability, and rollout controls
- packaging and CI support for GPU-capable environments

Out of scope for this cycle:
- replacing all PyTorch paths immediately
- AMD/ROCm support as a required path
- automatic model graph rewrites beyond standard ONNX Runtime optimization levels

### Runtime and Provider Strategy

Primary runtime:
- `onnxruntime` via a provider abstraction layer

Provider priority:
- macOS Apple Silicon: `coreml` -> `cpu`
- Linux NVIDIA: `tensorrt` -> `cuda` -> `cpu` (TensorRT opt-in initially)

Fallback policy:
- provider initialization failures and unsupported op paths must fall back to `cpu`
- fallback events must be metered and surfaced in runtime stats

### Configuration Surface (planned)

Additions to `EmbeddingConfig`:
- `runtime`: `pytorch | onnxruntime`
- `provider`: `cpu | coreml | cuda | tensorrt | auto`
- `provider_options`: map for provider-specific knobs (for example precision and graph optimization mode)
- `onnx_model_path`: optional path for ONNX-specific deployment

Behavioral rules:
- `runtime='pytorch'` keeps current behavior unchanged
- `runtime='onnxruntime'` activates provider resolution and ONNX session options
- `provider='auto'` resolves by platform/provider priority table

### Work Packages

1) Compatibility and baselines
- inventory candidate models and ONNX opset compatibility
- establish CPU baselines for latency, throughput, and embedding quality
- create pass/fail matrix for CoreML and CUDA providers

2) Runtime abstraction
- add `EmbeddingInferenceBackend` interface for model load/infer/health/metadata
- implement `OnnxRuntimeEmbeddingBackend`
- preserve existing PyTorch backend behind same interface

3) Provider resolution and fallback
- centralize provider detection and resolver logic
- add deterministic fallback chain with typed errors
- emit `requested_provider` and `resolved_provider` in embedding metadata

4) Packaging and environment
- define platform extras (for example `gpu-mac`, `gpu-linux`)
- pin Linux NVIDIA compatibility matrix (ORT, CUDA, cuDNN, driver)
- document Apple Silicon/macOS minimum versions and CoreML caveats

5) Performance tuning
- benchmark batch-size and sequence-length sweeps by model/provider
- evaluate fp16 and TensorRT only where quality gates remain green
- publish tuned defaults per model and platform

6) Observability and reliability
- metrics: provider usage, fallback count, model load errors, p50/p95 latency, throughput
- startup healthchecks for provider readiness
- safe-mode feature flag to force CPU globally or per model

### Test and Acceptance Gates

Correctness:
- deterministic output shape and dtype checks across providers
- embedding quality drift gates using cosine similarity thresholds
- retrieval stability checks for ColBERT and BERT ranking outputs

Performance:
- per-platform throughput improvement vs CPU baseline for target models
- p95 latency targets for representative batch sizes

Reliability:
- fallback-to-CPU behavior verified for provider unavailability and unsupported ops
- startup healthcheck and degraded-mode behavior verified in CI/nightly

### Release Mapping

`3.3.0`:
- introduce runtime/provider config fields (CPU default)
- add ONNX Runtime backend as opt-in path
- add provider resolver and metadata fields
- add GPU smoke tests (mock/provider-availability focused)

`3.4.0`:
- promote `provider='auto'` where parity/quality/perf gates are green
- add Linux CUDA benchmark pipeline and Apple Silicon CoreML benchmark artifacts
- add rollout flags for per-model provider overrides

`3.5.0`:
- selective TensorRT optimization for highest-volume models
- optional `auto` tuning profiles by model family
- finalize operational playbooks for incident fallback and rollback

### Phase 0 Completion Package (Implemented)

This section records what is now implemented for Phase 0 and what remains for Phase 1+.

Completed implementation scope:
- runtime/provider configuration surface added in code (`runtime`, `provider`, `provider_options`, `onnx_model_path`, `startup_mode`)
- ONNX runtime backend scaffold added with provider resolution (`coreml`, `cuda`, `tensorrt`, `cpu`) and CPU fallback behavior
- embedding runtime setup integrated into pipeline execution with health and telemetry output
- startup policy controls implemented (`permissive` and `strict`)
- vector/LSH pipeline integration wired through config with embedding preflight diagnostics
- runtime telemetry snapshot export command implemented
- runtime baseline registry and compare workflow implemented
- runtime compare artifact export implemented (`json`, `md`, `csv`)
- one-shot runtime gate command implemented for CI with optional `fail-on-regression`
- baseline bootstrap behavior implemented for first-run environments (`--bootstrap-baseline`)
- operational runbook added (`docs/development/RUNTIME_HEALTH_CI_RUNBOOK.md`)

Phase 0 command surface now available:
- `arango-er runtime-health`
- `arango-er runtime-health-export`
- `arango-er runtime-health-baseline`
- `arango-er runtime-health-compare`
- `arango-er runtime-health-gate`
- `arango-er status --include-runtime-health --config <path>`

Phase 0 acceptance summary:
- [DONE] provider/device resolution + fallback instrumentation
- [DONE] runtime health diagnostics and telemetry visibility
- [DONE] baseline/compare/gate workflows with CI-ready exit behavior
- [DONE] artifact export for health snapshots and compare outputs
- [DONE] first-run bootstrap path for missing baselines
- [TODO] full workload benchmark harness for representative model inference throughput/latency
- [IN PROGRESS] quality drift/retrieval stability automated gates tied to production model sets (policy-backed corpus gate scaffold added via `ci/runtime-quality/quality_gate_policy.json` and runtime matrix workflow)
- [IN PROGRESS] platform CI matrix expansion for dedicated Apple Silicon and Linux GPU runners (workflow scaffold added: `.github/workflows/runtime-platform-matrix.yml`; self-hosted lane activation pending runner availability)

Recommended handoff to Phase 1:
- keep the current runtime gate path as the operational guardrail
- implement benchmark corpus + benchmark command workflow next
- add quality regression checks (cosine drift and retrieval stability) before default promotion decisions

### Integration with Existing In-Flight Plans

This GPU plan must be incorporated into partially executed plans rather than tracked as a parallel roadmap.

Required integration approach:
- keep existing release trains (`3.3.0`, `3.4.0`, `3.5.0`) intact
- map new GPU tasks into current milestones using additive work items
- preserve backward compatibility defaults until parity gates pass
- require explicit change notes where this plan supersedes earlier PyTorch-first assumptions

---

## Recommended Release Sequence

| Release | Theme |
|---------|-------|
| `3.3.0` | ONNX runtime/provider abstraction (CPU default), explicit Ollama support, clustering backend abstraction, `python_union_find` |
| `3.4.0` | Provider auto-selection promotion (gate-based), embedding throughput tuning, `python_sparse`, LLM health and fallback controls |
| `3.5.0` | Optional TensorRT optimization for selected models and optional `GAE` clustering backend for enterprise-scale graphs |

---

## Release 3.3.0

Primary theme: make hardware, provider, and backend selection explicit without breaking existing users.

> [INFO] Implementation precedence: when this release section conflicts with the
> "Cross-Platform GPU Implementation Brief (Apple Silicon + Linux)" section above,
> follow the cross-platform section and treat older PyTorch/MPS-only guidance as superseded.

### Files Changed

| File | Change type |
|------|-------------|
| `src/entity_resolution/config/er_config.py` | Modify 3 classes, add 1 class |
| `src/entity_resolution/services/embedding_service.py` | Modify `__init__`, add `resolve_device` |
| `src/entity_resolution/services/wcc_clustering_service.py` | Replace `use_bulk_fetch` with `backend` |
| `src/entity_resolution/reasoning/llm_verifier.py` | Add Ollama base_url wiring |
| `src/entity_resolution/reasoning/feedback.py` | Accept `LLMProviderConfig` |
| `src/entity_resolution/services/clustering_backends/` | New directory + 4 new files |
| `tests/unit/test_embedding_device_resolution.py` | New test file |
| `tests/unit/test_clustering_backends.py` | New test file |
| `tests/unit/test_ollama_config.py` | New test file |

---

### 1. `EmbeddingConfig` — `er_config.py`

**Current state** (lines 221–321):

```python
class EmbeddingConfig:
    def __init__(
        self,
        model_name: str = 'all-MiniLM-L6-v2',
        device: str = 'cpu',        # <-- hardcoded to 'cpu'
        embedding_field: str = 'embedding_vector',
        multi_resolution_mode: bool = False,
        coarse_model_name: Optional[str] = None,
        fine_model_name: Optional[str] = None,
        embedding_field_coarse: str = 'embedding_vector_coarse',
        embedding_field_fine: str = 'embedding_vector_fine',
        profile: str = 'default',
        batch_size: int = 32
    ):
        ...

    def validate(self) -> List[str]:
        ...
        if self.device not in ('cpu', 'cuda'):   # <-- rejects 'mps' and 'auto'
            errors.append(...)
```

**Required changes:**

> **Default deferred.** `device` default stays `'cpu'` in `3.3.0`. Change it to `'auto'`
> in `3.4.0` once MPS/CUDA parity tests pass. Only add `'auto'`, `'mps'` as valid values
> and extend `validate()` in this release.

```python
class EmbeddingConfig:
    def __init__(
        self,
        model_name: str = 'all-MiniLM-L6-v2',
        runtime: str = 'pytorch',           # NEW — 'pytorch' only in 3.3.0
        device: str = 'cpu',               # unchanged default — 'auto' deferred to 3.4.0
        embedding_field: str = 'embedding_vector',
        multi_resolution_mode: bool = False,
        coarse_model_name: Optional[str] = None,
        fine_model_name: Optional[str] = None,
        embedding_field_coarse: str = 'embedding_vector_coarse',
        embedding_field_fine: str = 'embedding_vector_fine',
        profile: str = 'default',
        batch_size: int = 32,
    ):
        self.runtime = runtime
        self.device = device
        # ... rest unchanged

    def validate(self) -> List[str]:
        errors = []
        # CHANGED: 'mps' and 'auto' are now valid
        if self.device not in ('cpu', 'cuda', 'mps', 'auto'):
            errors.append(f"device must be 'cpu', 'cuda', 'mps', or 'auto', got: {self.device}")
        if self.runtime not in ('pytorch',):
            errors.append(f"runtime must be 'pytorch', got: {self.runtime}")
        # ... existing validations unchanged
```

Also update `from_dict()` and `to_dict()` to read/write `runtime`:

```python
@classmethod
def from_dict(cls, config_dict: Dict[str, Any]) -> 'EmbeddingConfig':
    return cls(
        ...
        runtime=config_dict.get('runtime', 'pytorch'),   # NEW
        device=config_dict.get('device', 'cpu'),         # default stays 'cpu' until 3.4.0
        ...
    )

def to_dict(self) -> Dict[str, Any]:
    result = {
        ...
        'runtime': self.runtime,   # NEW
        'device': self.device,
        ...
    }
```

---

### 2. `EmbeddingService` — `embedding_service.py`

**Current state** (line 93–106):

```python
def __init__(
    self,
    model_name: str = DEFAULT_MODEL,
    device: str = 'cpu',         # <-- hardcoded default, no 'auto' or 'mps'
    embedding_field: str = DEFAULT_EMBEDDING_FIELD,
    db_manager: Optional[DatabaseManager] = None,
    multi_resolution_mode: bool = False,
    coarse_model_name: Optional[str] = None,
    fine_model_name: Optional[str] = None,
    embedding_field_coarse: str = DEFAULT_EMBEDDING_FIELD_COARSE,
    embedding_field_fine: str = DEFAULT_EMBEDDING_FIELD_FINE,
    profile: str = 'default',
    serializer: Optional[TupleEmbeddingSerializer] = None
    # Note: no batch_size param — batch_size only exists on EmbeddingConfig
):
```

Also: the docstring for `device` currently reads `'cpu' or 'cuda'` only.

**Required changes:**

> **Default deferred.** `device` default stays `'cpu'` in `3.3.0` here too. The resolver
> method is wired in, but `'auto'` is only activated when the user explicitly sets it.
> Change the default to `'auto'` in `3.4.0` after CI parity is confirmed.

```python
def __init__(
    self,
    model_name: str = DEFAULT_MODEL,
    runtime: str = 'pytorch',        # NEW
    device: str = 'cpu',             # unchanged default — 'auto' deferred to 3.4.0
    embedding_field: str = DEFAULT_EMBEDDING_FIELD,
    db_manager: Optional[DatabaseManager] = None,
    multi_resolution_mode: bool = False,
    coarse_model_name: Optional[str] = None,
    fine_model_name: Optional[str] = None,
    embedding_field_coarse: str = DEFAULT_EMBEDDING_FIELD_COARSE,
    embedding_field_fine: str = DEFAULT_EMBEDDING_FIELD_FINE,
    profile: str = 'default',
    serializer: Optional[TupleEmbeddingSerializer] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,   # NEW — wire batch_size through to model.encode()
):
    self.runtime = runtime
    self.requested_device = device
    self.device = self.resolve_device(device)   # store resolved device
    self.batch_size = batch_size
    # ... rest of __init__ unchanged, but pass self.device to SentenceTransformer()
```

**New method to add:**

```python
def resolve_device(self, requested: str) -> str:
    """
    Resolve the requested device string to a concrete device available at runtime.

    Args:
        requested: 'auto', 'cpu', 'cuda', or 'mps'

    Returns:
        'cuda', 'mps', or 'cpu'
    """
    if requested == 'auto':
        try:
            import torch
            if torch.cuda.is_available():
                return 'cuda'
            if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return 'mps'
        except ImportError:
            pass
        return 'cpu'
    return requested
```

**Embed resolved device in metadata** — wherever embedding metadata is built (search for `metadata_version` or `embedding_metadata`), add:

```python
metadata['requested_device'] = self.requested_device
metadata['resolved_device'] = self.device
```

**Batch size wiring** — wherever `model.encode(...)` is called, pass `batch_size=self.batch_size`. Search for `.encode(` in `embedding_service.py` to find all call sites.

---

### 3. `LLMProviderConfig` — new class in `er_config.py`

Add this new config class **before** `ActiveLearningConfig`:

```python
class LLMProviderConfig:
    """
    Provider configuration for LLM-assisted match verification.

    Translates structured provider settings into a litellm model string.
    litellm already supports Ollama natively; the model string format is
    'ollama/model_name' with base_url pointing at the local server.

    Example (Ollama):
        LLMProviderConfig(
            provider='ollama',
            model='llama3.1:8b',
            base_url='http://localhost:11434'
        )
        # produces litellm model string: 'ollama/llama3.1:8b'

    Example (OpenRouter):
        LLMProviderConfig(
            provider='openrouter',
            model='google/gemini-2.0-flash'
        )
        # produces litellm model string: 'openrouter/google/gemini-2.0-flash'
    """

    PROVIDER_BASE_URLS = {
        'ollama': 'http://localhost:11434',
    }

    def __init__(
        self,
        provider: str = 'openrouter',
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key_env: Optional[str] = None,
        timeout_seconds: int = 60,
    ):
        self.provider = provider
        self.model = model
        self.base_url = base_url or self.PROVIDER_BASE_URLS.get(provider)
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    def to_litellm_model_string(self) -> Optional[str]:
        """
        Return the litellm model string for this provider config.

        Returns None if model is not set (caller should fall back to env defaults).
        """
        if not self.model:
            return None
        if self.provider in ('openrouter', 'openai', 'anthropic', 'ollama'):
            return f"{self.provider}/{self.model}"
        return self.model

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'LLMProviderConfig':
        return cls(
            provider=config_dict.get('provider', 'openrouter'),
            model=config_dict.get('model'),
            base_url=config_dict.get('base_url'),
            api_key_env=config_dict.get('api_key_env'),
            timeout_seconds=config_dict.get('timeout_seconds', 60),
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            'provider': self.provider,
            'timeout_seconds': self.timeout_seconds,
        }
        if self.model is not None:
            result['model'] = self.model
        if self.base_url is not None:
            result['base_url'] = self.base_url
        if self.api_key_env is not None:
            result['api_key_env'] = self.api_key_env
        return result

    def validate(self) -> List[str]:
        errors = []
        valid_providers = ('openrouter', 'openai', 'anthropic', 'ollama')
        if self.provider not in valid_providers:
            errors.append(
                f"provider must be one of {valid_providers}, got: {self.provider}"
            )
        if self.timeout_seconds < 1:
            errors.append(f"timeout_seconds must be >= 1, got: {self.timeout_seconds}")
        return errors
```

---

### 4. `ActiveLearningConfig` — `er_config.py`

**Current state** (lines 324–399):

```python
class ActiveLearningConfig:
    def __init__(
        self,
        enabled: bool = False,
        feedback_collection: Optional[str] = None,
        refresh_every: int = 100,
        model: Optional[str] = None,    # <-- bare litellm model string
        low_threshold: float = 0.55,
        high_threshold: float = 0.80,
        optimizer_target_precision: float = 0.95,
        optimizer_min_samples: int = 20,
    ):
```

**Required changes** — add `llm: Optional[LLMProviderConfig]` alongside the existing `model` field. Both should work; `llm` takes precedence.

```python
class ActiveLearningConfig:
    def __init__(
        self,
        enabled: bool = False,
        feedback_collection: Optional[str] = None,
        refresh_every: int = 100,
        model: Optional[str] = None,                    # kept for backward compat
        low_threshold: float = 0.55,
        high_threshold: float = 0.80,
        optimizer_target_precision: float = 0.95,
        optimizer_min_samples: int = 20,
        llm: Optional[LLMProviderConfig] = None,        # NEW
    ):
        ...
        self.llm = llm

    def effective_model_string(self) -> Optional[str]:
        """
        Return the litellm model string to use, preferring llm config over bare model string.
        """
        if self.llm is not None:
            return self.llm.to_litellm_model_string()
        return self.model

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'ActiveLearningConfig':
        llm_dict = config_dict.get('llm')
        llm = LLMProviderConfig.from_dict(llm_dict) if llm_dict else None
        return cls(
            ...
            llm=llm,   # NEW
        )

    def to_dict(self) -> Dict[str, Any]:
        result = { ... }  # existing fields
        if self.llm is not None:
            result['llm'] = self.llm.to_dict()   # NEW
        return result

    def validate(self) -> List[str]:
        errors = []
        # ... existing validations ...
        if self.llm is not None:
            errors.extend(self.llm.validate())   # NEW
        return errors
```

---

### 5. `LLMMatchVerifier` — `reasoning/llm_verifier.py`

**Current state** — verifier accepts a single `model` litellm string. Ollama is already supported
via model strings like `"ollama/mistral"`. The docstring mentions this but it is not visible in config.

**Required changes** — add `base_url` and `timeout_seconds` params so `LLMProviderConfig` values
can be forwarded. Pass `base_url` and `timeout` to litellm calls.

```python
class LLMMatchVerifier:
    def __init__(
        self,
        model: Optional[str] = None,
        low_threshold: float = 0.55,
        high_threshold: float = 0.80,
        entity_type: str = "entity",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,      # NEW — needed for Ollama
        timeout_seconds: int = 60,           # NEW
    ):
        ...
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
```

When calling `litellm.completion(...)`, add:

```python
kwargs = dict(
    model=self.model,
    messages=messages,
    timeout=self.timeout_seconds,
)
if self.base_url:
    kwargs['base_url'] = self.base_url
response = litellm.completion(**kwargs)
```

**Helper — build from `LLMProviderConfig`:**

```python
@classmethod
def from_provider_config(cls, provider_config: 'LLMProviderConfig', **kwargs) -> 'LLMMatchVerifier':
    return cls(
        model=provider_config.to_litellm_model_string(),
        base_url=provider_config.base_url,
        timeout_seconds=provider_config.timeout_seconds,
        **kwargs,
    )
```

---

### 6. `ClusteringConfig` — `er_config.py`

**Current state** (lines 177–218):

```python
class ClusteringConfig:
    def __init__(
        self,
        algorithm: str = "wcc",
        min_cluster_size: int = 2,
        store_results: bool = True,
        wcc_algorithm: str = "python_dfs"    # <-- no 'backend' param
    ):
```

**Required changes:**

> **Mapping preserves existing behaviour.** `wcc_algorithm='python_dfs'` maps to
> `backend='python_dfs'` — NOT to `backend='python_union_find'`. This keeps cluster
> outputs identical for all users with existing YAML configs in 3.3.0. The
> `python_union_find` backend is available but only activates when explicitly requested.
> It becomes the default only in 3.4.0 once parity tests are green.

```python
class ClusteringConfig:
    # Mapping from legacy wcc_algorithm values to new backend values.
    # python_dfs maps to python_dfs (not python_union_find) to preserve existing output.
    _WCC_ALGORITHM_TO_BACKEND = {
        'python_dfs': 'python_dfs',        # preserves current cluster output
        'aql_graph': 'aql_graph',
    }

    def __init__(
        self,
        algorithm: str = "wcc",
        min_cluster_size: int = 2,
        store_results: bool = True,
        backend: str = "python_dfs",                # default matches current behaviour
        wcc_algorithm: Optional[str] = None,        # DEPRECATED — maps to backend
    ):
        self.algorithm = algorithm
        self.min_cluster_size = min_cluster_size
        self.store_results = store_results

        if wcc_algorithm is not None:
            import warnings
            warnings.warn(
                "ClusteringConfig.wcc_algorithm is deprecated and will be removed in 3.5.0. "
                "Use backend= instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            self.backend = self._WCC_ALGORITHM_TO_BACKEND.get(wcc_algorithm, wcc_algorithm)
        else:
            self.backend = backend

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'ClusteringConfig':
        return cls(
            algorithm=config_dict.get('algorithm', 'wcc'),
            min_cluster_size=config_dict.get('min_cluster_size', 2),
            store_results=config_dict.get('store_results', True),
            backend=config_dict.get('backend', 'python_union_find'),
            wcc_algorithm=config_dict.get('wcc_algorithm'),  # still read, triggers deprecation warning
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'algorithm': self.algorithm,
            'min_cluster_size': self.min_cluster_size,
            'store_results': self.store_results,
            'backend': self.backend,    # write new field, not wcc_algorithm
        }
```

---

### 7. Clustering backends — new directory and files

**Create the directory:**

```
src/entity_resolution/services/clustering_backends/
    __init__.py
    base.py
    python_dfs.py
    python_union_find.py
    aql_graph.py
```

**`base.py`** — Protocol definition:

```python
from typing import List, Protocol, runtime_checkable

@runtime_checkable
class ClusteringBackend(Protocol):
    def cluster(self) -> List[List[str]]:
        """Return list of clusters; each cluster is a list of document keys."""
        ...

    def backend_name(self) -> str:
        """Return the canonical backend identifier string."""
        ...
```

**`python_union_find.py`** — implementation sketch:

```python
class PythonUnionFindBackend:
    """
    In-process WCC via Union-Find.

    Algorithm:
    1. Fetch all edges from the edge collection in one AQL query.
    2. Map vertex _id strings to compact integer indices.
    3. Run path-compressed Union-Find over those integers.
    4. Convert component integer IDs back to document keys.

    This is faster than Python DFS for larger graphs because Union-Find
    has near-linear amortized complexity and the fetch is a single query.
    """

    def __init__(self, db, edge_collection_name: str, vertex_collection: Optional[str] = None):
        self.db = db
        self.edge_collection_name = edge_collection_name
        self.vertex_collection = vertex_collection

    def _fetch_edges(self) -> List[tuple]:
        """Fetch all (_from, _to) pairs from the edge collection."""
        cursor = self.db.aql.execute(
            "FOR e IN @@col RETURN [e._from, e._to]",
            bind_vars={'@col': self.edge_collection_name}
        )
        return list(cursor)

    def _build_union_find(self, edges: List[tuple]) -> Dict[str, str]:
        """
        Run Union-Find and return a mapping of vertex_id -> root_vertex_id.
        Uses path compression and union by rank.
        """
        parent: Dict[str, str] = {}
        rank: Dict[str, int] = {}

        def find(x: str) -> str:
            if parent.setdefault(x, x) != x:
                parent[x] = find(parent[x])   # path compression
            return parent[x]

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra == rb:
                return
            if rank.get(ra, 0) < rank.get(rb, 0):
                ra, rb = rb, ra
            parent[rb] = ra
            if rank.get(ra, 0) == rank.get(rb, 0):
                rank[ra] = rank.get(ra, 0) + 1

        for from_id, to_id in edges:
            union(from_id, to_id)

        return {v: find(v) for v in parent}

    def cluster(self) -> List[List[str]]:
        from collections import defaultdict
        edges = self._fetch_edges()
        components = self._build_union_find(edges)

        groups: Dict[str, List[str]] = defaultdict(list)
        for vertex_id, root_id in components.items():
            # Convert _id ('collection/key') to key only
            key = vertex_id.split('/')[-1]
            groups[root_id].append(key)

        return list(groups.values())

    def backend_name(self) -> str:
        return 'python_union_find'
```

**`aql_graph.py`** — thin wrapper extracting the existing AQL traversal logic from `WCCClusteringService._find_connected_components_aql()`.

**`python_dfs.py`** — thin wrapper extracting the existing bulk DFS logic from `WCCClusteringService._find_connected_components_bulk()`.

---

### 8. `WCCClusteringService` — backend dispatch

**Current state** (line 56–64):

```python
def __init__(
    self,
    db: StandardDatabase,
    edge_collection: str = "similarTo",
    cluster_collection: str = "entity_clusters",
    vertex_collection: Optional[str] = None,
    min_cluster_size: int = 2,
    graph_name: Optional[str] = None,
    use_bulk_fetch: bool = True         # <-- binary flag
):
```

**Required changes:**

```python
def __init__(
    self,
    db: StandardDatabase,
    edge_collection: str = "similarTo",
    cluster_collection: str = "entity_clusters",
    vertex_collection: Optional[str] = None,
    min_cluster_size: int = 2,
    graph_name: Optional[str] = None,
    backend: str = "python_union_find",   # NEW
    use_bulk_fetch: Optional[bool] = None,  # DEPRECATED shim
):
    if use_bulk_fetch is not None:
        import warnings
        warnings.warn(
            "WCCClusteringService.use_bulk_fetch is deprecated. Use backend= instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.backend = 'python_union_find' if use_bulk_fetch else 'aql_graph'
    else:
        self.backend = backend
```

**`cluster()` method** — replace the `if self.use_bulk_fetch:` branch:

```python
def cluster(self, store_results: bool = True, truncate_existing: bool = True) -> List[List[str]]:
    start_time = time.time()

    backend_impl = self._get_backend()
    clusters = backend_impl.cluster()

    filtered_clusters = [c for c in clusters if len(c) >= self.min_cluster_size]

    if store_results:
        if truncate_existing:
            self.cluster_collection.truncate()
        self._store_clusters(filtered_clusters)

    execution_time = time.time() - start_time
    self._stats['backend_used'] = backend_impl.backend_name()   # NEW stat field
    self._update_statistics(filtered_clusters, execution_time)
    return filtered_clusters

def _get_backend(self):
    from .clustering_backends.python_union_find import PythonUnionFindBackend
    from .clustering_backends.python_dfs import PythonDFSBackend
    from .clustering_backends.aql_graph import AQLGraphBackend

    if self.backend == 'python_union_find':
        return PythonUnionFindBackend(self.db, self.edge_collection_name, self.vertex_collection)
    if self.backend in ('python_dfs', 'bulk_python_dfs'):
        return PythonDFSBackend(self.db, self.edge_collection_name, self.vertex_collection)
    if self.backend == 'aql_graph':
        return AQLGraphBackend(self.db, self.edge_collection_name, self.vertex_collection, self.graph_name)
    raise ValueError(f"Unknown clustering backend: {self.backend!r}")
```

Also add `backend_used` to `_stats` initial dict (currently missing).

---

### Config Schema Diff for 3.3.0

```diff
 entity_resolution:
   embedding:
     model_name: all-MiniLM-L6-v2
+    runtime: pytorch          # NEW — explicit, 'pytorch' is the only valid value
     device: cpu               # UNCHANGED default — opt into 'auto'/'mps'/'cuda' explicitly
+    batch_size: 32            # NEW — was implicit, now explicit

   active_learning:
     enabled: true
     low_threshold: 0.55
     high_threshold: 0.80
-    model: openrouter/google/gemini-2.0-flash     # still works (backward compat)
+    llm:                                          # NEW structured form (takes precedence)
+      provider: ollama
+      model: llama3.1:8b
+      base_url: http://localhost:11434
+      timeout_seconds: 60

   clustering:
     algorithm: wcc
-    wcc_algorithm: python_dfs           # still works but emits DeprecationWarning
+    backend: python_dfs                 # equivalent — preserves existing cluster output
```

Note: `device: auto` is **not** shown in the diff above because changing the default would
be a silent behaviour change. Users who want hardware acceleration must opt in explicitly:

```yaml
embedding:
  device: auto   # opt in — resolves to cuda, mps, or cpu at runtime
```

### Acceptance Criteria — 3.3.0

- `EmbeddingService.resolve_device('auto')` returns `'mps'` on Apple Silicon when PyTorch MPS is available (mocked in CI).
- `EmbeddingService.resolve_device('auto')` returns `'cpu'` when neither `cuda` nor `mps` is available.
- `device='mps'`, `device='cuda'`, and `device='auto'` are accepted by `EmbeddingConfig.validate()` without error.
- **`device='cpu'` remains the default** — no user sees a behaviour change without opting in.
- Existing embedding configs with `device='cpu'` work unchanged with no warnings emitted.
- `runtime='pytorch'` is the only accepted runtime value and is validated.
- `LLMProviderConfig(provider='ollama', model='llama3.1:8b').to_litellm_model_string()` returns `'ollama/llama3.1:8b'`.
- `ActiveLearningConfig.effective_model_string()` returns the `llm`-derived string when `llm` is set.
- Existing `ActiveLearningConfig(model='openrouter/...')` still works unchanged.
- `WCCClusteringService(backend='python_union_find')` runs and produces correct clusters.
- `WCCClusteringService(backend='python_dfs')` produces **identical output** to the current `use_bulk_fetch=True` path (parity test required).
- `WCCClusteringService(use_bulk_fetch=True)` still works and emits a `DeprecationWarning`.
- `ClusteringConfig(wcc_algorithm='python_dfs')` maps to `backend='python_dfs'` (not `python_union_find`) and emits a `DeprecationWarning`.
- **`python_dfs` remains the effective default** — existing users with no config changes see identical cluster outputs.
- `get_statistics()` includes `backend_used` key.
- Parity test `test_union_find_parity_with_python_dfs` must be green before `python_union_find` can become the default in 3.4.0.
- Unit tests added for: device resolution, `LLMProviderConfig`, `ActiveLearningConfig.effective_model_string()`, clustering backend dispatch, and `python_dfs`/`python_union_find` parity.

### Test Files — 3.3.0

```
tests/unit/test_embedding_device_resolution.py
    - test_auto_resolves_to_cpu_when_no_gpu
    - test_auto_resolves_to_mps_when_mps_available (mocked)
    - test_auto_resolves_to_cuda_when_cuda_available (mocked)
    - test_explicit_cpu_unchanged
    - test_explicit_mps_unchanged
    - test_validate_accepts_mps
    - test_validate_accepts_auto
    - test_validate_rejects_unknown_device

tests/unit/test_clustering_backends.py
    - test_union_find_single_component
    - test_union_find_two_components
    - test_union_find_no_edges
    - test_union_find_parity_with_python_dfs (compare outputs on shared fixture)
    - test_wcc_service_backend_param
    - test_wcc_service_deprecation_warning_for_use_bulk_fetch
    - test_clustering_config_deprecation_warning_for_wcc_algorithm
    - test_backend_used_in_statistics

tests/unit/test_llm_provider_config.py
    - test_ollama_model_string
    - test_openrouter_model_string
    - test_active_learning_effective_model_string_uses_llm_when_set
    - test_active_learning_effective_model_string_falls_back_to_model
    - test_llm_provider_config_from_dict
    - test_llm_provider_config_to_dict
    - test_llm_provider_config_validate_unknown_provider
```

---

## Release 3.4.0

Primary theme: make abstractions operationally strong and performance-aware.

### Files Changed

| File | Change type |
|------|-------------|
| `src/entity_resolution/config/er_config.py` | Extend 2 classes; `device` default changes to `'auto'`; `ClusteringConfig.backend` default changes to `'python_union_find'` |
| `src/entity_resolution/services/embedding_service.py` | Backend-aware batch defaults, OOM warnings, benchmark metadata |
| `src/entity_resolution/reasoning/llm_verifier.py` | Add `healthcheck()` method |
| `src/entity_resolution/services/wcc_clustering_service.py` | `_get_backend()` handles `'auto'` and `'python_sparse'` |
| `src/entity_resolution/services/clustering_backends/python_sparse.py` | New file |
| `tests/unit/test_auto_backend_selection.py` | New test file |
| `tests/unit/test_llm_healthcheck.py` | New test file |

---

### 1. `EmbeddingConfig` additions

```python
class EmbeddingConfig:
    def __init__(
        self,
        ...,
        batch_size: int = 32,
        max_batch_size: Optional[int] = None,  # NEW — cap for OOM safety
    ):
```

`from_dict()` addition:

```python
max_batch_size=config_dict.get('max_batch_size'),
```

---

### 2. `EmbeddingService` — backend-aware batch defaults and OOM handling

Add backend-aware default batch selection logic when `batch_size` is not explicitly set:

```python
DEFAULT_BATCH_SIZES = {
    'cpu': 32,
    'mps': 32,
    'cuda': 64,
}
```

Wrap `model.encode(...)` calls in a try/except for OOM:

```python
try:
    embeddings = model.encode(texts, batch_size=self.batch_size, ...)
except RuntimeError as e:
    if 'out of memory' in str(e).lower():
        self.logger.warning(
            "OOM during embedding. Try reducing batch_size. "
            f"Current device: {self.device}, batch_size: {self.batch_size}"
        )
    raise
```

---

### 3. `LLMProviderConfig` additions

```python
class LLMProviderConfig:
    def __init__(
        self,
        ...,
        healthcheck_on_start: bool = False,    # NEW
        fallback_provider: Optional[str] = None,  # NEW
    ):
```

---

### 4. `ClusteringConfig` additions and default change

In 3.4.0 two default values change — both are intentional promotions of already-tested paths:

- `device` in `EmbeddingConfig` and `EmbeddingService` changes from `'cpu'` to `'auto'`, now that MPS and CUDA parity tests passed in 3.3.0.
- `backend` in `ClusteringConfig` changes from `'python_dfs'` to `'python_union_find'`, now that parity tests passed in 3.3.0.
- `backend='auto'` is introduced as a valid value but is **not** the default yet — that is deferred to 3.5.0.

```python
class ClusteringConfig:
    def __init__(
        self,
        ...,
        backend: str = "python_union_find",                 # CHANGED from 'python_dfs' — parity confirmed in 3.3.0
        auto_select_threshold_edges: int = 2_000_000,       # NEW — used when backend='auto'
        sparse_backend_enabled: bool = True,                # NEW — used when backend='auto'
    ):
```

---

### 5. `LLMMatchVerifier.healthcheck()`

```python
def healthcheck(self) -> Dict[str, Any]:
    """
    Check whether the configured model/provider is reachable.

    Returns a dict with keys:
        'ok': bool
        'provider': str
        'model': str
        'latency_ms': float or None
        'error': str or None
    """
    import time
    start = time.time()
    try:
        response = litellm.completion(
            model=self.model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            timeout=5,
            **({"base_url": self.base_url} if self.base_url else {}),
        )
        return {
            'ok': True,
            'model': self.model,
            'latency_ms': round((time.time() - start) * 1000, 1),
            'error': None,
        }
    except Exception as e:
        return {
            'ok': False,
            'model': self.model,
            'latency_ms': None,
            'error': str(e),
        }
```

---

### 6. `python_sparse.py` — new backend

```python
class PythonSparseBackend:
    """
    In-process WCC via scipy.sparse.csgraph.

    Requires: scipy (optional dependency)

    Algorithm:
    1. Fetch all edges.
    2. Build a scipy CSR sparse adjacency matrix.
    3. Call scipy.sparse.csgraph.connected_components().
    4. Map component labels back to document keys.

    Faster than Union-Find for very dense large graphs.
    """

    def __init__(self, db, edge_collection_name: str, vertex_collection: Optional[str] = None):
        ...

    def cluster(self) -> List[List[str]]:
        try:
            from scipy.sparse import csr_matrix
            from scipy.sparse.csgraph import connected_components
        except ImportError:
            raise ImportError(
                "python_sparse backend requires scipy. "
                "Install it with: pip install scipy"
            )
        # fetch edges, build int index map, build CSR, call connected_components, return clusters

    def backend_name(self) -> str:
        return 'python_sparse'
```

---

### 7. `WCCClusteringService._get_backend()` — `auto` logic

```python
def _get_backend(self):
    if self.backend == 'auto':
        return self._auto_select_backend()
    # ... existing dispatch

def _auto_select_backend(self):
    edge_count = self.edge_collection.count()
    threshold = getattr(self, 'auto_select_threshold_edges', 2_000_000)
    sparse_enabled = getattr(self, 'sparse_backend_enabled', True)

    if sparse_enabled and edge_count > threshold:
        try:
            from .clustering_backends.python_sparse import PythonSparseBackend
            return PythonSparseBackend(self.db, self.edge_collection_name, self.vertex_collection)
        except ImportError:
            pass  # fall through to union_find

    from .clustering_backends.python_union_find import PythonUnionFindBackend
    return PythonUnionFindBackend(self.db, self.edge_collection_name, self.vertex_collection)
```

Pass `auto_select_threshold_edges` and `sparse_backend_enabled` from `ClusteringConfig` when building the service in `ConfigurableERPipeline`.

---

### Config Schema Diff for 3.4.0

This release promotes two defaults that were confirmed safe in 3.3.0 testing:

```diff
 entity_resolution:
   embedding:
     runtime: pytorch
-    device: cpu               # default promoted to 'auto' — MPS/CUDA parity confirmed
+    device: auto
     batch_size: 32
+    max_batch_size: 128

   active_learning:
     llm:
       provider: ollama
       model: llama3.1:8b
       base_url: http://localhost:11434
       timeout_seconds: 60
+      healthcheck_on_start: true
+      fallback_provider: openrouter

   clustering:
     algorithm: wcc
-    backend: python_dfs        # default promoted to 'python_union_find' — parity confirmed
+    backend: python_union_find
+    auto_select_threshold_edges: 2000000   # used when backend='auto' (opt-in)
+    sparse_backend_enabled: true           # used when backend='auto' (opt-in)
```

Note: `backend: auto` is **not** the default in 3.4.0. It is available as an opt-in value.
Users who want auto-selection must set it explicitly. It becomes the default in 3.5.0.

### Acceptance Criteria — 3.4.0

- `device='auto'` is now the default; existing explicit `device='cpu'` configs still work unchanged.
- `backend='python_union_find'` is the new default; clusters are identical to the 3.3.0 `python_dfs` output on shared fixtures (confirmed before release).
- `backend='auto'` (opt-in) selects `python_union_find` below the edge threshold and records `backend_used`.
- `backend='auto'` (opt-in) selects `python_sparse` above the edge threshold when scipy is installed.
- `python_sparse` output matches `python_union_find` output on shared benchmark fixtures.
- `LLMMatchVerifier.healthcheck()` returns `'ok': True` for a live Ollama instance and `'ok': False` with an informative `'error'` when unreachable.
- Embedding benchmarks on CUDA and MPS (where available) show measurable throughput improvement versus CPU baseline.
- Docs include platform-specific install guidance for CPU, CUDA, MPS, and Ollama.

### ONNX Evaluation Gates (3.4.x)

`ONNX` should only move forward if it demonstrates all of the following on representative ER workloads:
- materially better CPU throughput than PyTorch
- no unacceptable regression in embedding quality (cosine similarity of outputs within 0.01 tolerance)
- acceptable model load and startup time
- manageable packaging and developer experience
- clean fallback behavior to PyTorch if ONNX fails

### Test Files — 3.4.0

```
tests/unit/test_auto_backend_selection.py
    - test_auto_selects_union_find_below_threshold
    - test_auto_selects_sparse_above_threshold_when_scipy_available
    - test_auto_falls_back_to_union_find_when_scipy_missing
    - test_sparse_parity_with_union_find

tests/unit/test_llm_healthcheck.py
    - test_healthcheck_ok (mocked successful litellm response)
    - test_healthcheck_failure (mocked exception)
    - test_healthcheck_timeout (mocked timeout)
```

---

## Release 3.5.0

Primary theme: enterprise-scale clustering with optional GAE integration.

### Files Changed

| File | Change type |
|------|-------------|
| `src/entity_resolution/config/er_config.py` | Add `GAEClusteringConfig`, extend `ClusteringConfig` |
| `src/entity_resolution/services/clustering_backends/gae_wcc.py` | New file |
| `src/entity_resolution/services/wcc_clustering_service.py` | Add `'gae_wcc'` dispatch, extend `auto` |
| `tests/unit/test_gae_backend.py` | New test file |
| `tests/integration/test_gae_clustering.py` | New integration test (requires GAE env) |

---

### 1. `GAEClusteringConfig` — new class in `er_config.py`

```python
class GAEClusteringConfig:
    """
    Configuration for optional ArangoDB Graph Analytics Engine (GAE) clustering.

    GAE is an enterprise capability for very large graphs (>10M edges).
    This backend is optional and capability-gated; the system falls back
    to local backends when GAE is unavailable.

    deployment_mode values:
        'self_managed' — caller manages the graph lifecycle
        'auto'         — service creates/deletes a temporary graph automatically
    """

    def __init__(
        self,
        enabled: bool = False,
        deployment_mode: str = 'self_managed',
        graph_name: Optional[str] = None,
        engine_size: str = 'e16',
        auto_cleanup: bool = True,
        timeout_seconds: int = 3600,
    ):
        self.enabled = enabled
        self.deployment_mode = deployment_mode
        self.graph_name = graph_name
        self.engine_size = engine_size
        self.auto_cleanup = auto_cleanup
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'GAEClusteringConfig':
        return cls(
            enabled=config_dict.get('enabled', False),
            deployment_mode=config_dict.get('deployment_mode', 'self_managed'),
            graph_name=config_dict.get('graph_name'),
            engine_size=config_dict.get('engine_size', 'e16'),
            auto_cleanup=config_dict.get('auto_cleanup', True),
            timeout_seconds=config_dict.get('timeout_seconds', 3600),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'enabled': self.enabled,
            'deployment_mode': self.deployment_mode,
            'graph_name': self.graph_name,
            'engine_size': self.engine_size,
            'auto_cleanup': self.auto_cleanup,
            'timeout_seconds': self.timeout_seconds,
        }
```

---

### 2. `ClusteringConfig` — add `gae` field

```python
class ClusteringConfig:
    def __init__(
        self,
        ...,
        backend: str = "auto",
        gae: Optional[GAEClusteringConfig] = None,   # NEW
    ):
        ...
        self.gae = gae

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'ClusteringConfig':
        gae_dict = config_dict.get('gae')
        gae = GAEClusteringConfig.from_dict(gae_dict) if gae_dict else None
        return cls(..., gae=gae)
```

---

### 3. `gae_wcc.py` — backend skeleton

```python
class GAEWCCBackend:
    """
    WCC clustering via ArangoDB Graph Analytics Engine.

    Requirements:
    - ArangoDB Enterprise or ArangoGraph (AMP) with GAE enabled
    - Graph must be defined or auto-created

    Implementation pattern is inspired by the agentic-graph-analytics project
    (~/code/agentic-graph-analytics) but does not create a hard dependency on it.
    """

    def __init__(
        self,
        db,
        edge_collection_name: str,
        vertex_collection: Optional[str] = None,
        gae_config: Optional['GAEClusteringConfig'] = None,
    ):
        self.db = db
        self.edge_collection_name = edge_collection_name
        self.vertex_collection = vertex_collection
        self.gae_config = gae_config or GAEClusteringConfig()

    def is_available(self) -> bool:
        """
        Return True if GAE is accessible on the connected ArangoDB instance.
        Check for the /_api/analytics endpoint or a known GAE capability signal.
        """
        try:
            response = self.db.conn.send_request('GET', '/_api/analytics')
            return response.status_code == 200
        except Exception:
            return False

    def cluster(self) -> List[List[str]]:
        if not self.is_available():
            raise RuntimeError(
                "GAE clustering backend is not available. "
                "Requires ArangoDB Enterprise or ArangoGraph with GAE enabled. "
                "Use backend='auto' to fall back to a local backend automatically."
            )
        # GAE WCC call, polling, result parsing
        raise NotImplementedError("GAE WCC implementation to be completed in 3.5.0")

    def backend_name(self) -> str:
        return 'gae_wcc'
```

---

### 4. `WCCClusteringService._auto_select_backend()` — add GAE

```python
def _auto_select_backend(self):
    gae_config = getattr(self, 'gae_config', None)
    if gae_config and gae_config.enabled:
        from .clustering_backends.gae_wcc import GAEWCCBackend
        gae = GAEWCCBackend(self.db, self.edge_collection_name, self.vertex_collection, gae_config)
        if gae.is_available():
            edge_count = self.edge_collection.count()
            threshold = getattr(self, 'auto_select_threshold_edges', 2_000_000)
            if edge_count > threshold:
                return gae

    # ... fall through to existing auto logic
```

Also store GAE stats when used:

```python
self._stats['backend_used'] = backend.backend_name()
if hasattr(backend, 'gae_job_id'):
    self._stats['gae_job_id'] = backend.gae_job_id
    self._stats['gae_runtime_seconds'] = backend.gae_runtime_seconds
```

---

### Config Schema Diff for 3.5.0

```diff
 entity_resolution:
   clustering:
     algorithm: wcc
     backend: auto
     auto_select_threshold_edges: 2000000
     sparse_backend_enabled: true
+    gae:
+      enabled: true
+      deployment_mode: self_managed
+      graph_name: companies_similarity_graph
+      engine_size: e16
+      auto_cleanup: true
+      timeout_seconds: 3600
```

### Acceptance Criteria — 3.5.0

- `backend='gae_wcc'` raises a clear `RuntimeError` explaining requirements when GAE is unavailable.
- `backend='auto'` does not select GAE when `gae.enabled=False` (default).
- `backend='auto'` selects GAE when `gae.enabled=True` and GAE is available and edge count exceeds threshold.
- `auto` falls back safely when GAE is unavailable.
- GAE WCC output matches local and AQL clustering on reference datasets.
- Cluster document shape is identical across all backends (same keys and format).
- `get_statistics()` includes `backend_used`, `gae_job_id`, and `gae_runtime_seconds` when GAE was used.
- End-to-end integration test exists (skippable when GAE env is unavailable).

### Test Files — 3.5.0

```
tests/unit/test_gae_backend.py
    - test_is_available_returns_false_when_endpoint_missing (mocked)
    - test_cluster_raises_on_unavailable_gae
    - test_auto_skips_gae_when_disabled
    - test_auto_selects_gae_when_enabled_and_available (mocked)
    - test_auto_skips_gae_when_below_threshold

tests/integration/test_gae_clustering.py   (skip marker: requires_gae)
    - test_gae_wcc_produces_correct_clusters
    - test_gae_fallback_to_local_when_unavailable
```

---

## Packaging and Platform Guidance

- Keep the base install CPU-safe.
- Keep `sentence-transformers` and `torch` under existing optional ML extras.
- Document CUDA, MPS, and Ollama setup separately — do not attempt to encode every platform wheel in `pyproject.toml`.
- `scipy` for `python_sparse` should be an optional dependency (not required for default installs).
- Keep GAE support capability-gated with a clear error message when unavailable.
- Keep Ollama support dependency-free — it works through `litellm`, which is already a dependency.

---

## Backward Compatibility Risk Register

Three changes across these releases alter **default runtime behaviour** without a deprecation
warning. Each is staged so the change only lands after the relevant parity tests are green.

| Change | Lands in | Risk | Mitigation |
|--------|----------|------|------------|
| `device` default `'cpu'` → `'auto'` | `3.4.0` | MPS/CUDA may produce slightly different float values; OOM possible on low-memory GPUs | Keep `'cpu'` default in `3.3.0`; add parity and OOM tests; users can always pin `device: cpu` |
| `backend` default `'python_dfs'` → `'python_union_find'` | `3.4.0` | Cluster membership may differ if algorithm has edge-case bugs | Keep `'python_dfs'` default in `3.3.0`; require parity test to pass before 3.4.0 |
| `backend` default `'python_union_find'` → `'auto'` | `3.5.0` | Auto-selection may pick different backend on different machines | Keep `'python_union_find'` default in `3.4.0`; `'auto'` is opt-in until 3.5.0 |

All other changes in all three releases are additive or explicitly deprecated with warnings.

---

## Compatibility Rules

- `device='cpu'` and existing embedding configs remain valid throughout all three releases.
- `device='auto'` is opt-in in `3.3.0`; becomes the default in `3.4.0` only after parity confirmed.
- `runtime='pytorch'` is the only valid runtime in `3.3.0` and `3.4.0`.
- `wcc_algorithm=` on `ClusteringConfig` emits `DeprecationWarning` from `3.3.0` and must not be removed before `3.5.0`.
- `use_bulk_fetch=` on `WCCClusteringService` emits `DeprecationWarning` from `3.3.0` and must not be removed before `3.5.0`.
- `ActiveLearningConfig(model=...)` continues to work; `llm=` takes precedence when both are set.
- `ClusteringConfig(wcc_algorithm='python_dfs')` maps to `backend='python_dfs'` in `3.3.0` — NOT to `python_union_find`.
- `backend='python_union_find'` is opt-in in `3.3.0`; becomes the default in `3.4.0` only after parity confirmed.
- `backend='auto'` is opt-in in `3.4.0`; must not become the default before `3.5.0`.

---

## Recommended Execution Order

1. Build `3.3.0` first.
2. Implement `clustering_backends/` directory and `python_union_find` before touching any GAE code.
3. Add `LLMProviderConfig` and `Ollama` wiring in the same release as the config cleanup.
4. Add `auto` backend selection only after at least two local backends are stable (`3.4.0`).
5. Evaluate `ONNX` only after the hardware-aware PyTorch path is stable and benchmarked.
6. Add `GAE` last (`3.5.0`), after local backends and config surfaces are fully proven.

---

## Address ER Pipeline — Specialized Implementation Plan

The address pipeline currently lives in `dnb_er` (`scripts/run_er_addresses_search.py`).
It uses `AddressERService` from this library but carries substantial domain knowledge
and hard-won lessons that should be lifted into the library as a first-class specialized
pipeline.

---

### Current State in dnb_er

**Data shape:** ~1.4M address records in the `regaddrs` collection.

**Sharding:** the collection is sharded by ZIP3 (first 3 digits of postal code).
ZIP3 produces a manageable number of shards (~900) compared to ZIP5 (~40K).

**Blocking key:** normalized `street | city | state | zip5`.

**Edge volume:** ~3.9M `address_sameAs` edges at `max_block_size=100`.

**Runtime:** blocking 2-4 minutes; edge creation 2-4 minutes (CSV/arangoimport), or 10-15 minutes (Python API).

**Config:** `config/address_er_config.yaml` in dnb_er. Key values:

```yaml
address_er:
  max_block_size: 100       # registered-agent cap
  min_bm25_score: 2.0
  batch_size: 5000
  edge_collection: address_sameAs
  search_view_name: regaddrs_search

edge_insertion:
  mode: bulk                # CSV + arangoimport (10-20x faster than API)
  bulk_export_file: data/edges/address_sameAs.csv
  edge_batch_size: 1000

field_mapping:
  street_field: ADDRESS_LINE_1
  city_field: PRIMARY_TOWN
  state_field: TERRITORY_CODE
  postal_code_field: POSTAL_CODE
  collection_name: regaddrs

quality:
  max_addresses_in_block: 100
  require_same_state: true
  require_same_zip5: true
```

---

### Known Problems to Fix

#### 1. Cross-Shard Scatter-Gather on COLLECT (current bottleneck)

**Problem:** The blocking query groups by `zip5` (a refinement of the shard key `zip3`),
but ArangoDB does not automatically recognize that a ZIP5 block is always shard-local.
The optimizer fires a scatter-gather: each shard runs `COLLECT` locally, then the
coordinator merges all results. For 1.4M records across ~900 shards, this produces
significant cross-shard coordinator overhead.

**Evidence:** the current `_find_duplicate_addresses` query does:

```aql
FOR addr IN regaddrs
    LET zip5 = SUBSTRING(postal_code, 0, 5)
    LET block_key = CONCAT_SEPARATOR('|', norm_street, norm_city, state, zip5)
    COLLECT block = block_key INTO group = addr._id
    ...
```

ArangoDB's `restrict-to-single-shard` optimizer rule only fires when the query filters
on the exact shard key value (e.g., `FILTER addr.zip3 == "100"`). A `COLLECT` that
groups by a derived value does not trigger it, even if that derived value is a strict
refinement of the shard key.

**Planned fix — shard-parallel approach (target: 3.3.0 or 3.4.0):**

Enumerate distinct ZIP3 values, then run one sub-query per ZIP3. Each sub-query includes
`FILTER SUBSTRING(postal_code, 0, 3) == @zip3` which is the exact shard key, so the
optimizer can route it to a single shard without scatter-gather.

```python
def _find_duplicate_addresses_shard_parallel(self, max_block_size: int, zip3_field: str = 'zip3') -> ...:
    """
    Shard-parallel blocking: one AQL query per ZIP3 value.
    Each query is routed to a single shard (no scatter-gather).
    """
    zip3_values = self._get_distinct_zip3_values()

    all_blocks = {}
    for zip3 in zip3_values:
        query = f"""
        FOR addr IN {self.collection}
            FILTER SUBSTRING(addr.{self.postal_code_field}, 0, 3) == @zip3
            FILTER addr.{self.street_field} != null
            // ... normalization ...
            LET block_key = CONCAT_SEPARATOR('|', norm_street, norm_city, state, zip5)
            COLLECT block = block_key INTO group = addr._id
            LET block_size = LENGTH(group)
            FILTER block_size >= 2 AND block_size <= @max_block_size
            RETURN {{ block_key: block, addresses: group, size: block_size }}
        """
        cursor = self.db.aql.execute(query, bind_vars={'zip3': zip3, 'max_block_size': max_block_size})
        for result in cursor:
            all_blocks[result['block_key']] = result['addresses']

    return all_blocks
```

This approach eliminates coordinator scatter-gather entirely — each query hits
exactly one shard. The trade-off is orchestration overhead (~900 round-trips instead of 1),
but each round-trip is cheap and fully shard-local.

**Library API change required:**

`AddressERService` needs a `blocking_mode` config key:

```yaml
address_er:
  blocking_mode: shard_parallel   # 'single_query' (current) or 'shard_parallel'
  shard_key_field: POSTAL_CODE    # field whose first 3 chars are the shard key
  shard_key_prefix_length: 3      # how many chars of shard key to use
```

#### 2. Edge Insertion: CSV/arangoimport vs Python API

**Problem:** Python `insert_many` is 10-20x slower than `arangoimport` for edge sets
of this size (3.9M edges). The `csv` path (`_create_edges_via_csv`) already exists in
the library and works well. However, AI-assisted debugging sessions keep reverting to
the Python API path because it is simpler to instrument.

**Production expectation:**
- `mode: bulk` (CSV + arangoimport): ~2-4 minutes for 3.9M edges
- `mode: batch` (Python API): ~10-15 minutes for 3.9M edges

**The library must make `bulk` the recommended mode for address-scale datasets.**

Required changes to `AddressERService`:

- Add a log warning at startup when `edge_loading_method='api'` and estimated edge count exceeds 100K:
  ```
  WARNING: Estimated 3.9M edges. Consider edge_loading_method='csv' for 10-20x faster insertion.
  ```
- Add an `arangoimport` availability check at service init time (not at edge-creation time)
  so misconfiguration fails early rather than after the blocking phase completes.
- Document `bulk` as the recommended default for datasets above 100K edges.
- Preserve `api` mode for small datasets and environments without `arangoimport`.

**arangoimport invocation (from the existing `bulk_import_address_edges.sh`):**

```bash
arangoimport \
    --server.endpoint $ARANGO_HOST \
    --server.username $ARANGO_USER \
    --server.password $ARANGO_PASSWORD \
    --server.database $DB_NAME \
    --collection address_sameAs \
    --type csv \
    --file address_sameAs.csv \
    --overwrite false \
    --create-collection false \
    --on-duplicate ignore \
    --threads 4 \
    --batch-size 10000
```

The `--on-duplicate ignore` flag is important: re-running the pipeline should not fail
if edges already exist.

#### 3. Registered Agent / Address Proliferation Filter

**Problem:** some addresses (registered agent offices) are shared by thousands of
companies. Without the `max_block_size` cap, a single block of 22K+ companies would
produce ~242M edges.

**Current fix:** `max_block_size: 100` in config. This is working correctly and must
be preserved.

**Recommended enhancements for the library:**

- Surface `blocks_skipped_by_max_block_size` in the pipeline results dict so operators
  can see how many registered-agent-style blocks were excluded.
- Add an optional `min_block_size` param (already in `quality` config, but not wired
  into `_find_duplicate_addresses`).
- Consider adding a `registered_agent_sample` log: if any block exceeds `max_block_size`,
  log the block key and its size so operators can audit which addresses are being skipped.

**Example result shape after this change:**

```python
{
    'blocks_found': 42000,
    'blocks_skipped_max_size': 127,      # registered-agent-style addresses skipped
    'largest_skipped_block_size': 22411, # useful for auditing
    'addresses_matched': 210000,
    'edges_created': 3900000,
}
```

---

### AddressERPipeline — Proposed Library Class (target: 3.4.0 or 3.5.0)

Extract and generalize the address-specific logic into a first-class library class
that encapsulates all the above decisions.

**New file:** `src/entity_resolution/pipelines/address_pipeline.py`

```python
class AddressERPipeline:
    """
    Specialized ER pipeline for address data at scale.

    Handles the specific challenges of address deduplication:
    - Shard-parallel blocking to avoid cross-shard scatter-gather
    - Registered-agent proliferation filtering (max_block_size cap)
    - arangoimport-backed bulk edge insertion for large edge volumes
    - ZIP3/ZIP5 sharding strategy
    - Configurable normalization and field mapping
    """

    def __init__(
        self,
        db: StandardDatabase,
        collection: str,
        field_mapping: Dict[str, str],
        edge_collection: str = 'address_sameAs',
        search_view_name: Optional[str] = None,
        shard_key_field: Optional[str] = None,   # enables shard-parallel mode
        shard_key_prefix_length: int = 3,         # ZIP3 = 3, ZIP5 = 5
        max_block_size: int = 100,
        min_bm25_score: float = 2.0,
        edge_loading_method: str = 'auto',        # 'api', 'csv', or 'auto'
        csv_path: Optional[str] = None,
        edge_count_threshold_for_csv: int = 100_000,  # switch to CSV above this
    ):
        ...
```

**`edge_loading_method='auto'`** behaviour:

1. Estimate edge count from blocking results.
2. If estimated count > `edge_count_threshold_for_csv` and `arangoimport` is in PATH: use CSV.
3. Otherwise: use Python API.
4. Log the selected method and the reason.

**Config schema:**

```yaml
entity_resolution:
  address_pipeline:
    collection: regaddrs
    edge_collection: address_sameAs
    shard_key_field: POSTAL_CODE
    shard_key_prefix_length: 3
    max_block_size: 100
    min_bm25_score: 2.0
    edge_loading_method: auto
    edge_count_threshold_for_csv: 100000

    field_mapping:
      street: ADDRESS_LINE_1
      city: PRIMARY_TOWN
      state: TERRITORY_CODE
      postal_code: POSTAL_CODE
```

---

### Acceptance Criteria for Address Pipeline

- Shard-parallel blocking produces identical blocks to the current single-query COLLECT.
- Shard-parallel blocking is measurably faster than single-query COLLECT on a sharded cluster with 900+ shards.
- `edge_loading_method='auto'` selects `csv` when `arangoimport` is available and estimated edges exceed threshold.
- `arangoimport` availability is checked at service init, not at edge insertion time.
- A startup warning is emitted when `api` mode is selected for large datasets.
- `blocks_skipped_max_size` and `largest_skipped_block_size` appear in pipeline results.
- Re-running the pipeline does not fail if `address_sameAs` edges already exist (`--on-duplicate ignore`).
- All existing `AddressERService` call sites in `dnb_er` continue to work without changes.

---

### Migration Path for dnb_er

When `AddressERPipeline` is available in the library:

```python
# Before (current dnb_er/scripts/run_er_addresses_search.py)
from entity_resolution.services.address_er_service import AddressERService
service = AddressERService(db=db, collection='regaddrs', field_mapping=..., config=service_config)

# After
from entity_resolution.pipelines import AddressERPipeline
pipeline = AddressERPipeline(
    db=db,
    collection='regaddrs',
    field_mapping=field_mapping,
    shard_key_field='POSTAL_CODE',
    shard_key_prefix_length=3,
    max_block_size=100,
    edge_loading_method='auto',
)
results = pipeline.run(create_edges=True)
```

The dnb_er `config/address_er_config.yaml` maps directly to `AddressERPipeline` parameters
with no semantic changes needed.

---

### Suggested Release Assignment

| Item | Target release | Effort |
|------|---------------|--------|
| `blocks_skipped_max_size` in results dict | `3.3.0` | Small — add counter to existing loop |
| `arangoimport` availability check at init | `3.3.0` | Small — subprocess check |
| Startup warning for large datasets on API mode | `3.3.0` | Small |
| Shard-parallel blocking mode | `3.4.0` | Medium — new query path + config key |
| `edge_loading_method='auto'` selection logic | `3.4.0` | Medium |
| `AddressERPipeline` class extraction | `3.5.0` | Large — new pipeline abstraction |

---

## Related Docs

- `docs/PRD.md` — current product scope and forward-looking roadmap
- `docs/development/RUNTIME_HEALTH_CI_RUNBOOK.md` — Phase 0 runtime baseline/compare/gate operations
- `docs/development/GAE_ENHANCEMENT_PATH.md` — detailed GAE design notes
- `docs/development/PROJECT_EVOLUTION.md` — historical evolution context
- `VERSION_HISTORY.md` — shipped version history
- `~/code/dnb_er/config/address_er_config.yaml` — current dnb_er address config
- `~/code/dnb_er/scripts/run_er_addresses_search.py` — current dnb_er address pipeline driver
