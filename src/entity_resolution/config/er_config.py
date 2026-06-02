"""
Entity Resolution Pipeline Configuration

Provides configuration classes for defining ER pipelines via YAML/JSON.
Supports validation, defaults, and environment variable overrides.
"""

from typing import Dict, List, Any, Optional, Union
from pathlib import Path
import yaml
import json

from ..utils.constants import DEFAULT_SIMILARITY_THRESHOLD, DEFAULT_BATCH_SIZE


class BlockingConfig:
    """Blocking configuration."""
    
    def __init__(
        self,
        strategy: str = "exact",
        max_block_size: int = 100,
        min_block_size: int = 2,
        fields: Optional[List[Dict[str, Any]]] = None,
        search_field: Optional[str] = None,
        blocking_field: Optional[str] = None,
        embedding_field: Optional[str] = None,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        limit_per_entity: int = 20,
        num_hash_tables: int = 10,
        num_hyperplanes: int = 8,
        random_seed: Optional[int] = 42,
        allow_unsafe_expressions: bool = False,
    ):
        """
        Initialize blocking configuration.

        Args:
            strategy: Blocking strategy.
                - ``"bm25"`` — ArangoSearch BM25 (recommended)
                - ``"arangosearch"`` — deprecated alias for ``"bm25"``
                - ``"exact"`` — COLLECT-based exact field matching
            max_block_size: Maximum documents per block
            min_block_size: Minimum documents per block
            fields: List of field configurations for blocking
            search_field: Field to run BM25 search against (bm25 strategy only).
                Defaults to the first entry in ``fields`` when not provided.
            blocking_field: Hard-filter field used as a pre-partition in BM25 blocking
                (e.g. ``"state"``).  Defaults to the second entry in ``fields`` when
                not provided.  Set to ``None`` to disable the pre-partition filter.
            embedding_field: Embedding vector field for vector/LSH blocking.
            similarity_threshold: Vector blocking minimum cosine similarity.
            limit_per_entity: Vector blocking max candidates per entity.
            num_hash_tables: LSH number of hash tables.
            num_hyperplanes: LSH number of hyperplanes per table.
            random_seed: LSH seed for deterministic hashing.
            allow_unsafe_expressions: When ``False`` (default), computed-field
                AQL expressions are validated to reject data-modification
                keywords, sub-queries, and comment/break-out sequences (these
                expressions are interpolated directly into generated AQL).
                Set ``True`` only for trusted configs that require advanced
                AQL that the validator would otherwise reject.
        """
        self.strategy = strategy
        self.max_block_size = max_block_size
        self.min_block_size = min_block_size
        self.fields = fields or []
        self.search_field = search_field
        self.blocking_field = blocking_field
        self.embedding_field = embedding_field
        self.similarity_threshold = similarity_threshold
        self.limit_per_entity = limit_per_entity
        self.num_hash_tables = num_hash_tables
        self.num_hyperplanes = num_hyperplanes
        self.random_seed = random_seed
        self.allow_unsafe_expressions = allow_unsafe_expressions
    
    def parse_fields(self) -> tuple[list[str], dict[str, str]]:
        """
        Parse ``self.fields`` into (field_names, computed_fields).

        This is the **canonical** implementation shared by both
        ``ERPipelineConfig._get_blocking_field_names`` and
        ``ConfigurableERPipeline._get_blocking_fields``.  Keeping the
        logic here (on the config object that owns the data) means there
        is only one place to update if the field schema changes (H3).

        Supported item formats:
        - ``str``  → plain field name, no computed expression.
        - ``dict`` → must have ``"name"`` or ``"field"`` key; optional
          ``"expression"``/``"aql"`` key for AQL computed-field expressions.

        Returns:
            A 2-tuple of:
            - ``field_names``: de-duplicated, order-preserving list of field names.
            - ``computed_fields``: mapping of ``{field_name: aql_expression}``
              for fields that carry an expression.
        """
        field_names: list[str] = []
        computed_fields: dict[str, str] = {}

        for item in (self.fields or []):
            if isinstance(item, str):
                name = item.strip()
            elif isinstance(item, dict):
                name = (item.get("name") or item.get("field") or "").strip()
                expr = item.get("expression") or item.get("aql")
                if name and isinstance(expr, str) and expr.strip():
                    if getattr(self, "allow_unsafe_expressions", False):
                        computed_fields[name] = expr.strip()
                    else:
                        # Validate config-supplied AQL expressions before they
                        # are interpolated into generated queries (AQL injection
                        # prevention).
                        from ..utils.validation import (
                            validate_computed_field_expression,
                        )
                        computed_fields[name] = validate_computed_field_expression(expr)
            else:
                continue
            if name:
                field_names.append(name)

        # De-dup while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for name in field_names:
            if name not in seen:
                seen.add(name)
                deduped.append(name)

        return deduped, computed_fields

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'BlockingConfig':
        """Create from dictionary."""
        return cls(
            strategy=config_dict.get('strategy', 'exact'),
            max_block_size=config_dict.get('max_block_size', 100),
            min_block_size=config_dict.get('min_block_size', 2),
            fields=config_dict.get('fields', []),
            search_field=config_dict.get('search_field'),
            blocking_field=config_dict.get('blocking_field'),
            embedding_field=config_dict.get('embedding_field'),
            similarity_threshold=config_dict.get('similarity_threshold', DEFAULT_SIMILARITY_THRESHOLD),
            limit_per_entity=config_dict.get('limit_per_entity', 20),
            num_hash_tables=config_dict.get('num_hash_tables', 10),
            num_hyperplanes=config_dict.get('num_hyperplanes', 8),
            random_seed=config_dict.get('random_seed', 42),
            allow_unsafe_expressions=config_dict.get('allow_unsafe_expressions', False),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result: Dict[str, Any] = {
            'strategy': self.strategy,
            'max_block_size': self.max_block_size,
            'min_block_size': self.min_block_size,
            'fields': self.fields,
        }
        if self.search_field is not None:
            result['search_field'] = self.search_field
        if self.blocking_field is not None:
            result['blocking_field'] = self.blocking_field
        if self.embedding_field is not None:
            result['embedding_field'] = self.embedding_field
        result['similarity_threshold'] = self.similarity_threshold
        result['limit_per_entity'] = self.limit_per_entity
        result['num_hash_tables'] = self.num_hash_tables
        result['num_hyperplanes'] = self.num_hyperplanes
        if self.random_seed is not None:
            result['random_seed'] = self.random_seed
        return result



class SimilarityConfig:
    """Similarity configuration."""
    
    def __init__(
        self,
        algorithm: str = "jaro_winkler",
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        batch_size: int = DEFAULT_BATCH_SIZE,
        field_weights: Optional[Dict[str, float]] = None,
        transformers: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize similarity configuration.
        
        Args:
            algorithm: Similarity algorithm ("jaro_winkler", "levenshtein", "jaccard")
            threshold: Minimum similarity threshold (0.0-1.0). Default DEFAULT_SIMILARITY_THRESHOLD (0.75).
            batch_size: Batch size for similarity computation. Default DEFAULT_BATCH_SIZE (5000).
            field_weights: Dictionary of field names to weights
            transformers: Optional per-field transformer registry applied before
                similarity scoring.
        """
        self.algorithm = algorithm
        self.threshold = threshold
        self.batch_size = batch_size
        self.field_weights = field_weights or {}
        self.transformers = transformers or {}
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'SimilarityConfig':
        """Create from dictionary."""
        return cls(
            algorithm=config_dict.get('algorithm', 'jaro_winkler'),
            threshold=config_dict.get('threshold', DEFAULT_SIMILARITY_THRESHOLD),
            batch_size=config_dict.get('batch_size', DEFAULT_BATCH_SIZE),
            field_weights=config_dict.get('field_weights', {}),
            transformers=config_dict.get('transformers', {})
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'algorithm': self.algorithm,
            'threshold': self.threshold,
            'batch_size': self.batch_size,
            'field_weights': self.field_weights,
            'transformers': self.transformers,
        }


class GAEClusteringConfig:
    """Configuration for optional ArangoDB Graph Analytics Engine (GAE) clustering.

    GAE is an enterprise capability for very large graphs (>10M edges).
    This backend is optional and capability-gated; the system falls back
    to local backends when GAE is unavailable.

    ``deployment_mode`` values:

    - ``self_managed`` -- caller manages the graph lifecycle
    - ``auto`` -- service creates/deletes a temporary graph automatically
    """

    VALID_DEPLOYMENT_MODES = ("self_managed", "auto")

    def __init__(
        self,
        enabled: bool = False,
        deployment_mode: str = "self_managed",
        graph_name: Optional[str] = None,
        engine_size: str = "e16",
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
    def from_dict(cls, config_dict: Dict[str, Any]) -> "GAEClusteringConfig":
        return cls(
            enabled=config_dict.get("enabled", False),
            deployment_mode=config_dict.get("deployment_mode", "self_managed"),
            graph_name=config_dict.get("graph_name"),
            engine_size=config_dict.get("engine_size", "e16"),
            auto_cleanup=config_dict.get("auto_cleanup", True),
            timeout_seconds=config_dict.get("timeout_seconds", 3600),
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "enabled": self.enabled,
            "deployment_mode": self.deployment_mode,
            "engine_size": self.engine_size,
            "auto_cleanup": self.auto_cleanup,
            "timeout_seconds": self.timeout_seconds,
        }
        if self.graph_name is not None:
            result["graph_name"] = self.graph_name
        return result

    def validate(self) -> List[str]:
        errors: List[str] = []
        if self.deployment_mode not in self.VALID_DEPLOYMENT_MODES:
            errors.append(
                f"deployment_mode must be one of {self.VALID_DEPLOYMENT_MODES}, "
                f"got: {self.deployment_mode!r}"
            )
        if self.timeout_seconds < 1:
            errors.append(
                f"timeout_seconds must be >= 1, got: {self.timeout_seconds}"
            )
        if self.enabled and self.deployment_mode == "self_managed" and not self.graph_name:
            errors.append(
                "graph_name is required when gae.enabled=True and "
                "deployment_mode='self_managed'"
            )
        return errors


class ClusteringConfig:
    """Clustering configuration.

    The ``backend`` field selects the WCC algorithm implementation:

    - ``python_dfs`` -- bulk edge fetch + iterative DFS
    - ``python_union_find`` -- bulk edge fetch + Union-Find
    - ``python_sparse`` -- scipy sparse matrix WCC (optional, large graphs)
    - ``aql_graph`` -- per-vertex server-side AQL traversal
    - ``gae_wcc`` -- ArangoDB Graph Analytics Engine (enterprise)
    - ``auto`` -- automatic selection based on edge count (default since 3.5.0)

    The legacy ``wcc_algorithm`` parameter is still accepted for backward
    compatibility but emits a ``DeprecationWarning``.
    """

    _WCC_ALGORITHM_TO_BACKEND = {
        "python_dfs": "python_dfs",
        "aql_graph": "aql_graph",
    }

    VALID_BACKENDS = (
        "python_dfs", "python_union_find", "python_sparse",
        "aql_graph", "gae_wcc", "auto",
    )

    def __init__(
        self,
        algorithm: str = "wcc",
        min_cluster_size: int = 2,
        store_results: bool = True,
        backend: str = "auto",
        wcc_algorithm: Optional[str] = None,
        auto_select_threshold_edges: int = 2_000_000,
        sparse_backend_enabled: bool = True,
        gae: Optional[GAEClusteringConfig] = None,
    ):
        """
        Initialize clustering configuration.

        Args:
            algorithm: Clustering algorithm ("wcc")
            min_cluster_size: Minimum entities per cluster
            store_results: Whether to store cluster results
            backend: Clustering backend. Default changed to ``auto`` in 3.5.0.
            wcc_algorithm: Deprecated -- use ``backend`` instead.
                If provided, maps to ``backend`` and emits a DeprecationWarning.
            auto_select_threshold_edges: Edge count above which ``auto`` backend
                prefers ``python_sparse`` or GAE. Default 2M.
            sparse_backend_enabled: Whether ``auto`` backend may select
                ``python_sparse``. Default True.
            gae: Optional GAE clustering configuration.
        """
        import warnings

        self.algorithm = algorithm
        self.min_cluster_size = min_cluster_size
        self.store_results = store_results
        self.auto_select_threshold_edges = auto_select_threshold_edges
        self.sparse_backend_enabled = sparse_backend_enabled
        self.gae = gae

        if wcc_algorithm is not None:
            warnings.warn(
                "ClusteringConfig.wcc_algorithm is deprecated and will be removed "
                "in a future release. Use backend= instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            self.backend = self._WCC_ALGORITHM_TO_BACKEND.get(
                wcc_algorithm, wcc_algorithm
            )
        else:
            self.backend = backend

        # Keep wcc_algorithm in sync for any code that still reads it
        self.wcc_algorithm = self.backend

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'ClusteringConfig':
        """Create from dictionary."""
        gae_dict = config_dict.get("gae")
        gae = GAEClusteringConfig.from_dict(gae_dict) if gae_dict else None
        return cls(
            algorithm=config_dict.get('algorithm', 'wcc'),
            min_cluster_size=config_dict.get('min_cluster_size', 2),
            store_results=config_dict.get('store_results', True),
            backend=config_dict.get('backend', 'auto'),
            wcc_algorithm=config_dict.get('wcc_algorithm'),
            auto_select_threshold_edges=config_dict.get('auto_select_threshold_edges', 2_000_000),
            sparse_backend_enabled=config_dict.get('sparse_backend_enabled', True),
            gae=gae,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            'algorithm': self.algorithm,
            'min_cluster_size': self.min_cluster_size,
            'store_results': self.store_results,
            'backend': self.backend,
        }
        if self.auto_select_threshold_edges != 2_000_000:
            result['auto_select_threshold_edges'] = self.auto_select_threshold_edges
        if not self.sparse_backend_enabled:
            result['sparse_backend_enabled'] = self.sparse_backend_enabled
        if self.gae is not None:
            result['gae'] = self.gae.to_dict()
        return result

    def validate(self) -> List[str]:
        """Validate clustering configuration."""
        errors: List[str] = []
        if self.backend not in self.VALID_BACKENDS:
            errors.append(
                f"backend must be one of {self.VALID_BACKENDS}, got: {self.backend!r}"
            )
        if self.min_cluster_size < 1:
            errors.append(
                f"min_cluster_size must be >= 1, got: {self.min_cluster_size}"
            )
        if self.auto_select_threshold_edges < 1:
            errors.append(
                f"auto_select_threshold_edges must be >= 1, got: {self.auto_select_threshold_edges}"
            )
        if self.gae is not None:
            errors.extend(self.gae.validate())
        return errors


class EmbeddingConfig:
    """Embedding configuration for vector-based blocking."""
    
    def __init__(
        self,
        model_name: str = 'all-MiniLM-L6-v2',
        runtime: str = 'pytorch',
        device: str = 'auto',
        provider: str = 'cpu',
        provider_options: Optional[Dict[str, Any]] = None,
        onnx_model_path: Optional[str] = None,
        startup_mode: str = 'permissive',
        coreml_use_basic_optimizations: bool = True,
        coreml_warmup_runs: int = 10,
        coreml_max_p95_latency_ms: float = 65.0,
        coreml_warmup_batch_size: int = 8,
        coreml_warmup_seq_len: int = 128,
        embedding_field: str = 'embedding_vector',
        multi_resolution_mode: bool = False,
        coarse_model_name: Optional[str] = None,
        fine_model_name: Optional[str] = None,
        embedding_field_coarse: str = 'embedding_vector_coarse',
        embedding_field_fine: str = 'embedding_vector_fine',
        profile: str = 'default',
        batch_size: int = 32,
        max_batch_size: Optional[int] = None,
    ):
        """
        Initialize embedding configuration.
        
        Args:
            model_name: Sentence-transformers model name (legacy mode or fine model)
            runtime: Embedding runtime ('pytorch' or 'onnxruntime')
            device: Device for pytorch inference ('cpu', 'cuda', 'mps', or 'auto').
                Default changed to 'auto' in 3.4.0 (MPS/CUDA parity confirmed in 3.3.0).
            provider: Provider for onnxruntime ('cpu', 'coreml', 'cuda', 'tensorrt', or 'auto')
            provider_options: Optional provider-specific options for onnxruntime
            onnx_model_path: Optional path to ONNX model artifact when using onnxruntime
            startup_mode: Runtime startup policy ('permissive' or 'strict')
            coreml_use_basic_optimizations: Use ORT_ENABLE_BASIC for CoreML sessions
            coreml_warmup_runs: Number of warmup inference probes for CoreML
            coreml_max_p95_latency_ms: Warmup p95 threshold that triggers CPU fallback
            coreml_warmup_batch_size: Warmup batch size used for synthetic CoreML probes
            coreml_warmup_seq_len: Warmup sequence length used for synthetic CoreML probes
            embedding_field: Field name for storing embeddings (legacy mode)
            multi_resolution_mode: Enable multi-resolution embeddings (coarse + fine)
            coarse_model_name: Model name for coarse embeddings (required if multi_resolution_mode=True)
            fine_model_name: Model name for fine embeddings (defaults to model_name if None)
            embedding_field_coarse: Field name for coarse embeddings
            embedding_field_fine: Field name for fine embeddings
            profile: Profile name for metadata tracking
            batch_size: Batch size for embedding generation
            max_batch_size: Hard ceiling for batch size to prevent OOM on GPU devices
        """
        self.model_name = model_name
        self.runtime = runtime
        self.device = device
        self.provider = provider
        self.provider_options = provider_options or {}
        self.onnx_model_path = onnx_model_path
        self.startup_mode = startup_mode
        self.coreml_use_basic_optimizations = coreml_use_basic_optimizations
        self.coreml_warmup_runs = coreml_warmup_runs
        self.coreml_max_p95_latency_ms = coreml_max_p95_latency_ms
        self.coreml_warmup_batch_size = coreml_warmup_batch_size
        self.coreml_warmup_seq_len = coreml_warmup_seq_len
        self.embedding_field = embedding_field
        self.multi_resolution_mode = multi_resolution_mode
        self.coarse_model_name = coarse_model_name
        self.fine_model_name = fine_model_name
        self.embedding_field_coarse = embedding_field_coarse
        self.embedding_field_fine = embedding_field_fine
        self.profile = profile
        self.batch_size = batch_size
        self.max_batch_size = max_batch_size
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'EmbeddingConfig':
        """Create from dictionary."""
        return cls(
            model_name=config_dict.get('model_name', 'all-MiniLM-L6-v2'),
            runtime=config_dict.get('runtime', 'pytorch'),
            device=config_dict.get('device', 'auto'),
            provider=config_dict.get('provider', 'cpu'),
            provider_options=config_dict.get('provider_options', {}),
            onnx_model_path=config_dict.get('onnx_model_path'),
            startup_mode=config_dict.get('startup_mode', 'permissive'),
            coreml_use_basic_optimizations=config_dict.get('coreml_use_basic_optimizations', True),
            coreml_warmup_runs=config_dict.get('coreml_warmup_runs', 10),
            coreml_max_p95_latency_ms=config_dict.get('coreml_max_p95_latency_ms', 65.0),
            coreml_warmup_batch_size=config_dict.get('coreml_warmup_batch_size', 8),
            coreml_warmup_seq_len=config_dict.get('coreml_warmup_seq_len', 128),
            embedding_field=config_dict.get('embedding_field', 'embedding_vector'),
            multi_resolution_mode=config_dict.get('multi_resolution_mode', False),
            coarse_model_name=config_dict.get('coarse_model_name'),
            fine_model_name=config_dict.get('fine_model_name'),
            embedding_field_coarse=config_dict.get('embedding_field_coarse', 'embedding_vector_coarse'),
            embedding_field_fine=config_dict.get('embedding_field_fine', 'embedding_vector_fine'),
            profile=config_dict.get('profile', 'default'),
            batch_size=config_dict.get('batch_size', 32),
            max_batch_size=config_dict.get('max_batch_size'),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            'model_name': self.model_name,
            'runtime': self.runtime,
            'device': self.device,
            'provider': self.provider,
            'provider_options': self.provider_options,
            'startup_mode': self.startup_mode,
            'coreml_use_basic_optimizations': self.coreml_use_basic_optimizations,
            'coreml_warmup_runs': self.coreml_warmup_runs,
            'coreml_max_p95_latency_ms': self.coreml_max_p95_latency_ms,
            'coreml_warmup_batch_size': self.coreml_warmup_batch_size,
            'coreml_warmup_seq_len': self.coreml_warmup_seq_len,
            'embedding_field': self.embedding_field,
            'multi_resolution_mode': self.multi_resolution_mode,
            'profile': self.profile,
            'batch_size': self.batch_size,
        }
        if self.max_batch_size is not None:
            result['max_batch_size'] = self.max_batch_size
        if self.onnx_model_path is not None:
            result['onnx_model_path'] = self.onnx_model_path
        
        if self.multi_resolution_mode:
            result.update({
                'coarse_model_name': self.coarse_model_name,
                'fine_model_name': self.fine_model_name,
                'embedding_field_coarse': self.embedding_field_coarse,
                'embedding_field_fine': self.embedding_field_fine
            })
        
        return result
    
    def validate(self) -> List[str]:
        """
        Validate embedding configuration.
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        if self.multi_resolution_mode:
            if not self.coarse_model_name:
                errors.append(
                    "coarse_model_name is required when multi_resolution_mode=True"
                )
        
        if self.device not in ('cpu', 'cuda', 'mps', 'auto'):
            errors.append(
                "device must be 'cpu', 'cuda', 'mps', or 'auto', "
                f"got: {self.device}"
            )

        if self.runtime not in ('pytorch', 'onnxruntime'):
            errors.append(
                "runtime must be 'pytorch' or 'onnxruntime', "
                f"got: {self.runtime}"
            )

        if self.provider not in ('cpu', 'coreml', 'cuda', 'tensorrt', 'auto'):
            errors.append(
                "provider must be 'cpu', 'coreml', 'cuda', 'tensorrt', or 'auto', "
                f"got: {self.provider}"
            )

        if not isinstance(self.provider_options, dict):
            errors.append("provider_options must be a dictionary")

        if self.runtime == 'onnxruntime' and not self.onnx_model_path:
            errors.append("onnx_model_path is required when runtime == 'onnxruntime'")

        if self.startup_mode not in ('permissive', 'strict'):
            errors.append(
                "startup_mode must be 'permissive' or 'strict', "
                f"got: {self.startup_mode}"
            )
        if self.coreml_warmup_runs < 0:
            errors.append(
                f"coreml_warmup_runs must be >= 0, got: {self.coreml_warmup_runs}"
            )
        if self.coreml_max_p95_latency_ms <= 0:
            errors.append(
                "coreml_max_p95_latency_ms must be > 0, "
                f"got: {self.coreml_max_p95_latency_ms}"
            )
        if self.coreml_warmup_batch_size < 1:
            errors.append(
                f"coreml_warmup_batch_size must be >= 1, got: {self.coreml_warmup_batch_size}"
            )
        if self.coreml_warmup_seq_len < 1:
            errors.append(
                f"coreml_warmup_seq_len must be >= 1, got: {self.coreml_warmup_seq_len}"
            )
        
        if self.batch_size < 1:
            errors.append(f"batch_size must be >= 1, got: {self.batch_size}")
        if self.max_batch_size is not None and self.max_batch_size < 1:
            errors.append(f"max_batch_size must be >= 1, got: {self.max_batch_size}")
        
        return errors


class LLMProviderConfig:
    """Structured LLM provider configuration.

    Translates provider/model settings into a litellm model string.
    litellm already supports Ollama natively via ``ollama/model_name``
    with ``base_url`` pointing at the local server.

    Example (Ollama)::

        LLMProviderConfig(provider='ollama', model='llama3.1:8b')
        # to_litellm_model_string() -> 'ollama/llama3.1:8b'

    Example (OpenRouter)::

        LLMProviderConfig(provider='openrouter', model='google/gemini-2.0-flash')
        # to_litellm_model_string() -> 'openrouter/google/gemini-2.0-flash'
    """

    PROVIDER_BASE_URLS = {
        "ollama": "http://localhost:11434",
    }

    VALID_PROVIDERS = ("openrouter", "openai", "anthropic", "ollama")

    def __init__(
        self,
        provider: str = "openrouter",
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key_env: Optional[str] = None,
        timeout_seconds: int = 60,
        healthcheck_on_start: bool = False,
        fallback_provider: Optional[str] = None,
    ):
        self.provider = provider
        self.model = model
        self.base_url = base_url or self.PROVIDER_BASE_URLS.get(provider)
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds
        self.healthcheck_on_start = healthcheck_on_start
        self.fallback_provider = fallback_provider

    def to_litellm_model_string(self) -> Optional[str]:
        """Return the litellm model string, or ``None`` if model is unset."""
        if not self.model:
            return None
        if self.provider in self.VALID_PROVIDERS:
            return f"{self.provider}/{self.model}"
        return self.model

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'LLMProviderConfig':
        return cls(
            provider=config_dict.get("provider", "openrouter"),
            model=config_dict.get("model"),
            base_url=config_dict.get("base_url"),
            api_key_env=config_dict.get("api_key_env"),
            timeout_seconds=config_dict.get("timeout_seconds", 60),
            healthcheck_on_start=config_dict.get("healthcheck_on_start", False),
            fallback_provider=config_dict.get("fallback_provider"),
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "provider": self.provider,
            "timeout_seconds": self.timeout_seconds,
            "healthcheck_on_start": self.healthcheck_on_start,
        }
        if self.model is not None:
            result["model"] = self.model
        if self.base_url is not None:
            result["base_url"] = self.base_url
        if self.api_key_env is not None:
            result["api_key_env"] = self.api_key_env
        if self.fallback_provider is not None:
            result["fallback_provider"] = self.fallback_provider
        return result

    def validate(self) -> List[str]:
        errors: List[str] = []
        if self.provider not in self.VALID_PROVIDERS:
            errors.append(
                f"provider must be one of {self.VALID_PROVIDERS}, got: {self.provider!r}"
            )
        if self.timeout_seconds < 1:
            errors.append(
                f"timeout_seconds must be >= 1, got: {self.timeout_seconds}"
            )
        if self.fallback_provider is not None and self.fallback_provider not in self.VALID_PROVIDERS:
            errors.append(
                f"fallback_provider must be one of {self.VALID_PROVIDERS}, "
                f"got: {self.fallback_provider!r}"
            )
        return errors


class ActiveLearningConfig:
    """Opt-in active learning / LLM verification configuration.

    The ``llm`` field accepts a structured :class:`LLMProviderConfig`.
    When set, ``effective_model_string()`` prefers it over the bare
    ``model`` string for backward compatibility.
    """

    def __init__(
        self,
        enabled: bool = False,
        feedback_collection: Optional[str] = None,
        refresh_every: int = 100,
        model: Optional[str] = None,
        low_threshold: float = 0.55,
        high_threshold: float = 0.80,
        optimizer_target_precision: float = 0.95,
        optimizer_min_samples: int = 20,
        llm: Optional[LLMProviderConfig] = None,
    ):
        self.enabled = enabled
        self.feedback_collection = feedback_collection
        self.refresh_every = refresh_every
        self.model = model
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold
        self.optimizer_target_precision = optimizer_target_precision
        self.optimizer_min_samples = optimizer_min_samples
        self.llm = llm

    def effective_model_string(self) -> Optional[str]:
        """Return the litellm model string, preferring ``llm`` over bare ``model``."""
        if self.llm is not None:
            return self.llm.to_litellm_model_string()
        return self.model

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'ActiveLearningConfig':
        """Create from dictionary."""
        llm_dict = config_dict.get("llm")
        llm = LLMProviderConfig.from_dict(llm_dict) if llm_dict else None
        return cls(
            enabled=config_dict.get('enabled', False),
            feedback_collection=config_dict.get('feedback_collection'),
            refresh_every=config_dict.get('refresh_every', 100),
            model=config_dict.get('model'),
            low_threshold=config_dict.get('low_threshold', 0.55),
            high_threshold=config_dict.get('high_threshold', 0.80),
            optimizer_target_precision=config_dict.get('optimizer_target_precision', 0.95),
            optimizer_min_samples=config_dict.get('optimizer_min_samples', 20),
            llm=llm,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result: Dict[str, Any] = {
            'enabled': self.enabled,
            'refresh_every': self.refresh_every,
            'low_threshold': self.low_threshold,
            'high_threshold': self.high_threshold,
            'optimizer_target_precision': self.optimizer_target_precision,
            'optimizer_min_samples': self.optimizer_min_samples,
        }
        if self.feedback_collection is not None:
            result['feedback_collection'] = self.feedback_collection
        if self.model is not None:
            result['model'] = self.model
        if self.llm is not None:
            result['llm'] = self.llm.to_dict()
        return result

    def validate(self) -> List[str]:
        """Validate active learning configuration."""
        errors = []
        if self.refresh_every < 1:
            errors.append(f"refresh_every must be >= 1, got: {self.refresh_every}")
        if not 0.0 <= self.low_threshold <= 1.0:
            errors.append(f"low_threshold must be between 0.0 and 1.0, got: {self.low_threshold}")
        if not 0.0 <= self.high_threshold <= 1.0:
            errors.append(f"high_threshold must be between 0.0 and 1.0, got: {self.high_threshold}")
        if self.low_threshold >= self.high_threshold:
            errors.append(
                f"low_threshold ({self.low_threshold}) must be < high_threshold ({self.high_threshold})"
            )
        if not 0.0 < self.optimizer_target_precision <= 1.0:
            errors.append(
                "optimizer_target_precision must be > 0.0 and <= 1.0, "
                f"got: {self.optimizer_target_precision}"
            )
        if self.optimizer_min_samples < 1:
            errors.append(
                f"optimizer_min_samples must be >= 1, got: {self.optimizer_min_samples}"
            )
        if self.llm is not None:
            errors.extend(self.llm.validate())
        return errors


class CanonicalETLConfig:
    """Configuration for ETL-time canonical deduplication."""

    def __init__(
        self,
        locale: str = "en_US",
        signature_fields: Optional[List[str]] = None,
        shard_key_field: str = "postal",
        shard_key_length: int = 3,
        hub_threshold: int = 50,
        provenance: bool = True,
        max_variants: int = 20,
        field_mapping: Optional[Dict[str, str]] = None,
        hub_markers: Optional[Dict[str, str]] = None,
    ):
        self.locale = locale
        self.signature_fields = signature_fields or ["street", "city", "state", "postal"]
        self.shard_key_field = shard_key_field
        self.shard_key_length = shard_key_length
        self.hub_threshold = hub_threshold
        self.provenance = provenance
        self.max_variants = max_variants
        self.field_mapping = field_mapping or {}
        self.hub_markers = hub_markers or {}

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'CanonicalETLConfig':
        """Create from dictionary."""
        return cls(
            locale=config_dict.get('locale', 'en_US'),
            signature_fields=config_dict.get('signature_fields'),
            shard_key_field=config_dict.get('shard_key_field', 'postal'),
            shard_key_length=config_dict.get('shard_key_length', 3),
            hub_threshold=config_dict.get('hub_threshold', 50),
            provenance=config_dict.get('provenance', True),
            max_variants=config_dict.get('max_variants', 20),
            field_mapping=config_dict.get('field_mapping', {}),
            hub_markers=config_dict.get('hub_markers', {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'locale': self.locale,
            'signature_fields': self.signature_fields,
            'shard_key_field': self.shard_key_field,
            'shard_key_length': self.shard_key_length,
            'hub_threshold': self.hub_threshold,
            'provenance': self.provenance,
            'max_variants': self.max_variants,
            'field_mapping': self.field_mapping,
            'hub_markers': self.hub_markers,
        }

    def validate(self) -> List[str]:
        """Validate configuration."""
        errors = []
        if not self.signature_fields:
            errors.append("etl.canonical.signature_fields must not be empty")
        if self.shard_key_length < 1:
            errors.append(f"etl.canonical.shard_key_length must be >= 1, got: {self.shard_key_length}")
        if self.hub_threshold < 1:
            errors.append(f"etl.canonical.hub_threshold must be >= 1, got: {self.hub_threshold}")
        if self.max_variants < 1:
            errors.append(f"etl.canonical.max_variants must be >= 1, got: {self.max_variants}")
        return errors


class ERPipelineConfig:
    """
    Complete ER pipeline configuration.
    
    Supports loading from YAML/JSON files and provides validation.
    
    Example YAML:
        ```yaml
        entity_resolution:
          entity_type: "address"
          collection_name: "addresses"
          edge_collection: "address_sameAs"
          cluster_collection: "address_clusters"
          
          blocking:
            strategy: "arangosearch"
            max_block_size: 100
            min_block_size: 2
          
          similarity:
            algorithm: "jaro_winkler"
            threshold: 0.75  # Use DEFAULT_SIMILARITY_THRESHOLD in code
            field_weights:
              street: 0.5
              city: 0.3
              state: 0.1
              postal_code: 0.1
          
          clustering:
            algorithm: "wcc"
            min_cluster_size: 2
            wcc_algorithm: "python_dfs"
        ```
    """
    
    def __init__(
        self,
        entity_type: str,
        collection_name: str,
        edge_collection: str = "similarTo",
        cluster_collection: str = "entity_clusters",
        blocking: Optional[BlockingConfig] = None,
        similarity: Optional[SimilarityConfig] = None,
        clustering: Optional[ClusteringConfig] = None,
        embedding: Optional[EmbeddingConfig] = None,
        active_learning: Optional[ActiveLearningConfig] = None,
        canonical_etl: Optional[CanonicalETLConfig] = None,
    ):
        """
        Initialize ER pipeline configuration.
        
        Args:
            entity_type: Type of entity ("address", "person", "company", etc.)
            collection_name: Source collection name
            edge_collection: Edge collection name
            cluster_collection: Cluster collection name
            blocking: Blocking configuration
            similarity: Similarity configuration
            clustering: Clustering configuration
            embedding: Embedding configuration (optional)
            active_learning: Active learning configuration (optional)
            canonical_etl: Canonical ETL configuration (optional)
        """
        self.entity_type = entity_type
        self.collection_name = collection_name
        self.edge_collection = edge_collection
        self.cluster_collection = cluster_collection

        self.blocking = blocking or BlockingConfig()
        self.similarity = similarity or SimilarityConfig()
        self.clustering = clustering or ClusteringConfig()
        self.embedding = embedding
        self.active_learning = active_learning or ActiveLearningConfig()
        self.canonical_etl = canonical_etl
    
    @classmethod
    def from_yaml(cls, config_path: Union[str, Path]) -> 'ERPipelineConfig':
        """
        Load configuration from YAML file.
        
        Args:
            config_path: Path to YAML configuration file
        
        Returns:
            ERPipelineConfig instance
        
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If configuration is invalid
        """
        config_path = Path(config_path)
        
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_path, 'r') as f:
            config_dict = yaml.safe_load(f)
        
        return cls.from_dict(config_dict)
    
    @classmethod
    def from_json(cls, config_path: Union[str, Path]) -> 'ERPipelineConfig':
        """
        Load configuration from JSON file.
        
        Args:
            config_path: Path to JSON configuration file
        
        Returns:
            ERPipelineConfig instance
        
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If configuration is invalid
        """
        config_path = Path(config_path)
        
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_path, 'r') as f:
            config_dict = json.load(f)
        
        return cls.from_dict(config_dict)
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'ERPipelineConfig':
        """
        Load configuration from dictionary.
        
        Args:
            config_dict: Configuration dictionary (may have 'entity_resolution' key)
        
        Returns:
            ERPipelineConfig instance
        """
        # Handle nested 'entity_resolution' key
        if 'entity_resolution' in config_dict:
            config_dict = config_dict['entity_resolution']
        
        # Extract sub-configurations
        blocking_config = BlockingConfig.from_dict(
            config_dict.get('blocking', {})
        )
        similarity_config = SimilarityConfig.from_dict(
            config_dict.get('similarity', {})
        )
        clustering_config = ClusteringConfig.from_dict(
            config_dict.get('clustering', {})
        )
        embedding_config = None
        if 'embedding' in config_dict:
            embedding_config = EmbeddingConfig.from_dict(config_dict.get('embedding', {}))
        active_learning_config = None
        if 'active_learning' in config_dict:
            active_learning_config = ActiveLearningConfig.from_dict(config_dict.get('active_learning', {}))
        canonical_etl_config = None
        etl_section = config_dict.get('etl', {})
        if 'canonical' in etl_section:
            canonical_etl_config = CanonicalETLConfig.from_dict(etl_section['canonical'])
        
        return cls(
            entity_type=config_dict.get('entity_type', 'entity'),
            collection_name=config_dict.get('collection_name', 'entities'),
            edge_collection=config_dict.get('edge_collection', 'similarTo'),
            cluster_collection=config_dict.get('cluster_collection', 'entity_clusters'),
            blocking=blocking_config,
            similarity=similarity_config,
            clustering=clustering_config,
            embedding=embedding_config,
            active_learning=active_learning_config,
            canonical_etl=canonical_etl_config,
        )

    def _get_blocking_field_names(self) -> List[str]:
        """
        Extract normalised blocking field names from config.

        Delegates to ``BlockingConfig.parse_fields()`` (H3 — single canonical
        implementation; no local duplication).
        """
        names, _ = self.blocking.parse_fields()
        return names
    
    def validate(self) -> List[str]:
        """
        Validate configuration.
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Validate blocking
        if self.blocking.max_block_size < self.blocking.min_block_size:
            errors.append(
                f"blocking.max_block_size ({self.blocking.max_block_size}) must be >= "
                f"blocking.min_block_size ({self.blocking.min_block_size})"
            )
        
        if self.blocking.strategy not in ('exact', 'arangosearch', 'bm25', 'vector', 'lsh'):
            errors.append(
                "blocking.strategy must be 'exact', 'arangosearch', 'bm25', 'vector', or 'lsh', "
                f"got: {self.blocking.strategy}"
            )

        # For exact blocking, fields must be provided so a composite key can be built.
        # Address ER is handled by AddressERService and may ignore the generic blocking config.
        if self.entity_type != 'address' and self.blocking.strategy == 'exact':
            blocking_fields = self._get_blocking_field_names()
            if not blocking_fields:
                errors.append("blocking.fields must be provided when blocking.strategy == 'exact'")
        
        # Validate similarity
        if not 0.0 <= self.similarity.threshold <= 1.0:
            errors.append(
                f"similarity.threshold must be between 0.0 and 1.0, "
                f"got: {self.similarity.threshold}"
            )
        
        if self.similarity.algorithm not in ('jaro_winkler', 'levenshtein', 'jaccard'):
            errors.append(
                f"similarity.algorithm must be 'jaro_winkler', 'levenshtein', or 'jaccard', "
                f"got: {self.similarity.algorithm}"
            )
        
        if self.similarity.field_weights:
            if not all(w >= 0 for w in self.similarity.field_weights.values()):
                errors.append("similarity.field_weights must be non-negative")
        if not isinstance(self.similarity.transformers, dict):
            errors.append("similarity.transformers must be a dictionary")
        else:
            for field, spec in self.similarity.transformers.items():
                if not isinstance(field, str) or not field:
                    errors.append("similarity.transformers keys must be non-empty strings")
                    continue
                if not isinstance(spec, (str, dict, list)):
                    errors.append(
                        f"similarity.transformers['{field}'] must be a string, dict, or list"
                    )
        
        # Validate clustering
        if self.clustering.algorithm not in ('wcc',):
            errors.append(
                f"clustering.algorithm must be 'wcc', got: {self.clustering.algorithm}"
            )
        
        if self.clustering.backend not in ClusteringConfig.VALID_BACKENDS:
            errors.append(
                f"clustering.backend must be one of {ClusteringConfig.VALID_BACKENDS}, "
                f"got: {self.clustering.backend}"
            )
        
        if self.clustering.min_cluster_size < 1:
            errors.append(
                f"clustering.min_cluster_size must be >= 1, "
                f"got: {self.clustering.min_cluster_size}"
            )
        
        # Validate embedding configuration if present
        if self.embedding:
            embedding_errors = self.embedding.validate()
            errors.extend([f"embedding.{e}" for e in embedding_errors])
        if self.active_learning:
            active_learning_errors = self.active_learning.validate()
            errors.extend([f"active_learning.{e}" for e in active_learning_errors])
        if self.canonical_etl:
            etl_errors = self.canonical_etl.validate()
            errors.extend([f"etl.canonical.{e}" for e in etl_errors])
        
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            'entity_resolution': {
                'entity_type': self.entity_type,
                'collection_name': self.collection_name,
                'edge_collection': self.edge_collection,
                'cluster_collection': self.cluster_collection,
                'blocking': self.blocking.to_dict(),
                'similarity': self.similarity.to_dict(),
                'clustering': self.clustering.to_dict()
            }
        }
        
        if self.embedding:
            result['entity_resolution']['embedding'] = self.embedding.to_dict()
        if self.active_learning:
            result['entity_resolution']['active_learning'] = self.active_learning.to_dict()
        if self.canonical_etl:
            result['entity_resolution'].setdefault('etl', {})['canonical'] = self.canonical_etl.to_dict()
        
        return result
    
    def to_yaml(self, output_path: Optional[Union[str, Path]] = None) -> str:
        """
        Convert to YAML string or write to file.
        
        Args:
            output_path: Optional path to write YAML file
        
        Returns:
            YAML string
        """
        yaml_str = yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)
        
        if output_path:
            output_path = Path(output_path)
            with open(output_path, 'w') as f:
                f.write(yaml_str)
        
        return yaml_str
    
    def __repr__(self) -> str:
        """String representation."""
        return (f"ERPipelineConfig("
                f"entity_type='{self.entity_type}', "
                f"collection='{self.collection_name}')")

