"""AQL server-side graph traversal clustering backend.

Extracted from ``WCCClusteringService._find_connected_components_aql``.
Runs one AQL traversal per unvisited vertex.  Slower than local backends
for typical ER workloads but useful for very large graphs that exceed
available memory.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ...utils.graph_utils import extract_key_from_vertex_id
from ...utils.validation import validate_collection_name

logger = logging.getLogger(__name__)


class AQLGraphBackend:
    """Server-side WCC via per-vertex AQL graph traversal.

    Each unvisited vertex triggers one ``FOR v IN 0..999999 ANY`` traversal.
    This avoids pulling the full edge set into memory but is significantly
    slower due to per-vertex round-trips (~300s vs ~5s for 16K edges).
    """

    def __init__(
        self,
        db,
        edge_collection_name: str,
        vertex_collection: Optional[str] = None,
        graph_name: Optional[str] = None,
    ):
        self.db = db
        self.edge_collection_name = edge_collection_name
        self.vertex_collection = vertex_collection
        self.graph_name = graph_name

    def _get_vertex_collections(self) -> List[str]:
        if self.vertex_collection:
            return [self.vertex_collection]
        try:
            edge_coll = self.db.collection(self.edge_collection_name)
            sample_edges = list(edge_coll.all(limit=10))
            if not sample_edges:
                return []
            collections: set[str] = set()
            for edge in sample_edges:
                for field in ("_from", "_to"):
                    vid = edge.get(field, "")
                    if "/" in vid:
                        collections.add(vid.split("/")[0])
            return [validate_collection_name(c) for c in sorted(collections)]
        except Exception as exc:
            logger.error("Failed to detect vertex collections: %s", exc, exc_info=True)
            return []

    def cluster(self) -> List[List[str]]:
        vertex_collections = self._get_vertex_collections()
        with_clause = f"WITH {', '.join(vertex_collections)}" if vertex_collections else ""

        # Suppressed edges (human/LLM "not a match" verdicts) are excluded so
        # they neither seed vertices nor connect components.
        vertices_query = """
        LET from_vertices = (
            FOR e IN @@edge_collection FILTER e.suppressed != true RETURN DISTINCT e._from
        )
        LET to_vertices = (
            FOR e IN @@edge_collection FILTER e.suppressed != true RETURN DISTINCT e._to
        )
        RETURN UNION_DISTINCT(from_vertices, to_vertices)
        """
        edge_bind = {"@edge_collection": self.edge_collection_name}

        cursor = self.db.aql.execute(vertices_query, bind_vars=edge_bind)
        cursor_list = list(cursor)
        all_vertices = cursor_list[0] if cursor_list else []

        if not all_vertices:
            return []

        visited: set[str] = set()
        clusters: List[List[str]] = []

        for start_vertex in all_vertices:
            if start_vertex in visited:
                continue

            # A vertex belongs to the component only if reachable by a path
            # whose every edge is non-suppressed; suppressed edges must not
            # bridge two otherwise-separate components.
            component_query = f"""
            {with_clause}
            FOR v, e, p IN 0..999999 ANY @start_vertex @@edge_collection
                OPTIONS {{uniqueVertices: "global", bfs: true}}
                FILTER p.edges[*].suppressed ALL != true
                RETURN DISTINCT v._id
            """

            try:
                cursor = self.db.aql.execute(
                    component_query,
                    bind_vars={
                        "start_vertex": start_vertex,
                        "@edge_collection": self.edge_collection_name,
                    },
                )
                component_vertices = list(cursor)

                if component_vertices:
                    component_keys = [
                        k
                        for v in component_vertices
                        if (k := extract_key_from_vertex_id(v))
                    ]
                    if component_keys:
                        clusters.append(sorted(component_keys))
                        visited.update(component_vertices)

            except Exception as exc:
                logger.error(
                    "Failed to traverse component for %s: %s",
                    start_vertex,
                    exc,
                    exc_info=True,
                )
                continue

        return clusters

    def backend_name(self) -> str:
        return "aql_graph"
