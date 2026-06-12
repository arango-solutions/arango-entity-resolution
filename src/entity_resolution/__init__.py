"""
Entity Resolution System for ArangoDB

A complete entity resolution system that combines:
- Python orchestration and data processing
- ArangoDB native storage and querying
- Graph-based clustering algorithms
- Unified demo and presentation capabilities

Main components are lazily imported to improve startup time and avoid
unnecessary dependency loading.
"""

import importlib

# ---------------------------------------------------------------------------
# Lazy-import registry: {public_name: (dotted_module_path, attribute_name)}
# ---------------------------------------------------------------------------
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # Core components
    "EntityResolver":              (".core.entity_resolver",              "EntityResolver"),
    "ConfigurableERPipeline":      (".core.configurable_pipeline",       "ConfigurableERPipeline"),
    "MultiStrategyOrchestrator":   (".core.orchestrator",                "MultiStrategyOrchestrator"),
    "AddressERPipeline":           (".core.address_pipeline",            "AddressERPipeline"),

    # Core services
    "BlockingService":             (".services.blocking_service",        "BlockingService"),
    "SimilarityService":           (".services.similarity_service",      "SimilarityService"),
    "ClusteringService":           (".services.clustering_service",      "ClusteringService"),
    "GoldenRecordPersistenceService": (".services.golden_record_persistence_service",
                                       "GoldenRecordPersistenceService"),
    "BaseEntityResolutionService": (".services.base_service",            "BaseEntityResolutionService"),
    "DataManager":                 (".data.data_manager",                "DataManager"),

    # Blocking strategies
    "BlockingStrategy":            (".strategies",                       "BlockingStrategy"),
    "CollectBlockingStrategy":     (".strategies",                       "CollectBlockingStrategy"),
    "BM25BlockingStrategy":        (".strategies",                       "BM25BlockingStrategy"),
    "HybridBlockingStrategy":      (".strategies",                       "HybridBlockingStrategy"),
    "GeographicBlockingStrategy":  (".strategies",                       "GeographicBlockingStrategy"),
    "GraphTraversalBlockingStrategy": (".strategies",                    "GraphTraversalBlockingStrategy"),
    "VectorBlockingStrategy":      (".strategies",                       "VectorBlockingStrategy"),
    "LSHBlockingStrategy":         (".strategies",                       "LSHBlockingStrategy"),
    "ShardParallelBlockingStrategy": (".strategies.shard_parallel_blocking",
                                      "ShardParallelBlockingStrategy"),

    # Enhanced services
    "BatchSimilarityService":      (".services.batch_similarity_service",       "BatchSimilarityService"),
    "SimilarityEdgeService":       (".services.similarity_edge_service",        "SimilarityEdgeService"),
    "WCCClusteringService":        (".services.wcc_clustering_service",         "WCCClusteringService"),
    "AddressERService":            (".services.address_er_service",             "AddressERService"),
    "CrossCollectionMatchingService": (".services.cross_collection_matching_service",
                                       "CrossCollectionMatchingService"),
    "EmbeddingService":            (".services.embedding_service",              "EmbeddingService"),
    "Node2VecEmbeddingService":    (".services.node2vec_embedding_service",     "Node2VecEmbeddingService"),
    "Node2VecParams":              (".services.node2vec_embedding_service",     "Node2VecParams"),

    # ONNX Runtime backend
    "OnnxRuntimeEmbeddingBackend": (".services.onnx_embedding_backend",  "OnnxRuntimeEmbeddingBackend"),

    # Similarity components
    "WeightedFieldSimilarity":     (".similarity.weighted_field_similarity", "WeightedFieldSimilarity"),
    "GeospatialValidator":         (".similarity.geospatial_validator",      "GeospatialValidator"),
    "TemporalValidator":           (".similarity.geospatial_validator",      "TemporalValidator"),

    # LLM / reasoning
    "LLMMatchVerifier":            (".reasoning.llm_verifier",           "LLMMatchVerifier"),
    "DocumentEntityExtractor":     (".reasoning.graph_rag",              "DocumentEntityExtractor"),
    "GraphRAGLinker":              (".reasoning.graph_rag",              "GraphRAGLinker"),

    # ETL components
    "CanonicalResolver":           (".etl.canonical_resolver",           "CanonicalResolver"),
    "AddressNormalizer":           (".etl.normalizers",                  "AddressNormalizer"),
    "TokenNormalizer":             (".etl.normalizers",                  "TokenNormalizer"),
    "PostalNormalizer":            (".etl.normalizers",                  "PostalNormalizer"),
    "arangoimport_jsonl":          (".etl.arangoimport",                 "arangoimport_jsonl"),

    # Pipeline utilities
    "clean_er_results":            (".utils.pipeline_utils",             "clean_er_results"),
    "count_inferred_edges":        (".utils.pipeline_utils",             "count_inferred_edges"),
    "validate_edge_quality":       (".utils.pipeline_utils",             "validate_edge_quality"),
    "get_pipeline_statistics":     (".utils.pipeline_utils",             "get_pipeline_statistics"),

    # Configuration
    "Config":                      (".utils.config",                     "Config"),
    "ERPipelineConfig":            (".config",                           "ERPipelineConfig"),
    "BlockingConfig":              (".config",                           "BlockingConfig"),
    "SimilarityConfig":            (".config",                           "SimilarityConfig"),
    "ClusteringConfig":            (".config",                           "ClusteringConfig"),
    "GAEClusteringConfig":         (".config",                           "GAEClusteringConfig"),
    "LLMProviderConfig":           (".config",                           "LLMProviderConfig"),

    # Database utilities
    "DatabaseManager":             (".utils.database",                   "DatabaseManager"),
    "get_database_manager":        (".utils.database",                   "get_database_manager"),
    "get_database":                (".utils.database",                   "get_database"),

    # Constants
    "DEFAULT_DATABASE_CONFIG":     (".utils.constants",                  "DEFAULT_DATABASE_CONFIG"),
    "SIMILARITY_THRESHOLDS":       (".utils.constants",                  "SIMILARITY_THRESHOLDS"),
    "ALGORITHM_WEIGHTS":           (".utils.constants",                  "ALGORITHM_WEIGHTS"),

    # Demo capabilities
    "get_demo_manager":            (".demo",                             "get_demo_manager"),
    "run_presentation_demo":       (".demo",                             "run_presentation_demo"),
    "run_automated_demo":          (".demo",                             "run_automated_demo"),
}


