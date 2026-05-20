"""
DBML State Builder
Builds viewer state including entity details and hover cache.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


def build_entity_cache(
    graph: Dict[str, Any],
    output_base: Path = Path("output")
) -> Dict[str, Any]:
    """
    Build entity detail cache by merging profile, quality, PK, and LCIL data.
    
    Args:
        graph: Parsed DBML graph with nodes
        output_base: Base output directory
        
    Returns:
        Dict mapping entity_id -> merged details
    """
    entity_cache = {}
    
    for node in graph.get("nodes", []):
        entity_id = node["id"]
        entity_data = {}
        
        # Load profile
        profile_path = output_base / "profiles" / f"{entity_id}.json"
        if profile_path.exists():
            try:
                entity_data["profile"] = json.loads(
                    profile_path.read_text(encoding="utf-8")
                )
            except Exception:
                pass
        
        # Load quality
        quality_path = output_base / "quality" / f"{entity_id}.json"
        if quality_path.exists():
            try:
                entity_data["quality"] = json.loads(
                    quality_path.read_text(encoding="utf-8")
                )
            except Exception:
                pass
        
        # Load PK analysis
        pk_path = output_base / "pk_analysis" / f"{entity_id}.json"
        if pk_path.exists():
            try:
                entity_data["pk"] = json.loads(
                    pk_path.read_text(encoding="utf-8")
                )
            except Exception:
                pass
        
        # Load LCIL
        lcil_path = output_base / "lcil" / f"{entity_id}.json"
        if lcil_path.exists():
            try:
                entity_data["lcil"] = json.loads(
                    lcil_path.read_text(encoding="utf-8")
                )
            except Exception:
                pass
        
        if entity_data:
            entity_cache[entity_id] = entity_data
    
    return entity_cache


def build_hover_cache(
    graph: Dict[str, Any],
    entity_cache: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build hover card cache for columns.
    
    Args:
        graph: Parsed DBML graph
        entity_cache: Entity details from build_entity_cache()
        
    Returns:
        Dict mapping "table.column" -> hover card data
    """
    hover_cache = {}
    
    for node in graph.get("nodes", []):
        table_id = node["id"]
        entity_data = entity_cache.get(table_id, {})
        
        for column in node.get("columns", []):
            col_name = column["name"]
            key = f"{table_id}.{col_name}"
            
            hover_data = {
                "column": col_name,
                "table": table_id,
                "type": column.get("type", "UNKNOWN"),
                "pk": column.get("pk", False),
                "nullable": column.get("nullable", True),
            }
            
            # Add quality if available
            if "quality" in entity_data:
                col_quality = entity_data["quality"].get("columns", {}).get(col_name)
                if col_quality:
                    hover_data["quality"] = col_quality.get("overall_score", 0.0)
            
            # Add PK info
            if "pk" in entity_data:
                pk_analysis = entity_data["pk"].get("candidates", [])
                for pk_candidate in pk_analysis:
                    if pk_candidate.get("column") == col_name:
                        hover_data["cardinality"] = pk_candidate.get("uniqueness_ratio", 0.0)
                        break
            
            # Add LCIL insights
            if "lcil" in entity_data:
                insights = entity_data["lcil"].get("insights", {})
                col_insight = insights.get(col_name)
                if col_insight:
                    hover_data["business_meaning"] = col_insight.get("semantic_description", "")
                    hover_data["sample_values"] = col_insight.get("sample_values", [])
            
            # Add note from DBML
            if "note" in column:
                hover_data["note"] = column["note"]
            
            # Find relationships
            relationships = []
            for edge in graph.get("edges", []):
                if edge["source"] == table_id and edge["sourceColumn"] == col_name:
                    relationships.append({
                        "direction": "outgoing",
                        "target": f"{edge['target']}.{edge['targetColumn']}",
                        "type": edge["type"],
                    })
                elif edge["target"] == table_id and edge["targetColumn"] == col_name:
                    relationships.append({
                        "direction": "incoming",
                        "source": f"{edge['source']}.{edge['sourceColumn']}",
                        "type": edge["type"],
                    })
            
            if relationships:
                hover_data["relationships"] = relationships
            
            hover_cache[key] = hover_data
    
    return hover_cache


def save_viewer_state(
    graph: Dict[str, Any],
    entity_cache: Dict[str, Any],
    hover_cache: Dict[str, Any],
    output_base: Path = Path("output")
) -> Dict[str, str]:
    """
    Save all viewer state files.
    
    Returns:
        Dict with paths to saved files
    """
    ui_dir = output_base / "ui"
    ui_dir.mkdir(parents=True, exist_ok=True)
    
    paths = {}
    
    # Save entity cache
    entity_path = ui_dir / "entity_cache.json"
    entity_path.write_text(
        json.dumps(entity_cache, indent=2),
        encoding="utf-8"
    )
    paths["entity_cache"] = str(entity_path)
    
    # Save hover cache
    hover_path = ui_dir / "hover_cache.json"
    hover_path.write_text(
        json.dumps(hover_cache, indent=2),
        encoding="utf-8"
    )
    paths["hover_cache"] = str(hover_path)
    
    # Build relationship tree (for FK traversal)
    relationship_tree = build_relationship_tree(graph)
    tree_path = ui_dir / "relationship_tree.json"
    tree_path.write_text(
        json.dumps(relationship_tree, indent=2),
        encoding="utf-8"
    )
    paths["relationship_tree"] = str(tree_path)
    
    return paths


def build_relationship_tree(graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build relationship tree for FK traversal.
    TRUE_FK only.
    
    Returns:
        Dict mapping table_id -> {children: [...], parents: [...]}
    """
    tree = {}
    
    # Initialize all tables
    for node in graph.get("nodes", []):
        tree[node["id"]] = {
            "children": [],
            "parents": [],
        }
    
    # Add relationships (TRUE_FK only)
    for edge in graph.get("edges", []):
        if edge.get("type") == "TRUE_FK":
            source = edge["source"]
            target = edge["target"]
            
            # source has FK to target, so target is parent of source
            if source in tree:
                tree[source]["parents"].append({
                    "table": target,
                    "via": edge["sourceColumn"],
                })
            
            # target is referenced by source, so source is child of target
            if target in tree:
                tree[target]["children"].append({
                    "table": source,
                    "via": edge["targetColumn"],
                })
    
    return tree
