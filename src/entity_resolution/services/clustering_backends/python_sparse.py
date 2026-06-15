"""Sparse-matrix WCC backend using scipy.sparse.csgraph.

Requires ``scipy`` (optional dependency).  Faster than Union-Find for
very dense large graphs because ``connected_components`` on a CSR matrix
runs in highly optimised C code.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Optional

from ...utils.graph_utils import extract_key_from_vertex_id

logger = logging.getLogger(__name__)


class PythonSparseBackend:
    """In-process WCC via scipy sparse adjacency matrix.

    Algorithm:
    1. Fetch all edges in a single AQL query.
    2. Map vertex IDs to contiguous integer indices.
    3. Build a scipy CSR sparse adjacency matrix.
    4. Call ``scipy.sparse.csgraph.connected_components()``.
    5. Map component labels back to document keys.
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
        try:
            from scipy.sparse import csr_matrix
            from scipy.sparse.csgraph import connected_components
        except ImportError:
            raise ImportError(
                "python_sparse backend requires scipy. "
                "Install it with: pip install scipy"
            )

        logger.info("Fetching edges from %s for sparse WCC...", self.edge_collection_name)
        # Exclude suppressed edges (human/LLM "not a match" verdicts).
        cursor = self.db.aql.execute(
            "FOR e IN @@collection FILTER e.suppressed != true RETURN [e._from, e._to]",
            bind_vars={"@collection": self.edge_collection_name},
        )
        edges = list(cursor)

        if not edges:
            logger.warning("No edges found in collection")
            return []

        logger.info("  [OK] Fetched %s edges", f"{len(edges):,}")

        vertex_to_idx: Dict[str, int] = {}
        idx_to_vertex: Dict[int, str] = {}
        counter = 0
        rows: list[int] = []
        cols: list[int] = []

        for from_id, to_id in edges:
            for vid in (from_id, to_id):
                if vid not in vertex_to_idx:
                    vertex_to_idx[vid] = counter
                    idx_to_vertex[counter] = vid
                    counter += 1
            fi, ti = vertex_to_idx[from_id], vertex_to_idx[to_id]
            rows.extend([fi, ti])
            cols.extend([ti, fi])

        n = counter
        data = [1] * len(rows)
        matrix = csr_matrix((data, (rows, cols)), shape=(n, n))
        n_components, labels = connected_components(matrix, directed=False)

        groups: Dict[int, List[str]] = defaultdict(list)
        for idx, label in enumerate(labels):
            key = extract_key_from_vertex_id(idx_to_vertex[idx])
            if key:
                groups[label].append(key)

        clusters = [sorted(members) for members in groups.values()]
        logger.info("  [OK] Found %s connected components", f"{len(clusters):,}")
        return clusters

    def backend_name(self) -> str:
        return "python_sparse"
