"""
Weakly Connected Components (WCC) clustering service.

This service finds connected components in the similarity graph using
AQL graph traversal. Provides production-grade clustering with validation
and comprehensive statistics.
"""

from typing import List, Dict, Any, Optional
from arango.database import StandardDatabase
from arango.collection import EdgeCollection, StandardCollection
import time
from datetime import datetime
import logging

from ..utils.graph_utils import format_vertex_id, extract_key_from_vertex_id
from ..utils.validation import validate_collection_name


class WCCClusteringService:
    """
    Weakly Connected Components clustering using AQL graph traversal.
    
    Finds connected components in the similarity graph using server-side
    AQL graph traversal. This is efficient, works on all modern ArangoDB
    installations (3.11+), and handles graphs with millions of edges.
    
    Key features:
    - Server-side processing (no need to fetch edges to Python)
    - AQL graph traversal for efficiency
    - Configurable minimum cluster size
    - Cluster storage with metadata
    - Validation and statistics
    - Works with any edge collection
    
    Future enhancement: GAE (Graph Analytics Engine) support for
    extremely large graphs (millions of edges).
    
    Example:
        ```python
        service = WCCClusteringService(
            db=db,
            edge_collection="similarTo",
            cluster_collection="entity_clusters",
            vertex_collection="companies"
        )
        
        clusters = service.cluster(store_results=True)
        
        # Get statistics
        stats = service.get_statistics()
        print(f"Found {stats['total_clusters']} clusters")
        ```
    """
    
    def __init__(
        self,
        db: StandardDatabase,
        edge_collection: str = "similarTo",
        cluster_collection: str = "entity_clusters",
        vertex_collection: Optional[str] = None,
        min_cluster_size: int = 2,
        graph_name: Optional[str] = None,
        backend: str = "auto",
        use_bulk_fetch: Optional[bool] = None,
        auto_select_threshold_edges: int = 2_000_000,
        sparse_backend_enabled: bool = True,
        gae_config=None,
    ):
        """
        Initialize WCC clustering service.
        
        Args:
            db: ArangoDB database connection
            edge_collection: Edge collection containing similarity edges
            cluster_collection: Collection to store cluster results
            vertex_collection: Vertex collection name (for _from/_to parsing).
                If None, will auto-detect from edges.
            min_cluster_size: Minimum entities per cluster to store. Default 2.
            graph_name: Named graph to use (optional). If None, will use
                anonymous graph traversal.
            backend: Clustering backend to use.  Default ``auto`` (since 3.5.0).
            use_bulk_fetch: Deprecated -- use ``backend`` instead.
                ``True`` maps to ``python_dfs``, ``False`` to ``aql_graph``.
            auto_select_threshold_edges: Edge count above which ``auto`` prefers
                ``python_sparse`` or GAE. Default 2M.
            sparse_backend_enabled: Whether ``auto`` may select ``python_sparse``.
            gae_config: Optional GAEClusteringConfig for GAE backend.
        """
        import warnings

        self.db = db
        self.edge_collection_name = validate_collection_name(edge_collection)
        self.cluster_collection_name = validate_collection_name(cluster_collection)
        self.vertex_collection = validate_collection_name(vertex_collection) if vertex_collection else None
        self.min_cluster_size = min_cluster_size
        self.graph_name = graph_name
        self.auto_select_threshold_edges = auto_select_threshold_edges
        self.sparse_backend_enabled = sparse_backend_enabled
        self.gae_config = gae_config

        if use_bulk_fetch is not None:
            warnings.warn(
                "WCCClusteringService.use_bulk_fetch is deprecated and will be "
                "removed in a future release. Use backend= instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            self.backend = "python_dfs" if use_bulk_fetch else "aql_graph"
        else:
            self.backend = backend

        # Keep use_bulk_fetch in sync for any code that still reads it
        self.use_bulk_fetch = self.backend != "aql_graph"
        
        # Initialize logger
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Get collections
        self.edge_collection: EdgeCollection = db.collection(self.edge_collection_name)
        
        # Create cluster collection if it doesn't exist
        if not db.has_collection(self.cluster_collection_name):
            self.cluster_collection: StandardCollection = db.create_collection(self.cluster_collection_name)
        else:
            self.cluster_collection = db.collection(self.cluster_collection_name)
        
        # Statistics tracking
        self._stats = {
            'total_clusters': 0,
            'total_entities_clustered': 0,
            'avg_cluster_size': 0.0,
            'max_cluster_size': 0,
            'min_cluster_size': 0,
            'cluster_size_distribution': {},
            'backend_used': self.backend,
            'execution_time_seconds': 0.0,
            'timestamp': None
        }
    
    def cluster(
        self,
        store_results: bool = True,
        truncate_existing: bool = True
    ) -> List[List[str]]:
        """
        Run WCC clustering on similarity edges using AQL graph traversal.
        
        Args:
            store_results: Store clusters in cluster_collection. Default True.
            truncate_existing: Clear existing clusters before storing. Default True.
        
        Returns:
            List of clusters, each cluster is a list of document keys:
            [
                ["doc1", "doc2", "doc3"],  # Cluster 1
                ["doc4", "doc5"],          # Cluster 2
                ...
            ]
        
        Performance: Server-side processing, efficient for graphs up to
        millions of edges.
        """
        start_time = time.time()
        
        backend_impl = self._get_backend()
        self.logger.info("Using clustering backend: %s", backend_impl.backend_name())
        clusters = backend_impl.cluster()
        
        # Filter by minimum cluster size
        filtered_clusters = [
            cluster for cluster in clusters
            if len(cluster) >= self.min_cluster_size
        ]
        
        # Store results if requested
        if store_results:
            if truncate_existing:
                self.cluster_collection.truncate()
            self._store_clusters(filtered_clusters)
        
        execution_time = time.time() - start_time
        self._stats['backend_used'] = backend_impl.backend_name()
        if hasattr(backend_impl, 'gae_job_id') and backend_impl.gae_job_id:
            self._stats['gae_job_id'] = backend_impl.gae_job_id
            self._stats['gae_runtime_seconds'] = backend_impl.gae_runtime_seconds
        self._update_statistics(filtered_clusters, execution_time)
        
        return filtered_clusters
    
    def get_cluster_by_member(self, member_key: str) -> Optional[Dict[str, Any]]:
        """
        Find cluster containing a specific member.
        
        Args:
            member_key: Document key to search for
        
        Returns:
            Cluster record or None if not found
        
        Example:
            ```python
            cluster = service.get_cluster_by_member("company_123")
            if cluster:
                print(f"Company 123 is in cluster {cluster['cluster_id']}")
                print(f"Cluster has {cluster['size']} members")
            ```
        """
        # Format member key properly
        member_id = self._format_vertex_id(member_key)
        
        query = """
        FOR cluster IN @@cluster_collection
            FILTER @member_id IN cluster.members
            RETURN cluster
        """
        
        cursor = self.db.aql.execute(query, bind_vars={
            '@cluster_collection': self.cluster_collection_name,
            'member_id': member_id,
        })
        results = list(cursor)
        
        return results[0] if results else None
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get clustering statistics.
        
        Returns:
            Statistics dictionary:
            {
                "total_clusters": 234,
                "total_entities_clustered": 1523,
                "avg_cluster_size": 6.5,
                "max_cluster_size": 45,
                "min_cluster_size": 2,
                "cluster_size_distribution": {
                    "2": 120,
                    "3": 56,
                    "4-10": 45,
                    "11-50": 13
                },
                "algorithm_used": "aql_graph_traversal",
                "execution_time_seconds": 3.4,
                "timestamp": "2025-11-12T14:30:22"
            }
        """
        return self._stats.copy()
    
    def validate_clusters(self) -> Dict[str, Any]:
        """
        Validate cluster quality and consistency.
        
        Checks:
        - No overlapping clusters (each entity in at most one cluster)
        - All edges respected (connected entities in same cluster)
        - Minimum size requirement met
        
        Returns:
            Validation results:
            {
                "valid": True,
                "issues": [],
                "checks_performed": [
                    "no_overlapping_clusters",
                    "all_edges_respected",
                    "min_size_requirement"
                ],
                "entities_checked": 1523,
                "edges_checked": 845
            }
        """
        issues = []
        checks_performed = []
        
        # Check 1: No overlapping clusters
        checks_performed.append("no_overlapping_clusters")
        entity_to_cluster = {}
        
        for cluster_doc in self.cluster_collection:
            cluster_id = cluster_doc.get('cluster_id')
            members = cluster_doc.get('member_keys', [])
            
            for member in members:
                if member in entity_to_cluster:
                    issues.append({
                        'type': 'overlapping_clusters',
                        'entity': member,
                        'clusters': [entity_to_cluster[member], cluster_id]
                    })
                else:
                    entity_to_cluster[member] = cluster_id
        
        # Check 2: Minimum size requirement
        checks_performed.append("min_size_requirement")
        for cluster_doc in self.cluster_collection:
            size = cluster_doc.get('size', 0)
            if size < self.min_cluster_size:
                issues.append({
                    'type': 'below_min_size',
                    'cluster_id': cluster_doc.get('cluster_id'),
                    'size': size,
                    'min_required': self.min_cluster_size
                })
        
        # Check 3: Sample edge validation (check some edges are respected)
        checks_performed.append("sample_edges_validated")
        edges_sample = list(self.edge_collection.all(limit=100))
        edges_checked = 0
        
        for edge in edges_sample:
            from_key = self._extract_key_from_vertex_id(edge.get('_from', ''))
            to_key = self._extract_key_from_vertex_id(edge.get('_to', ''))
            
            from_cluster = entity_to_cluster.get(from_key)
            to_cluster = entity_to_cluster.get(to_key)
            
            if from_cluster != to_cluster:
                issues.append({
                    'type': 'edge_not_respected',
                    'from': from_key,
                    'to': to_key,
                    'from_cluster': from_cluster,
                    'to_cluster': to_cluster
                })
            
            edges_checked += 1
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'checks_performed': checks_performed,
            'entities_checked': len(entity_to_cluster),
            'edges_checked': edges_checked
        }
    
    def _get_backend(self):
        """Instantiate the selected clustering backend."""
        from .clustering_backends.python_dfs import PythonDFSBackend
        from .clustering_backends.python_union_find import PythonUnionFindBackend
        from .clustering_backends.aql_graph import AQLGraphBackend

        if self.backend == "auto":
            return self._auto_select_backend()
        if self.backend == "python_union_find":
            return PythonUnionFindBackend(
                self.db, self.edge_collection_name, self.vertex_collection
            )
        if self.backend in ("python_dfs", "bulk_python_dfs"):
            return PythonDFSBackend(
                self.db, self.edge_collection_name, self.vertex_collection
            )
        if self.backend == "python_sparse":
            from .clustering_backends.python_sparse import PythonSparseBackend
            return PythonSparseBackend(
                self.db, self.edge_collection_name, self.vertex_collection
            )
        if self.backend == "gae_wcc":
            from .clustering_backends.gae_wcc import GAEWCCBackend
            return GAEWCCBackend(
                self.db, self.edge_collection_name, self.vertex_collection,
                self.gae_config,
            )
        if self.backend == "aql_graph":
            return AQLGraphBackend(
                self.db,
                self.edge_collection_name,
                self.vertex_collection,
                self.graph_name,
            )
        raise ValueError(f"Unknown clustering backend: {self.backend!r}")

    def _auto_select_backend(self):
        """Pick the best backend based on edge count, GAE, and availability."""
        from .clustering_backends.python_union_find import PythonUnionFindBackend

        edge_count = self.edge_collection.count()
        self.logger.info(
            "Auto-selecting backend (edge_count=%s, threshold=%s, sparse_enabled=%s)",
            f"{edge_count:,}",
            f"{self.auto_select_threshold_edges:,}",
            self.sparse_backend_enabled,
        )

        # Try GAE first when enabled and above threshold
        if self.gae_config and self.gae_config.enabled and edge_count > self.auto_select_threshold_edges:
            try:
                from .clustering_backends.gae_wcc import GAEWCCBackend
                gae = GAEWCCBackend(
                    self.db, self.edge_collection_name,
                    self.vertex_collection, self.gae_config,
                )
                if gae.is_available():
                    self.logger.info("Auto-selected gae_wcc (GAE available, edge_count > threshold)")
                    return gae
                self.logger.info("GAE enabled but not available; trying local backends")
            except Exception as exc:
                self.logger.warning("GAE probe failed: %s; trying local backends", exc)

        # Try python_sparse for large graphs
        if self.sparse_backend_enabled and edge_count > self.auto_select_threshold_edges:
            try:
                from .clustering_backends.python_sparse import PythonSparseBackend
                self.logger.info("Auto-selected python_sparse (edge_count > threshold)")
                return PythonSparseBackend(
                    self.db, self.edge_collection_name, self.vertex_collection
                )
            except ImportError:
                self.logger.info("scipy not available; falling back to python_union_find")

        self.logger.info("Auto-selected python_union_find")
        return PythonUnionFindBackend(
            self.db, self.edge_collection_name, self.vertex_collection
        )

    def _store_clusters(self, clusters: List[List[str]]):
        """
        Store clusters in the cluster collection.
        
        Args:
            clusters: List of clusters to store
        """
        cluster_docs = []
        quality_by_members = self._compute_cluster_quality(clusters)
        
        for i, cluster_members in enumerate(clusters):
            cluster_doc = {
                '_key': f'cluster_{i:06d}',
                'cluster_id': i,
                'size': len(cluster_members),
                'members': [self._format_vertex_id(k) for k in cluster_members],
                'member_keys': cluster_members,
                'timestamp': datetime.now().isoformat(),
                'method': 'aql_graph_traversal'
            }
            cluster_doc.update(quality_by_members.get(tuple(sorted(cluster_members)), {}))
            cluster_docs.append(cluster_doc)
        
        if cluster_docs:
            # Insert in batches
            batch_size = 1000
            for i in range(0, len(cluster_docs), batch_size):
                batch = cluster_docs[i:i + batch_size]
                self.cluster_collection.insert_many(batch)

    def _compute_cluster_quality(self, clusters: List[List[str]]) -> Dict[tuple[str, ...], Dict[str, Any]]:
        """Compute quality metrics for stored clusters from existing edge similarities."""
        if not clusters:
            return {}

        membership: Dict[str, tuple[str, ...]] = {}
        for cluster_members in clusters:
            cluster_key = tuple(sorted(cluster_members))
            for member in cluster_members:
                membership[member] = cluster_key

        edges_query = """
        FOR e IN @@edge_collection
            RETURN {
                from: e._from,
                to: e._to,
                similarity: e.similarity
            }
        """

        try:
            cursor = self.db.aql.execute(
                edges_query,
                bind_vars={"@edge_collection": self.edge_collection_name},
            )
            edges = list(cursor)
        except Exception as exc:
            self.logger.warning("Failed to compute cluster quality metadata: %s", exc)
            return {}

        aggregates: Dict[tuple[str, ...], Dict[str, Any]] = {}
        for cluster_members in clusters:
            cluster_key = tuple(sorted(cluster_members))
            aggregates[cluster_key] = {
                'edge_count': 0,
                'similarity_sum': 0.0,
                'min_similarity': None,
                'max_similarity': None,
            }

        seen_pairs: set[tuple[tuple[str, ...], str, str]] = set()
        for edge in edges:
            from_key = self._extract_key_from_vertex_id(edge.get('from', ''))
            to_key = self._extract_key_from_vertex_id(edge.get('to', ''))
            if not from_key or not to_key:
                continue

            cluster_key = membership.get(from_key)
            if not cluster_key or cluster_key != membership.get(to_key):
                continue

            pair_key = tuple(sorted((from_key, to_key)))
            dedupe_key = (cluster_key, pair_key[0], pair_key[1])
            if dedupe_key in seen_pairs:
                continue
            seen_pairs.add(dedupe_key)

            similarity = edge.get('similarity')
            if similarity is None:
                similarity = 0.0
            similarity = float(similarity)

            agg = aggregates[cluster_key]
            agg['edge_count'] += 1
            agg['similarity_sum'] += similarity
            agg['min_similarity'] = similarity if agg['min_similarity'] is None else min(agg['min_similarity'], similarity)
            agg['max_similarity'] = similarity if agg['max_similarity'] is None else max(agg['max_similarity'], similarity)

        quality: Dict[tuple[str, ...], Dict[str, Any]] = {}
        for cluster_members in clusters:
            cluster_key = tuple(sorted(cluster_members))
            agg = aggregates[cluster_key]
            cluster_size = len(cluster_members)
            possible_edges = cluster_size * (cluster_size - 1) / 2 if cluster_size > 1 else 0
            density = round(agg['edge_count'] / possible_edges, 4) if possible_edges else 0.0
            average_similarity = (
                round(agg['similarity_sum'] / agg['edge_count'], 4)
                if agg['edge_count'] > 0 else None
            )
            min_similarity = round(agg['min_similarity'], 4) if agg['min_similarity'] is not None else None
            max_similarity = round(agg['max_similarity'], 4) if agg['max_similarity'] is not None else None
            quality_score = round(self._calculate_quality_score(density, average_similarity), 4)

            quality[cluster_key] = {
                'edge_count': agg['edge_count'],
                'average_similarity': average_similarity,
                'min_similarity': min_similarity,
                'max_similarity': max_similarity,
                'density': density,
                'quality_score': quality_score,
            }

        return quality

    @staticmethod
    def _calculate_quality_score(density: float, average_similarity: Optional[float]) -> float:
        """Simple composite score for downstream trust/review decisions."""
        similarity = average_similarity if average_similarity is not None else 0.0
        return min(1.0, (density * 0.4) + (similarity * 0.6))
    
    def _update_statistics(self, clusters: List[List[str]], execution_time: float):
        """Update internal statistics."""
        if not clusters:
            self._stats.update({
                'total_clusters': 0,
                'total_entities_clustered': 0,
                'execution_time_seconds': round(execution_time, 2),
                'timestamp': datetime.now().isoformat()
            })
            return
        
        sizes = [len(c) for c in clusters]
        total_entities = sum(sizes)
        
        # Calculate size distribution
        distribution = {
            '2': len([s for s in sizes if s == 2]),
            '3': len([s for s in sizes if s == 3]),
            '4-10': len([s for s in sizes if 4 <= s <= 10]),
            '11-50': len([s for s in sizes if 11 <= s <= 50]),
            '51+': len([s for s in sizes if s > 50])
        }
        
        self._stats.update({
            'total_clusters': len(clusters),
            'total_entities_clustered': total_entities,
            'avg_cluster_size': round(total_entities / len(clusters), 2),
            'max_cluster_size': max(sizes),
            'min_cluster_size': min(sizes),
            'cluster_size_distribution': distribution,
            'execution_time_seconds': round(execution_time, 2),
            'timestamp': datetime.now().isoformat()
        })
    
    def _format_vertex_id(self, key: str) -> str:
        """
        Format a document key as a vertex ID.
        
        Note:
            This method now delegates to the shared graph_utils.format_vertex_id()
            for consistency across the codebase.
        """
        return format_vertex_id(key, self.vertex_collection)
    
    def _extract_key_from_vertex_id(self, vertex_id: str) -> Optional[str]:
        """
        Extract document key from vertex ID.
        
        Note:
            This method now delegates to the shared graph_utils.extract_key_from_vertex_id()
            for consistency across the codebase.
        """
        return extract_key_from_vertex_id(vertex_id)
    
    def __repr__(self) -> str:
        """String representation."""
        return (f"WCCClusteringService("
                f"edge_collection='{self.edge_collection_name}', "
                f"min_cluster_size={self.min_cluster_size})")

