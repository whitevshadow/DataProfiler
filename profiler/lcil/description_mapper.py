"""
LCIL Description Mapper

Transforms LLM-generated descriptions into LCIL insights.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from dataclasses import dataclass

from profiler.lcil.models import LCILCandidate

log = logging.getLogger(__name__)


# Semantic domain normalization mappings
DOMAIN_MAPPINGS = {
    "payment method": "PaymentMethod",
    "payment": "PaymentMethod",
    "delivery method": "DeliveryMethod",
    "delivery": "DeliveryMethod",
    "shipping": "DeliveryMethod",
    "transaction type": "TransactionType",
    "transaction": "TransactionType",
    "category": "Category",
    "status": "Status",
    "state": "Status",
    "boolean flag": "BooleanFlag",
    "boolean": "BooleanFlag",
    "flag": "BooleanFlag",
    "geographic entity": "GeoEntity",
    "geography": "GeoEntity",
    "geo": "GeoEntity",
    "location": "GeoEntity",
    "country": "Country",
    "region": "Region",
    "territory": "Region",
    "color": "Color",
    "colour": "Color",
    "package type": "PackagingType",
    "packaging": "PackagingType",
    "customer category": "CustomerCategory",
    "supplier category": "SupplierCategory",
    "buying group": "BuyingGroup",
    "stock group": "StockGroup",
    "product category": "ProductCategory",
    "priority": "Priority",
    "severity": "Severity",
    "risk": "RiskLevel",
    "workflow": "WorkflowState",
    "lifecycle": "WorkflowState",
    "dimension": "Dimension",
}


@dataclass
class LowCardColumn:
    """Container for low-cardinality column data."""
    table_name: str
    column_name: str
    description: dict  # LLM description object
    profile_data: dict  # Profile statistics
    distinct_count: int
    top_values: list
    sample_values: list


def load_enrichment_sources(output_base: str) -> tuple[dict, list, list, dict]:
    """
    Load all source data for enrichment.
    
    Returns:
        descriptions: Dict[table.column → description object]
        relationships: List of relationship objects
        profiles: List of profile dicts
        canonical_map: Dict[table_name → canonical dict]
    """
    output_root = Path(output_base)
    
    # Load descriptions.json
    descriptions = _load_descriptions(output_root / "descriptions" / "descriptions.json")
    log.info(f"Loaded {len(descriptions)} descriptions")
    
    # Load relationships.json
    relationships = _load_relationships(output_root / "relationships" / "relationships.json")
    log.info(f"Loaded {len(relationships)} relationships")
    
    # Load profiles
    profiles = _load_profiles(output_root / "profiles")
    log.info(f"Loaded {len(profiles)} profiles")
    
    # Load canonical files
    canonical_map = _load_canonical_map(output_root / "canonical")
    log.info(f"Loaded {len(canonical_map)} canonical files")
    
    return descriptions, relationships, profiles, canonical_map


def _load_descriptions(path: Path) -> dict:
    """Load descriptions.json and build lookup dict."""
    if not path.exists():
        log.warning(f"Descriptions file not found: {path}")
        return {}
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Build dict: table.column → description object
    descriptions = {}
    for desc in data:
        table = desc.get("table_name", "unknown")
        column = desc.get("column_name", "unknown")
        key = f"{table}.{column}"
        descriptions[key] = desc
    
    return descriptions


def _load_relationships(path: Path) -> list:
    """Load relationships.json."""
    if not path.exists():
        log.warning(f"Relationships file not found: {path}")
        return []
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return data.get("relationships", [])


def _load_profiles(profiles_dir: Path) -> list:
    """Load all profile JSON files."""
    profiles = []
    
    if not profiles_dir.exists():
        log.warning(f"Profiles directory not found: {profiles_dir}")
        return profiles
    
    for profile_path in profiles_dir.glob("*.profile.json"):
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                profile_data = json.load(f)
            profiles.append(profile_data)
        except Exception as e:
            log.error(f"Failed to load profile {profile_path}: {e}")
    
    return profiles


def _load_canonical_map(canonical_dir: Path) -> dict:
    """Load canonical files and map by table_name."""
    canonical_map = {}
    
    if not canonical_dir.exists():
        log.warning(f"Canonical directory not found: {canonical_dir}")
        return canonical_map
    
    for canonical_path in canonical_dir.glob("*.canonical.json"):
        try:
            with open(canonical_path, "r", encoding="utf-8") as f:
                canonical_data = json.load(f)
            
            table_name = canonical_data.get("table_name") or canonical_data.get("table_id")
            if table_name:
                canonical_map[table_name] = canonical_data
        except Exception as e:
            log.error(f"Failed to load canonical {canonical_path}: {e}")
    
    return canonical_map


def filter_low_cardinality_columns(
    descriptions: dict,
    profiles: list,
) -> list[LowCardColumn]:
    """
    Filter descriptions to only low-cardinality columns.
    
    Returns: List of LowCardColumn objects
    """
    low_card_columns = []
    
    for profile in profiles:
        table_name = profile.get("table_name", "unknown")
        columns = profile.get("columns", [])
        
        for col in columns:
            column_name = col.get("column_name", "unknown")
            cardinality_class = col.get("cardinality_class")
            
            # Only low cardinality
            if cardinality_class != "low":
                continue
            
            # Find matching description
            key = f"{table_name}.{column_name}"
            description = descriptions.get(key)
            
            if not description:
                log.debug(f"No description found for {key}")
                continue
            
            # Extract statistics
            stats = col.get("statistics", {})
            distinct_count = stats.get("distinct_count", 0)
            top_values = stats.get("top_values", [])
            sample_values = col.get("sample_values", [])
            
            low_card_col = LowCardColumn(
                table_name=table_name,
                column_name=column_name,
                description=description,
                profile_data=col,
                distinct_count=distinct_count,
                top_values=top_values,
                sample_values=sample_values,
            )
            low_card_columns.append(low_card_col)
    
    return low_card_columns


def transform_description_to_base_insight(
    column_data: LowCardColumn,
) -> dict[str, Any]:
    """
    Transform LLM description into base insight data.
    
    Returns: Dict with base insight fields
    """
    desc = column_data.description
    
    # Extract fields from description
    data_domain = desc.get("data_domain", "Unknown")
    business_purpose = desc.get("business_purpose", "")
    semantic_desc = desc.get("semantic_description", "")
    likely_relationships = desc.get("likely_relationships", [])
    
    # Normalize semantic domain
    semantic_domain = normalize_domain(data_domain)
    
    # Extract ontology tags from data_domain
    ontology_tags = extract_ontology_tags(data_domain, semantic_desc)
    
    # Build base insight
    base_insight = {
        "table_name": column_data.table_name,
        "column_name": column_data.column_name,
        "semantic_domain": semantic_domain,
        "business_meaning": business_purpose or semantic_desc,
        "confidence": 0.85,  # Base confidence from successful LLM
        "is_ordered": False,
        "is_hierarchical": False,
        "is_workflow": False,
        "is_boolean": False,
        "suggested_entity": None,
        "ontology_tags": ontology_tags,
        "insights": [semantic_desc] if semantic_desc else [],
        "evidence": [
            f"LLM semantic description (domain: {data_domain})",
            f"{column_data.distinct_count} distinct values observed",
        ],
        "graph_nodes": [],
        "graph_edges": [],
    }
    
    return base_insight


def normalize_domain(data_domain: str) -> str:
    """
    Normalize data_domain to PascalCase semantic domain.
    
    Args:
        data_domain: Raw domain from LLM (e.g., "payment method", "boolean flag")
        
    Returns:
        Normalized domain (e.g., "PaymentMethod", "BooleanFlag")
    """
    domain_lower = data_domain.lower().strip()
    
    # Check direct mappings
    for pattern, normalized in DOMAIN_MAPPINGS.items():
        if pattern in domain_lower:
            return normalized
    
    # Fallback: Title case and remove spaces
    words = data_domain.split()
    if words:
        return "".join(word.capitalize() for word in words)
    
    return "Unknown"


def extract_ontology_tags(data_domain: str, semantic_desc: str) -> list[str]:
    """
    Extract ontology tags from domain and description.
    
    Returns: List of lowercase tags
    """
    tags = set()
    
    # Extract from domain
    domain_words = re.findall(r'\w+', data_domain.lower())
    tags.update(domain_words)
    
    # Extract key terms from description
    key_terms = [
        "payment", "delivery", "transaction", "category", "status",
        "geographic", "location", "country", "region", "color",
        "package", "customer", "supplier", "product", "boolean",
        "flag", "workflow", "lifecycle", "dimension", "measure",
    ]
    
    desc_lower = semantic_desc.lower() if semantic_desc else ""
    for term in key_terms:
        if term in desc_lower or term in data_domain.lower():
            tags.add(term)
    
    # Remove common stop words
    stop_words = {"the", "a", "an", "is", "are", "for", "of", "to", "in", "on"}
    tags = tags - stop_words
    
    return sorted(list(tags))
