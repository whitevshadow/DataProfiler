"""
LCIL Deterministic Rules

Deterministic detection of column flags (boolean, ordered, hierarchical, workflow).
"""

from __future__ import annotations

import re
import logging
from typing import Any

log = logging.getLogger(__name__)


# Ordered value sequences
ORDERED_SEQUENCES = [
    ["low", "medium", "high"],
    ["small", "medium", "large"],
    ["xs", "s", "m", "l", "xl"],
    ["bronze", "silver", "gold", "platinum"],
    ["basic", "standard", "premium", "enterprise"],
    ["1", "2", "3", "4", "5"],
    ["one", "two", "three", "four", "five"],
    ["first", "second", "third", "fourth"],
    ["poor", "fair", "good", "excellent"],
]

# Lifecycle/workflow terms
LIFECYCLE_TERMS = {
    "created", "draft", "pending", "submitted", "approved",
    "rejected", "processing", "completed", "cancelled",
    "closed", "archived", "active", "inactive", "open",
    "new", "in_progress", "done", "failed", "success",
}


def detect_flags(
    column_name: str,
    distinct_count: int,
    top_values: list,
    sample_values: list,
) -> dict[str, Any]:
    """
    Detect column flags using deterministic rules.
    
    Args:
        column_name: Column name
        distinct_count: Number of distinct values
        top_values: List of (value, count) tuples
        sample_values: List of sample values
        
    Returns:
        {
            "is_boolean": bool,
            "is_ordered": bool,
            "is_hierarchical": bool,
            "is_workflow": bool,
            "confidence_adjustment": float  # -0.05 to +0.10
        }
    """
    # Extract unique values
    unique_values = _extract_unique_values(top_values, sample_values)
    
    # Detect flags
    is_boolean = _detect_boolean(column_name, distinct_count, unique_values)
    is_ordered = _detect_ordered(unique_values)
    is_workflow = _detect_workflow(unique_values)
    is_hierarchical = False  # Detected from relationships, not values
    
    # Compute confidence adjustment
    confidence_adjustment = 0.0
    
    if is_boolean:
        confidence_adjustment += 0.10  # Very confident about booleans
    elif is_ordered:
        confidence_adjustment += 0.05  # Moderately confident about ordered
    elif is_workflow:
        confidence_adjustment += 0.05  # Moderately confident about workflow
    
    # Penalize if too many distinct values for a categorical
    if distinct_count > 30:
        confidence_adjustment -= 0.05
    
    return {
        "is_boolean": is_boolean,
        "is_ordered": is_ordered,
        "is_hierarchical": is_hierarchical,
        "is_workflow": is_workflow,
        "confidence_adjustment": confidence_adjustment,
    }


def _extract_unique_values(top_values: list, sample_values: list) -> list[str]:
    """Extract unique string values from top_values and sample_values."""
    values = set()
    
    # From top_values (list of [value, count] or (value, count))
    if top_values:
        for item in top_values:
            if isinstance(item, (list, tuple)) and len(item) >= 1:
                values.add(str(item[0]).lower().strip())
            else:
                values.add(str(item).lower().strip())
    
    # From sample_values
    if sample_values:
        for val in sample_values:
            if val is not None:
                values.add(str(val).lower().strip())
    
    # Remove empty strings
    values.discard("")
    values.discard("none")
    values.discard("null")
    
    return sorted(list(values))


def _detect_boolean(column_name: str, distinct_count: int, unique_values: list[str]) -> bool:
    """
    Detect boolean columns.
    
    Criteria:
    - Column name starts with is/has/can/should
    - Exactly 2 distinct values matching boolean patterns
    """
    # Check column name pattern
    name_lower = column_name.lower()
    if re.match(r"^(is|has|can|should|was|were|will)", name_lower):
        return True
    
    # Check distinct count = 2
    if distinct_count != 2:
        return False
    
    # Check value patterns
    boolean_patterns = [
        {"true", "false"},
        {"yes", "no"},
        {"y", "n"},
        {"1", "0"},
        {"active", "inactive"},
        {"enabled", "disabled"},
        {"on", "off"},
        {"success", "failure"},
        {"pass", "fail"},
    ]
    
    value_set = set(unique_values)
    
    for pattern in boolean_patterns:
        if value_set == pattern:
            return True
    
    return False


def _detect_ordered(unique_values: list[str]) -> bool:
    """
    Detect ordered/ranked columns.
    
    Criteria:
    - Values match a known ordered sequence
    """
    value_set = set(unique_values)
    
    for sequence in ORDERED_SEQUENCES:
        sequence_set = set(sequence)
        
        # Check if all observed values are in this sequence
        if value_set.issubset(sequence_set):
            return True
    
    # Check numeric sequences (1-5, 1-10, etc.)
    try:
        numeric_values = [int(v) for v in unique_values if v.isdigit()]
        if numeric_values and len(numeric_values) >= 2:
            # Check if it's a consecutive range
            numeric_values.sort()
            min_val = numeric_values[0]
            max_val = numeric_values[-1]
            if max_val - min_val <= 10:  # Small range
                return True
    except (ValueError, TypeError):
        pass
    
    return False


def _detect_workflow(unique_values: list[str]) -> bool:
    """
    Detect workflow/lifecycle state columns.
    
    Criteria:
    - At least 2 values match lifecycle terms
    """
    matches = sum(1 for v in unique_values if v in LIFECYCLE_TERMS)
    return matches >= 2


def update_flags_from_relationships(
    flags: dict[str, Any],
    column_relationships: dict[str, Any],
) -> dict[str, Any]:
    """
    Update flags based on relationship analysis.
    
    Detects hierarchical relationships (self-referential FKs).
    """
    flags = flags.copy()
    
    # Detect hierarchical (self-referential FK)
    for rel in column_relationships.get("outgoing", []):
        fk_table = rel.get("fk_table", "").lower()
        pk_table = rel.get("pk_table", "").lower()
        
        if fk_table == pk_table:
            flags["is_hierarchical"] = True
            flags["confidence_adjustment"] += 0.05
            break
    
    return flags
