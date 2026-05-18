"""
LCIL Candidate Selector

Filters columns to find safe low-cardinality categorical/dimension candidates using cardinality_class.
"""

from __future__ import annotations

import re
from typing import Any

from profiler.lcil.models import LCILCandidate


def select_candidates(
    profiles: list[dict[str, Any]],
    canonical_map: dict[str, dict[str, Any]],
) -> list[LCILCandidate]:
    """
    Select low-cardinality categorical/dimension candidates from profiles using cardinality_class.
    
    Args:
        profiles: List of profile JSON dictionaries
        canonical_map: Dict mapping table_name to canonical JSON
        
    Returns:
        List of LCILCandidate objects
    """
    candidates = []
    
    for profile in profiles:
        table_name = profile.get("table_name", "unknown")
        columns = profile.get("columns", [])
        
        canonical = canonical_map.get(table_name, {})
        canonical_columns = {col.get("name"): col for col in canonical.get("columns", [])}
        
        for col in columns:
            column_name = col.get("column_name", "unknown")
            distinct_count = col.get("distinct_count", 0) or col.get("statistics", {}).get("distinct_count", 0)
            cardinality_class = col.get("cardinality_class")
            logical_type = col.get("logical_type")
            physical_type = col.get("physical_type")
            semantic_type = col.get("semantic_type")
            
            # Core filter: only LOW cardinality (LLM-only for low card values)
            if cardinality_class != "low":
                continue
            
            # Accept categories and dimensions
            if logical_type in ("category", "dimension"):
                pass
            # Accept boolean-like types
            elif _is_boolean_like(physical_type, semantic_type, col):
                pass
            else:
                # Reject everything else
                continue
            
            # Reject unsafe column types
            if _is_rejected_column(column_name, logical_type, semantic_type, col):
                continue
            
            # Extract evidence
            stats = col.get("statistics", {})
            top_values = stats.get("top_values", [])
            sample_values = col.get("sample_values", [])
            
            canonical_col = canonical_columns.get(column_name, {})
            canonical_samples = canonical_col.get("sample_values", [])
            
            candidate = LCILCandidate(
                table_name=table_name,
                column_name=column_name,
                distinct_count=distinct_count if distinct_count else 0,
                logical_type=logical_type,
                physical_type=physical_type,
                semantic_type=semantic_type,
                top_values=top_values if isinstance(top_values, list) else [],
                sample_values=sample_values if isinstance(sample_values, list) else [],
                canonical_samples=canonical_samples if isinstance(canonical_samples, list) else [],
            )
            candidates.append(candidate)
    
    return candidates


def _is_boolean_like(physical_type: str | None, semantic_type: str | None, col: dict[str, Any]) -> bool:
    """Check if column is boolean-like."""
    if physical_type and physical_type.lower() == "boolean":
        return True
    if semantic_type and semantic_type.lower() in ("boolean_flag", "boolean", "yes_no"):
        return True
    return False


def _is_rejected_column(
    column_name: str,
    logical_type: str | None,
    semantic_type: str | None,
    col: dict[str, Any],
) -> bool:
    """
    Reject unsafe columns that should not be enriched.
    
    Rejects:
    - Identifiers, PKs, FKs, references
    - Audit fields
    - Timestamps
    - Descriptions/free text
    - UUIDs
    - Contact fields (email, phone)
    - URLs
    - Passwords/hashes
    - Addresses
    - Raw locations/geospatial points
    - Name patterns ending in 'id'
    """
    name_lower = column_name.lower()
    
    # Reject ID patterns
    if re.search(r"id$", name_lower):
        return True
    if re.search(r"_key$", name_lower):
        return True
    
    # Reject by logical type
    if logical_type:
        lt = logical_type.lower()
        if lt in ("identifier", "reference", "audit", "timestamp", "description", "contact", "geospatial"):
            return True
    
    # Reject by semantic type
    if semantic_type:
        st = semantic_type.lower()
        rejected_semantics = {
            "identifier", "natural_key", "surrogate_key", "foreign_key_candidate",
            "email", "phone", "ssn", "address", "url",
            "timestamp", "timestamp_start", "timestamp_end", "temporal", "temporal_start", "temporal_end",
            "description", "free_text", "comment",
            "latitude", "longitude", "geospatial_point", "geospatial_coordinate",
        }
        if st in rejected_semantics:
            return True
    
    # Reject audit fields by name
    audit_patterns = [
        r"created.*by", r"updated.*by", r"modified.*by", r"deleted.*by",
        r"created.*at", r"updated.*at", r"modified.*at", r"deleted.*at",
        r"last.*update", r"last.*modified", r"valid.*from", r"valid.*to",
    ]
    for pattern in audit_patterns:
        if re.search(pattern, name_lower):
            return True
    
    # Reject UUID-like columns
    if "uuid" in name_lower or "guid" in name_lower:
        return True
    
    # Reject password/hash columns
    if any(term in name_lower for term in ["password", "hash", "token", "secret", "key"]):
        return True
    
    # Reject raw location/coordinate columns
    if any(term in name_lower for term in ["latitude", "longitude", "lat", "lng", "coord"]):
        return True
    
    # Reject address fields
    if any(term in name_lower for term in ["address", "street", "postal", "zip"]):
        return True
    
    # Reject name-like columns (often high cardinality, not semantic)
    if re.search(r"^(full_?)?name$", name_lower):
        return True
    
    return False
