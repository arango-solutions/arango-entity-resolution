"""Bulk-fetch + Python DFS clustering backend.

Extracted from the original ``WCCClusteringService._find_connected_components_bulk``
implementation.  Fetches all edges in a single AQL query then runs an iterative
DFS in Python to discover connected components.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ...utils.graph_utils import extract_key_from_vertex_id

logger = logging.getLogger(__name__)


class PythonDFSBackend:
    """In-process WCC via bulk edge fetch and iterative DFS.

    Performance (16K edges, 24K vertices): ~3-8 seconds (1 query).
    Safe for graphs up to ~10M edges on typical hardware.
    """

    def __init__(
        self,
        db,
        edge_collection_name: str,
        vertex_collection: Optional[str] = None,
    ):
        self.db = db
        self.edge_collection_name = edge_collection_name
        self.vertex_collection = vertex_collection

    def cluster(self) -> List[List[str]]:
        # Exclude suppressed edges (human/LLM "not a match" verdicts).
        edges_query = """
        FOR e IN @@collection
        FILTER e.suppressed != true
        RETURN {from: e._from, to: e._to}
        """

        logger.info("Fetching all edges from %s in bulk...", self.edge_collection_name)
        cursor = self.db.aql.execute(
            edges_query,
            bind_vars={"@collection": self.edge_collection_name},
        )
        edges = list(cursor)

        if not edges:
            logger.warning("No edges found in collection")
            return []

        logger.info("  [OK] Fetched %s edges in one query", f"{len(edges):,}")

        graph: dict[str, set[str]] = {}
        all_vertices: set[str] = set()

        for edge in edges:
            from_id = edge["from"]
            to_id = edge["to"]
            all_vertices.add(from_id)
            all_vertices.add(to_id)
            graph.setdefault(from_id, set()).add(to_id)
            graph.setdefault(to_id, set()).add(from_id)

        logger.info("  [OK] Built graph with %s vertices", f"{len(all_vertices):,}")

        visited: set[str] = set()
        clusters: List[List[str]] = []

        for start_vertex in all_vertices:
            if start_vertex in visited:
                continue

            component: list[str] = []
            stack = [start_vertex]

            while stack:
                vertex = stack.pop()
                if vertex in visited:
                    continue
                visited.add(vertex)
                component.append(vertex)
                for neighbor in graph.get(vertex, ()):
                    if neighbor not in visited:
                        stack.append(neighbor)

            component_keys = [
                k for v in component if (k := extract_key_from_vertex_id(v))
            ]
            if component_keys:
                clusters.append(sorted(component_keys))

        logger.info("  [OK] Found %s connected components", f"{len(clusters):,}")
        return clusters

    def backend_name(self) -> str:
        return "python_dfs"
