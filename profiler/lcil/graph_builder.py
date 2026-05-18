"""
LCIL Graph Builder

Builds knowledge graph node and edge suggestions from enriched insights.
"""

from __future__ import annotations

import logging
from typing import Any

from profiler.lcil.models import GraphNode, GraphEdge

log = logging.getLogger(__name__)


def build_graph_suggestions(
    insight_data: dict[str, Any],
    profile_data: dict[str, Any],
    column_relationships: dict[str, Any],
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """
    Build knowledge graph nodes and edges.
    
    Node Types:
    - Domain: Semantic domain concept
    - Entity: Suggested entity type
    - Value: Observed categorical value
    - Table: Source table
    
    Edge Types:
    - INSTANCE_OF: Value → Domain
    - DEFINES: Column → Entity
    - RELATES_TO: Column → Column (from relationships)
    - TRUE_FK: Strong foreign key
    - SEMANTIC_LINK: Weak semantic relationship
    
    Args:
        insight_data: Base insight dict
        profile_data: Column profile data with statistics
        column_relationships: Relationships dict
        
    Returns:
        (nodes, edges) tuple
    """
    nodes = []
    edges = []
    
    table_name = insight_data["table_name"]
    column_name = insight_data["column_name"]
    semantic_domain = insight_data["semantic_domain"]
    suggested_entity = insight_data.get("suggested_entity")
    
    # Build column identifier
    column_id = f"{table_name}.{column_name}"
    
    # 1. Domain Node
    if semantic_domain and semantic_domain != "Unknown":
        domain_node = GraphNode(
            id=semantic_domain,
            label=_pascal_to_title(semantic_domain),
            node_type="Domain",
            properties={}
        )
        nodes.append(domain_node)
    
    # 2. Entity Node (if suggested)
    if suggested_entity:
        entity_node = GraphNode(
            id=f"{suggested_entity}_Entity",
            label=suggested_entity,
            node_type="Entity",
            properties={"table": table_name}
        )
        nodes.append(entity_node)
        
        # Edge: Column → Entity (DEFINES)
        edges.append(GraphEdge(
            source=column_id,
            target=f"{suggested_entity}_Entity",
            relationship="DEFINES",
            properties={}
        ))
    
    # 3. Value Nodes (observed categorical values)
    stats = profile_data.get("statistics", {})
    top_values = stats.get("top_values", []) or []
    
    for item in top_values[:10]:  # Limit to top 10
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            value, count = item[0], item[1]
        else:
            value, count = item, 0
        
        if value is None or str(value).strip() == "":
            continue
        
        value_str = str(value)
        value_id = f"{column_id}:{value_str}"
        
        # Calculate percentage if we have total count
        total_count = stats.get("distinct_count", 0)
        percentage = (count / total_count * 100) if total_count > 0 else 0.0
        
        value_node = GraphNode(
            id=value_id,
            label=value_str,
            node_type="Value",
            properties={
                "count": count,
                "percentage": round(percentage, 2),
                "column": column_id,
            }
        )
        nodes.append(value_node)
        
        # Edge: Value → Domain (INSTANCE_OF)
        if semantic_domain and semantic_domain != "Unknown":
            edges.append(GraphEdge(
                source=value_id,
                target=semantic_domain,
                relationship="INSTANCE_OF",
                properties={}
            ))
    
    # 4. Relationship Edges
    # TRUE_FK relationships
    for rel in column_relationships.get("true_fks", []):
        fk_table = rel.get("fk_table", "")
        fk_column = rel.get("fk_column", "")
        pk_table = rel.get("pk_table", "")
        pk_column = rel.get("pk_column", "")
        confidence = rel.get("confidence", 0.0)
        
        # Determine source and target
        if fk_table.lower() == table_name.lower() and fk_column.lower() == column_name.lower():
            # This column is the FK
            source_id = column_id
            target_id = f"{pk_table}.{pk_column}"
        else:
            # This column is the PK
            source_id = f"{fk_table}.{fk_column}"
            target_id = column_id
        
        edges.append(GraphEdge(
            source=source_id,
            target=target_id,
            relationship="TRUE_FK",
            properties={"confidence": confidence}
        ))
    
    # Semantic relationships
    for rel in column_relationships.get("semantic", []):
        fk_table = rel.get("fk_table", "")
        fk_column = rel.get("fk_column", "")
        pk_table = rel.get("pk_table", "")
        pk_column = rel.get("pk_column", "")
        confidence = rel.get("confidence", 0.0)
        
        # Determine source and target
        if fk_table.lower() == table_name.lower() and fk_column.lower() == column_name.lower():
            source_id = column_id
            target_id = f"{pk_table}.{pk_column}"
        else:
            source_id = f"{fk_table}.{fk_column}"
            target_id = column_id
        
        edges.append(GraphEdge(
            source=source_id,
            target=target_id,
            relationship="SEMANTIC_LINK",
            properties={"confidence": confidence}
        ))
    
    return nodes, edges


def _pascal_to_title(pascal_str: str) -> str:
    """
    Convert PascalCase to Title Case with spaces.
    
    Examples:
        "PaymentMethod" → "Payment Method"
        "GeoEntity" → "Geo Entity"
    """
    # Insert space before uppercase letters
    result = ""
    for i, char in enumerate(pascal_str):
        if i > 0 and char.isupper() and pascal_str[i-1].islower():
            result += " "
        result += char
    
    return result
