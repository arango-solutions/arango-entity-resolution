"""
Graph traversal blocking strategy for relationship-based entity resolution.

This strategy uses existing graph edges to find candidate pairs. Entities that
share relationships (e.g., same phone number, same address, same executive) are
likely to be duplicates or related entities.

Key features:
- Leverage existing graph structure for blocking
- Find entities sharing common relationships
- Configurable edge types and directions
- Transitive relationship discovery

Use cases:
- Find companies sharing phone numbers
- Discover entities at same address
- Identify businesses with same executives
- Link entities through common relationships
"""

from typing import List, Dict, Any, Optional
from arango.database import StandardDatabase
import time

from .base_strategy import BlockingStrategy
from ..utils.validation import validate_collection_name


class GraphTraversalBlockingStrategy(BlockingStrategy):
    """
    Graph traversal blocking for relationship-based entity resolution.
    
    This strategy finds candidate pairs by traversing existing graph edges.
    Entities that share common connections (phone numbers, addresses, people)
    are likely to be duplicates or highly related.
    
    Use cases:
    - Companies sharing phone numbers (potential duplicates)
    - Businesses at same address (co-location or duplicates)
    - Entities with same CEO/executive (related businesses)
    - Any scenario where shared relationships indicate similarity
    
    Performance: O(e x d^2) where e = number of edges, d = avg entities per node
    
    Example:
        ```python
        # Find companies sharing phone numbers
        strategy = GraphTraversalBlockingStrategy(
            db=db,
            collection="companies",
            edge_collection="hasTelephone",
            intermediate_collection="telephone",
            direction="INBOUND",
            filters={
                "telephone._key": {"not_equal": ["0", "0000000000"]}
            }
        )
        pairs = strategy.generate_candidates()
        
        # Find businesses at same address
        strategy = GraphTraversalBlockingStrategy(
            db=db,
            collection="businesses",
            edge_collection="hasAddress",
            intermediate_collection="addresses",
            direction="INBOUND"
        )
        pairs = strategy.generate_candidates()
        ```
    
    Performance: Much faster than comparing all entity pairs when entities
    share few common relationships (high selectivity)
    """
    
    def __init__(
        self,
        db: StandardDatabase,
        collection: str,
        edge_collection: str,
        intermediate_collection: str,
        direction: str = "INBOUND",
        filters: Optional[Dict[str, Dict[str, Any]]] = None,
        max_entities_per_node: int = 100,
        min_entities_per_node: int = 2
    ):
        """
        Initialize graph traversal blocking strategy.
        
        Args:
            db: ArangoDB database connection
            collection: Source entity collection name (e.g., "companies")
            edge_collection: Edge collection connecting entities to intermediate nodes
                (e.g., "hasTelephone", "hasAddress")
            intermediate_collection: Collection of shared resources
                (e.g., "telephone", "addresses", "executives")
            direction: Traversal direction from intermediate node to entities:
                - "INBOUND": intermediate <- entity (most common)
                - "OUTBOUND": intermediate -> entity
                - "ANY": both directions
            filters: Optional filters for intermediate nodes.
                Example: {"_key": {"not_equal": ["0", "invalid"]}}
            max_entities_per_node: Skip nodes with too many entities (likely noise).
                Default 100. E.g., a shared "unknown" phone number.
            min_entities_per_node: Skip nodes with too few entities (no pairs).
                Default 2 (need at least 2 entities to form a pair).
        
        Raises:
            ValueError: If configuration is invalid
        """
        # Don't pass filters to base class since they apply to intermediate collection
        super().__init__(db, collection, filters={})
        
        # Validate inputs
        if not edge_collection:
            raise ValueError("edge_collection cannot be empty")
        if not intermediate_collection:
            raise ValueError("intermediate_collection cannot be empty")
        if direction not in ["INBOUND", "OUTBOUND", "ANY"]:
            raise ValueError("direction must be 'INBOUND', 'OUTBOUND', or 'ANY'")
        
        # Validate collection names for security
        self.edge_collection = validate_collection_name(edge_collection)
        self.intermediate_collection = validate_collection_name(intermediate_collection)
        self.direction = direction
        self.intermediate_filters = filters or {}
        self.max_entities_per_node = max_entities_per_node
        self.min_entities_per_node = min_entities_per_node
        
        if min_entities_per_node < 2:
            raise ValueError("min_entities_per_node must be at least 2")
        if max_entities_per_node < min_entities_per_node:
            raise ValueError("max_entities_per_node must be >= min_entities_per_node")
    
    def generate_candidates(self) -> List[Dict[str, Any]]:
        """
        Generate candidate pairs using graph traversal.
        
        Process:
        1. For each node in intermediate collection (e.g., phone number)
        2. Find all entities connected to that node (e.g., companies with that phone)
        3. If 2+ entities share the node, they're candidates
        4. Generate all pairs of entities sharing the node
        5. Apply size filters to avoid noise
        
        Returns:
            List of candidate pairs:
            [
                {
                    "doc1_key": "company_123",
                    "doc2_key": "company_456",
                    "shared_node": "phone/5551234567",
                    "shared_node_key": "5551234567",
                    "node_degree": 3,  # 3 entities share this phone
                    "method": "graph_traversal_blocking",
                    "edge_collection": "hasTelephone"
                },
                ...
            ]
        
        Performance: O(e x d^2) where e = edges, d = avg entities per node
        Fast when entities share few common resources (high selectivity)
        """
        start_time = time.time()
        
        # Build the AQL query
        query, bind_vars = self._build_graph_traversal_query()

        # Execute query
        cursor = self.db.aql.execute(query, bind_vars=bind_vars)
        pairs = list(cursor)
        
        # Normalize pairs
        normalized_pairs = self._normalize_pairs(pairs)
        
        # Update statistics
        execution_time = time.time() - start_time
        self._update_statistics(normalized_pairs, execution_time)
        
        # Add additional stats
        self._stats.update({
            'edge_collection': self.edge_collection,
            'intermediate_collection': self.intermediate_collection,
            'direction': self.direction,
            'min_entities_per_node': self.min_entities_per_node,
            'max_entities_per_node': self.max_entities_per_node,
            'unique_shared_nodes': self._count_unique_shared_nodes(normalized_pairs),
            'avg_node_degree': self._calculate_avg_node_degree(normalized_pairs)
        })
        
        return normalized_pairs
    
    def _build_graph_traversal_query(self) -> tuple[str, dict]:
        """
        Build the AQL query for graph traversal blocking.

        Returns:
            Tuple of (AQL query string, bind_vars dict)
        """
        query_parts = [
            f"WITH {self.collection}",
            f"FOR node IN {self.intermediate_collection}"
        ]

        bind_vars: dict = {}
        # Add filters for intermediate nodes
        if self.intermediate_filters:
            conditions, filter_bind_vars = self._build_filter_conditions(self.intermediate_filters)
            bind_vars.update(filter_bind_vars)
            for condition in conditions:
                query_parts.append(f"    FILTER {condition}")

        # Traverse to find connected entities
        query_parts.append(
            f"    LET connected_entities = ("
        )
        query_parts.append(
            f"        FOR entity IN 1..1 {self.direction} node {self.edge_collection}"
        )
        query_parts.append(
            "            RETURN entity._key"
        )
        query_parts.append(
            "    )"
        )

        # Filter by node degree (number of connected entities)
        query_parts.append(f"    FILTER LENGTH(connected_entities) >= {self.min_entities_per_node}")
        query_parts.append(f"    FILTER LENGTH(connected_entities) <= {self.max_entities_per_node}")

        # Generate all pairs within this node
        query_parts.append("    FOR i IN 0..LENGTH(connected_entities)-2")
        query_parts.append("        FOR j IN (i+1)..LENGTH(connected_entities)-1")

        # Return pair with metadata
        return_clause = f"""            RETURN {{
                doc1_key: connected_entities[i],
                doc2_key: connected_entities[j],
                shared_node: node._id,
                shared_node_key: node._key,
                node_degree: LENGTH(connected_entities),
                method: "graph_traversal_blocking",
                edge_collection: "{self.edge_collection}"
            }}"""

        query_parts.append(return_clause)

        return "\n".join(query_parts), bind_vars
    
    def _build_filter_conditions(
        self,
        field_filters: Dict[str, Any],
    ) -> tuple[list[str], dict]:
        """
        Build AQL filter conditions for intermediate nodes (``node.`` prefix).

        Delegates operator logic to the shared base implementation, customizing
        only the field reference prefix.
        """
        return super()._build_filter_conditions(
            field_filters, field_ref_fn=lambda name: f"node.{name}"
        )
    
    def _count_unique_shared_nodes(self, pairs: List[Dict[str, Any]]) -> int:
        """
        Count unique shared nodes from pairs.
        
        Args:
            pairs: List of generated pairs
        
        Returns:
            Number of unique shared nodes
        """
        if not pairs:
            return 0
        
        shared_nodes = set()
        for pair in pairs:
            if 'shared_node' in pair:
                shared_nodes.add(pair['shared_node'])
        
        return len(shared_nodes)
    
    def _calculate_avg_node_degree(self, pairs: List[Dict[str, Any]]) -> Optional[float]:
        """
        Calculate average node degree from pairs.
        
        Node degree = number of entities sharing a node.
        
        Args:
            pairs: List of generated pairs
        
        Returns:
            Average node degree or None if no pairs
        """
        if not pairs:
            return None
        
        # Collect node degrees (unique per shared_node)
        node_degrees = {}
        for pair in pairs:
            if 'shared_node' in pair and 'node_degree' in pair:
                node_degrees[pair['shared_node']] = pair['node_degree']
        
        if not node_degrees:
            return None
        
        return round(sum(node_degrees.values()) / len(node_degrees), 2)
    
    def __repr__(self) -> str:
        """String representation of the strategy."""
        return (
            f"GraphTraversalBlockingStrategy("
            f"collection='{self.collection}', "
            f"edge_collection='{self.edge_collection}', "
            f"intermediate='{self.intermediate_collection}', "
            f"direction='{self.direction}')"
        )

