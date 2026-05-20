"""
DBML Parser
Converts DBML text to JSON graph structure for viewer.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional


def parse_dbml(dbml_content: str) -> Dict[str, Any]:
    """
    Parse DBML text into JSON graph structure.
    
    Args:
        dbml_content: Raw DBML text
        
    Returns:
        Dict with:
            - nodes: List[Dict] - Table nodes
            - edges: List[Dict] - Relationship edges
            - metadata: Dict - Stats and info
    """
    nodes = []
    edges = []
    
    # Parse tables
    table_pattern = re.compile(
        r'Table\s+(\w+)\s*\{([^}]+)\}',
        re.IGNORECASE | re.DOTALL
    )
    
    for match in table_pattern.finditer(dbml_content):
        table_name = match.group(1)
        table_body = match.group(2)
        
        # Parse columns
        columns = []
        for line in table_body.split('\n'):
            line = line.strip()
            if not line or line.startswith('//'):
                continue
            
            # Match: columnname type [attributes]
            col_match = re.match(r'(\w+)\s+(\w+)(\s+\[([^\]]+)\])?', line)
            if col_match:
                col_name = col_match.group(1)
                col_type = col_match.group(2)
                col_attrs = col_match.group(4) or ""
                
                column = {
                    "name": col_name,
                    "type": col_type,
                    "pk": "pk" in col_attrs or "primary key" in col_attrs.lower(),
                    "nullable": "not null" not in col_attrs.lower(),
                    "unique": "unique" in col_attrs.lower(),
                }
                
                # Extract note
                note_match = re.search(r'note:\s*[\'"]([^\'"]+)[\'"]', col_attrs)
                if note_match:
                    column["note"] = note_match.group(1)
                
                columns.append(column)
        
        nodes.append({
            "id": table_name,
            "name": table_name,
            "type": "table",
            "columns": columns,
        })
    
    # Parse relationships
    ref_pattern = re.compile(
        r'Ref:\s*(\w+)\.(\w+)\s*([<>-]+)\s*(\w+)\.(\w+)',
        re.IGNORECASE
    )
    
    for match in ref_pattern.finditer(dbml_content):
        from_table = match.group(1)
        from_column = match.group(2)
        rel_type = match.group(3)
        to_table = match.group(4)
        to_column = match.group(5)
        
        # Determine cardinality
        if '>' in rel_type:
            cardinality = "1:N"
        elif '<' in rel_type:
            cardinality = "N:1"
        else:
            cardinality = "1:1"
        
        edges.append({
            "id": f"{from_table}.{from_column}-{to_table}.{to_column}",
            "source": from_table,
            "sourceColumn": from_column,
            "target": to_table,
            "targetColumn": to_column,
            "type": "TRUE_FK",
            "cardinality": cardinality,
        })
    
    # Build metadata
    metadata = {
        "tables": len(nodes),
        "relationships": len(edges),
        "parsedAt": None,  # Will be set when saved
    }
    
    return {
        "nodes": nodes,
        "edges": edges,
        "metadata": metadata,
    }


def save_dbml_render(
    graph: Dict[str, Any],
    output_base: Path = Path("output")
) -> str:
    """
    Save parsed DBML graph to JSON cache.
    
    Args:
        graph: Parsed graph from parse_dbml()
        output_base: Base output directory
        
    Returns:
        Path to saved file
    """
    from datetime import datetime
    
    ui_dir = output_base / "ui"
    ui_dir.mkdir(parents=True, exist_ok=True)
    
    render_path = ui_dir / "dbml_render.json"
    
    # Add timestamp
    graph["metadata"]["parsedAt"] = datetime.now().isoformat()
    
    # Save
    render_path.write_text(
        json.dumps(graph, indent=2),
        encoding="utf-8"
    )
    
    return str(render_path)


def load_dbml_render(output_base: Path = Path("output")) -> Optional[Dict[str, Any]]:
    """
    Load cached DBML render graph.
    
    Returns:
        Cached graph or None if not found
    """
    render_path = output_base / "ui" / "dbml_render.json"
    
    if not render_path.exists():
        return None
    
    try:
        return json.loads(render_path.read_text(encoding="utf-8"))
    except Exception:
        return None
