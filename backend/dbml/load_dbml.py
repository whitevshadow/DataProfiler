"""
DBML Loader
Loads existing schema.dbml from output directory without regeneration.
"""

from pathlib import Path
from typing import Dict, Any, Optional


def load_dbml(
    dbml_path: Optional[str] = None,
    output_base: Path = Path("output")
) -> Dict[str, Any]:
    """
    Load existing schema.dbml file.
    
    Args:
        dbml_path: Optional explicit path to DBML file
        output_base: Base output directory
        
    Returns:
        Dict with:
            - success: bool
            - content: str (DBML text)
            - path: str (resolved path)
            - error: str (if failed)
    """
    # Determine DBML path
    if dbml_path:
        dbml_file = Path(dbml_path)
    else:
        # Try multiple locations
        candidates = [
            output_base / "erd" / "schema.dbml",
            output_base / "visualizations" / "schema.dbml",
            Path("schema.dbml"),
        ]
        
        dbml_file = None
        for candidate in candidates:
            if candidate.exists():
                dbml_file = candidate
                break
    
    # Validate file exists
    if not dbml_file or not dbml_file.exists():
        return {
            "success": False,
            "error": f"DBML file not found. Expected locations: {[str(c) for c in candidates]}",
            "hint": "Generate DBML first using generate_er_visualizations(mode='dbml')"
        }
    
    # Load content
    try:
        content = dbml_file.read_text(encoding="utf-8")
        
        if not content.strip():
            return {
                "success": False,
                "error": f"DBML file is empty: {dbml_file}",
            }
        
        return {
            "success": True,
            "content": content,
            "path": str(dbml_file.resolve()),
            "size_bytes": len(content),
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to read DBML file: {e}",
            "path": str(dbml_file),
        }


def get_dbml_path(output_base: Path = Path("output")) -> Optional[str]:
    """
    Get path to existing DBML file without loading content.
    
    Returns:
        Path string if found, None otherwise
    """
    candidates = [
        output_base / "erd" / "schema.dbml",
        output_base / "visualizations" / "schema.dbml",
    ]
    
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())
    
    return None
