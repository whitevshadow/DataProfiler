"""
Graph Builder

Constructs relationship graphs for visualization and analysis.

Graph Formats:
    1. Adjacency list (for graph algorithms)
    2. NetworkX compatible (for visualization)
    3. DOT format (for Graphviz)
    4. JSON graph (for web visualization)

Use Cases:
    - Visualize FK relationships
    - Detect cyclic dependencies
    - Identify relationship clusters
    - Export to graph databases (Neo4j, etc.)
"""

from typing import Dict, List, Set, Tuple, Any
from relationships.relationship_models import Relationship, RelationshipReport


class GraphBuilder:
    """
    Builds relationship graphs from detected FK relationships.
    
    Supports multiple graph formats for different use cases.
    """
    
    def __init__(self):
        """Initialize graph builder."""
        pass
    
    def build_adjacency_list(
        self,
        relationships: List[Relationship],
    ) -> Dict[str, List[str]]:
        """
        Build adjacency list representation of relationships.
        
        Format:
            {
                "orders": ["customers", "products"],
                "customers": [],
                "products": ["categories"]
            }
        
        Args:
            relationships: List of detected relationships
        
        Returns:
            Dict mapping table -> list of referenced tables
        """
        adjacency = {}
        
        for rel in relationships:
            if not rel.accepted:
                continue
            
            fk_table = rel.from_column.table
            pk_table = rel.to_column.table
            
            if fk_table not in adjacency:
                adjacency[fk_table] = []
            
            if pk_table not in adjacency[fk_table]:
                adjacency[fk_table].append(pk_table)
            
            # Ensure pk_table exists in graph
            if pk_table not in adjacency:
                adjacency[pk_table] = []
        
        return adjacency
    
    def build_edge_list(
        self,
        relationships: List[Relationship],
    ) -> List[Tuple[str, str, Dict[str, Any]]]:
        """
        Build edge list representation.
        
        Format:
            [
                ("orders", "customers", {"confidence": 0.98, ...}),
                ("orders", "products", {"confidence": 0.95, ...}),
            ]
        
        Args:
            relationships: List of detected relationships
        
        Returns:
            List of (from_table, to_table, attributes) tuples
        """
        edges = []
        
        for rel in relationships:
            if not rel.accepted:
                continue
            
            edge = (
                rel.from_column.table,
                rel.to_column.table,
                {
                    "from_column": rel.from_column.column,
                    "to_column": rel.to_column.column,
                    "confidence": rel.confidence,
                    "relationship_type": rel.relationship_type.value,
                    "containment_ratio": rel.evidence.containment_ratio,
                },
            )
            edges.append(edge)
        
        return edges
    
    def build_json_graph(
        self,
        relationships: List[Relationship],
    ) -> Dict[str, Any]:
        """
        Build JSON graph format for web visualization.
        
        Format compatible with D3.js, Cytoscape.js, etc.
        
        Args:
            relationships: List of detected relationships
        
        Returns:
            Dict with "nodes" and "edges" keys
        """
        nodes_set = set()
        edges = []
        
        for rel in relationships:
            if not rel.accepted:
                continue
            
            fk_table = rel.from_column.table
            pk_table = rel.to_column.table
            
            nodes_set.add(fk_table)
            nodes_set.add(pk_table)
            
            edge = {
                "source": fk_table,
                "target": pk_table,
                "from_column": rel.from_column.column,
                "to_column": rel.to_column.column,
                "confidence": round(rel.confidence, 4),
                "relationship_type": rel.relationship_type.value,
            }
            edges.append(edge)
        
        nodes = [{"id": node, "label": node} for node in sorted(nodes_set)]
        
        return {
            "nodes": nodes,
            "edges": edges,
        }
    
    def build_dot_format(
        self,
        relationships: List[Relationship],
        graph_name: str = "relationships",
    ) -> str:
        """
        Build DOT format for Graphviz visualization.
        
        Args:
            relationships: List of detected relationships
            graph_name: Name of the graph
        
        Returns:
            DOT format string
        """
        lines = [f"digraph {graph_name} {{"]
        lines.append('  rankdir=LR;')
        lines.append('  node [shape=box, style=rounded];')
        lines.append("")
        
        # Add nodes
        nodes_set = set()
        for rel in relationships:
            if rel.accepted:
                nodes_set.add(rel.from_column.table)
                nodes_set.add(rel.to_column.table)
        
        for node in sorted(nodes_set):
            lines.append(f'  "{node}";')
        
        lines.append("")
        
        # Add edges
        for rel in relationships:
            if not rel.accepted:
                continue
            
            fk_table = rel.from_column.table
            pk_table = rel.to_column.table
            fk_col = rel.from_column.column
            pk_col = rel.to_column.column
            confidence = rel.confidence
            
            label = f"{fk_col} -> {pk_col}\\n{confidence:.2f}"
            lines.append(f'  "{fk_table}" -> "{pk_table}" [label="{label}"];')
        
        lines.append("}")
        
        return "\n".join(lines)
    
    def detect_cycles(
        self,
        adjacency_list: Dict[str, List[str]],
    ) -> List[List[str]]:
        """
        Detect cyclic dependencies in relationship graph.
        
        Args:
            adjacency_list: Adjacency list representation
        
        Returns:
            List of cycles (each cycle is a list of table names)
        """
        cycles = []
        visited = set()
        rec_stack = set()
        
        def dfs(node: str, path: List[str]):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in adjacency_list.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, path[:])
                elif neighbor in rec_stack:
                    # Cycle detected
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)
            
            rec_stack.remove(node)
        
        for node in adjacency_list:
            if node not in visited:
                dfs(node, [])
        
        return cycles
    
    def compute_graph_metrics(
        self,
        relationships: List[Relationship],
    ) -> Dict[str, Any]:
        """
        Compute graph-level metrics.
        
        Args:
            relationships: List of detected relationships
        
        Returns:
            Dict with graph metrics
        """
        adjacency = self.build_adjacency_list(relationships)
        
        # Count nodes and edges
        node_count = len(adjacency)
        edge_count = sum(len(neighbors) for neighbors in adjacency.values())
        
        # Detect cycles
        cycles = self.detect_cycles(adjacency)
        
        # Compute in/out degrees
        in_degrees = {node: 0 for node in adjacency}
        out_degrees = {node: len(neighbors) for node, neighbors in adjacency.items()}
        
        for node, neighbors in adjacency.items():
            for neighbor in neighbors:
                in_degrees[neighbor] += 1
        
        # Find root tables (no incoming edges)
        root_tables = [node for node, degree in in_degrees.items() if degree == 0]
        
        # Find leaf tables (no outgoing edges)
        leaf_tables = [node for node, degree in out_degrees.items() if degree == 0]
        
        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "cycle_count": len(cycles),
            "cycles": cycles,
            "root_tables": root_tables,
            "leaf_tables": leaf_tables,
            "max_out_degree": max(out_degrees.values()) if out_degrees else 0,
            "max_in_degree": max(in_degrees.values()) if in_degrees else 0,
        }


# Singleton instance
_graph_builder = GraphBuilder()


def build_relationship_graph(relationships: List[Relationship]) -> Dict[str, Any]:
    """Convenience function to build JSON graph."""
    return _graph_builder.build_json_graph(relationships)


def export_to_dot(relationships: List[Relationship]) -> str:
    """Convenience function to export to DOT format."""
    return _graph_builder.build_dot_format(relationships)
