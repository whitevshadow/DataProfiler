"""
LCIL Relationship Enhancer

Enhances insights with relationship data from relationships.json.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def find_column_relationships(
    table: str,
    column: str,
    relationships: list,
) -> dict[str, Any]:
    """
    Find all relationships involving this column.
    
    Args:
        table: Table name
        column: Column name
        relationships: List of relationship objects from relationships.json
        
    Returns:
        {
            "true_fks": [list of TRUE_FK relationships],
            "semantic": [list of SEMANTICALLY_RELATED],
            "incoming": [columns that reference this],
            "outgoing": [columns this references]
        }
    """
    table_lower = table.lower()
    column_lower = column.lower()
    
    true_fks = []
    semantic = []
    incoming = []
    outgoing = []
    
    for rel in relationships:
        rel_class = rel.get("relationship_class", "")
        fk_table = rel.get("fk_table", "").lower()
        fk_column = rel.get("fk_column", "").lower()
        pk_table = rel.get("pk_table", "").lower()
        pk_column = rel.get("pk_column", "").lower()
        
        # Check if this column is involved
        is_fk_side = (fk_table == table_lower and fk_column == column_lower)
        is_pk_side = (pk_table == table_lower and pk_column == column_lower)
        
        if not (is_fk_side or is_pk_side):
            continue
        
        # Categorize by relationship class
        if rel_class == "TRUE_FK":
            true_fks.append(rel)
        elif rel_class == "SEMANTICALLY_RELATED":
            semantic.append(rel)
        
        # Categorize by direction
        if is_fk_side:
            outgoing.append(rel)  # This column references another
        if is_pk_side:
            incoming.append(rel)  # This column is referenced by another
    
    return {
        "true_fks": true_fks,
        "semantic": semantic,
        "incoming": incoming,
        "outgoing": outgoing,
        "total_count": len(true_fks) + len(semantic),
    }


def enhance_insight_with_relationships(
    base_insight: dict[str, Any],
    column_relationships: dict[str, Any],
    descriptions: dict,
) -> dict[str, Any]:
    """
    Add relationship-derived insights and confidence boost.
    
    Args:
        base_insight: Base insight dict from description
        column_relationships: Result from find_column_relationships()
        descriptions: All descriptions dict for FK target lookup
        
    Returns:
        Enhanced insight dict
    """
    insight = base_insight.copy()
    
    true_fks = column_relationships["true_fks"]
    incoming = column_relationships["incoming"]
    outgoing = column_relationships["outgoing"]
    total_count = column_relationships["total_count"]
    
    # Boost confidence if TRUE_FK relationships exist
    if true_fks:
        confidence_boost = min(0.10, len(true_fks) * 0.02)  # Up to +0.10
        insight["confidence"] = min(1.0, insight["confidence"] + confidence_boost)
        insight["evidence"].append(
            f"{len(true_fks)} TRUE_FK relationship(s) detected"
        )
    
    # Add relationship insights
    if incoming:
        insight["insights"].append(
            f"Referenced by {len(incoming)} other column(s)"
        )
    
    if outgoing:
        insight["insights"].append(
            f"References {len(outgoing)} other column(s)"
        )
    
    # Extract suggested entity from FK targets
    if outgoing and not insight.get("suggested_entity"):
        # If this column is an FK, suggest entity from PK table
        for rel in outgoing:
            if rel.get("relationship_class") == "TRUE_FK":
                pk_table = rel.get("pk_table", "")
                if pk_table:
                    # Convert table name to entity (e.g., "application_paymentmethods" → "PaymentMethod")
                    entity = _table_to_entity(pk_table)
                    insight["suggested_entity"] = entity
                    break
    
    # Add relationship count to evidence
    if total_count > 0:
        insight["evidence"].append(
            f"{total_count} total relationship(s) (TRUE_FK + semantic)"
        )
    
    return insight


def _table_to_entity(table_name: str) -> str:
    """
    Convert table name to entity name.
    
    Examples:
        "application_paymentmethods" → "PaymentMethod"
        "sales_customers" → "Customer"
        "warehouse_colors" → "Color"
    """
    # Remove common prefixes
    parts = table_name.lower().split("_")
    
    # Skip schema prefix (first part if common schema name)
    schema_prefixes = {"application", "sales", "purchasing", "warehouse", "dbo", "public"}
    if parts and parts[0] in schema_prefixes:
        parts = parts[1:]
    
    if not parts:
        return "Unknown"
    
    # Take the main table name part
    main_part = parts[0]
    
    # Remove plural 's' or 'es'
    if main_part.endswith("ies"):
        main_part = main_part[:-3] + "y"
    elif main_part.endswith("ses") or main_part.endswith("ches") or main_part.endswith("xes"):
        main_part = main_part[:-2]
    elif main_part.endswith("s") and not main_part.endswith("ss"):
        main_part = main_part[:-1]
    
    # Capitalize
    return main_part.capitalize()