def __getattr__(name: str):
    if name == "__version__":
        from .utils.constants import get_version_string
        return get_version_string()

    if name == "__author__":
        return "Entity Resolution Team"

    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        module = importlib.import_module(module_path, __package__)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Core services
    'EntityResolver',
    'ConfigurableERPipeline',
    'MultiStrategyOrchestrator',
    'BlockingService',
    'SimilarityService',
    'ClusteringService',
    'GoldenRecordPersistenceService',
    'BaseEntityResolutionService',
    'DataManager',

    # Blocking strategies
    'BlockingStrategy',
    'CollectBlockingStrategy',
    'BM25BlockingStrategy',
    'HybridBlockingStrategy',
    'GeographicBlockingStrategy',
    'GraphTraversalBlockingStrategy',
    'VectorBlockingStrategy',
    'LSHBlockingStrategy',
    'ShardParallelBlockingStrategy',

    # Enhanced services
    'BatchSimilarityService',
    'SimilarityEdgeService',
    'WCCClusteringService',
    'AddressERService',
    'AddressERPipeline',
    'CrossCollectionMatchingService',
    'EmbeddingService',
    'OnnxRuntimeEmbeddingBackend',
    'Node2VecEmbeddingService',
    'Node2VecParams',

    # Similarity components
    'WeightedFieldSimilarity',
    'GeospatialValidator',
    'TemporalValidator',

    # LLM / reasoning
    'LLMMatchVerifier',
    'DocumentEntityExtractor',
    'GraphRAGLinker',

    # ETL components
    'CanonicalResolver',
    'AddressNormalizer',
    'TokenNormalizer',
    'PostalNormalizer',
    'arangoimport_jsonl',

    # Pipeline utilities
    'clean_er_results',
    'count_inferred_edges',
    'validate_edge_quality',
    'get_pipeline_statistics',

    # Configuration
    'Config',
    'ERPipelineConfig',
    'BlockingConfig',
    'SimilarityConfig',
    'ClusteringConfig',
    'GAEClusteringConfig',
    'LLMProviderConfig',

    # Database utilities
    'DatabaseManager',
    'get_database_manager',
    'get_database',

    # Constants
    'DEFAULT_DATABASE_CONFIG',
    'SIMILARITY_THRESHOLDS',
    'ALGORITHM_WEIGHTS',

    # Demo capabilities
    'get_demo_manager',
    'run_presentation_demo',
    'run_automated_demo',
]
