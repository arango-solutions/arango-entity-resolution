"""Union-Find (disjoint-set) clustering backend.

Near-linear amortized complexity via path compression and union by rank.
Fetches all edges in a single AQL query then runs Union-Find in Python.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Optional

from ...utils.graph_utils import extract_key_from_vertex_id

logger = logging.getLogger(__name__)


class PythonUnionFindBackend:
    """In-process WCC via Union-Find with path compression and union by rank.

    Faster than DFS for larger graphs because Union-Find has near-linear
    amortized complexity and the fetch is a single query.
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

    def _fetch_edges(self) -> List[list]:
        # Exclude human/LLM-suppressed edges so "not a match" verdicts split
        # clusters; confirmed edges are present in the collection and cluster
        # normally.
        cursor = self.db.aql.execute(
            "FOR e IN @@collection FILTER e.suppressed != true RETURN [e._from, e._to]",
            bind_vars={"@collection": self.edge_collection_name},
        )
        return list(cursor)

    @staticmethod
    def _build_components(edges: List[list]) -> Dict[str, str]:
        """Run Union-Find and return vertex_id -> root_vertex_id mapping."""
        parent: Dict[str, str] = {}
        rank: Dict[str, int] = {}

        def find(x: str) -> str:
            while parent.setdefault(x, x) != x:
                parent[x] = parent[parent[x]]  # path halving
                x = parent[x]
            return x

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
        logger.info("Fetching edges from %s for Union-Find...", self.edge_collection_name)
        edges = self._fetch_edges()

        if not edges:
            logger.warning("No edges found in collection")
            return []

        logger.info("  [OK] Fetched %s edges", f"{len(edges):,}")

        components = self._build_components(edges)

        groups: Dict[str, List[str]] = defaultdict(list)
        for vertex_id, root_id in components.items():
            key = extract_key_from_vertex_id(vertex_id)
            if key:
                groups[root_id].append(key)

        clusters = [sorted(members) for members in groups.values()]
        logger.info("  [OK] Found %s connected components", f"{len(clusters):,}")
        return clusters

    def backend_name(self) -> str:
        return "python_union_find"
