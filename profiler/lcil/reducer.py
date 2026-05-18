"""
LCIL Reducer and Serializer

Aggregates insights and writes the final LCIL report.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from profiler.lcil.models import LCILInsight, LCILReport

log = logging.getLogger(__name__)


def reduce_insights(insights: list[LCILInsight]) -> list[LCILInsight]:
    """
    Reduce and normalize insights.
    
    Currently a pass-through, but can be extended for:
    - Deduplication
    - Ontology tag normalization
    - Cross-column pattern detection
    
    Args:
        insights: List of LCILInsight objects
        
    Returns:
        Reduced list of LCILInsight objects
    """
    # Normalize ontology tags across all insights
    tag_aliases = _build_tag_aliases(insights)
    
    normalized_insights = []
    for insight in insights:
        # Normalize tags using aliases
        normalized_tags = []
        for tag in insight.ontology_tags:
            canonical_tag = tag_aliases.get(tag, tag)
            if canonical_tag not in normalized_tags:
                normalized_tags.append(canonical_tag)
        
        insight.ontology_tags = normalized_tags
        normalized_insights.append(insight)
    
    return normalized_insights


def _build_tag_aliases(insights: list[LCILInsight]) -> dict[str, str]:
    """
    Build ontology tag aliases for normalization.
    
    Maps similar tags to canonical forms:
    - payment -> payments
    - delivery -> deliveries
    - etc.
    """
    aliases = {}
    
    # Collect all tags
    all_tags = set()
    for insight in insights:
        all_tags.update(insight.ontology_tags)
    
    # Simple pluralization normalization
    for tag in all_tags:
        if tag.endswith("s"):
            singular = tag[:-1]
            if singular in all_tags:
                # Map singular to plural
                aliases[singular] = tag
    
    return aliases


def serialize_report(
    insights: list[LCILInsight],
    output_dir: Path,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """
    Serialize LCIL report to JSON file.
    
    Args:
        insights: List of LCILInsight objects
        output_dir: Output directory path
        metadata: Optional generation metadata
        
    Returns:
        Path to written report file
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Build summary
    total_columns = len(insights)
    domains = {}
    confidence_sum = 0.0
    
    for insight in insights:
        domain = insight.semantic_domain
        domains[domain] = domains.get(domain, 0) + 1
        confidence_sum += insight.confidence
    
    avg_confidence = confidence_sum / total_columns if total_columns > 0 else 0.0
    
    summary = {
        "total_columns_enriched": total_columns,
        "unique_domains": len(domains),
        "domain_distribution": domains,
        "average_confidence": round(avg_confidence, 4),
        "high_confidence_count": sum(1 for i in insights if i.confidence >= 0.8),
        "medium_confidence_count": sum(1 for i in insights if 0.5 <= i.confidence < 0.8),
        "low_confidence_count": sum(1 for i in insights if i.confidence < 0.5),
    }
    
    # Build report
    report = LCILReport(
        schema_version="1.0",
        artifact_type="low_cardinality_insights",
        generated_at=datetime.now(),
        metadata=metadata or {},
        summary=summary,
        insights=insights,
    )
    
    # Write to file
    output_path = output_dir / "low_cardinality_insights.json"
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))
    
    log.info(f"LCIL report written: {output_path}")
    log.info(f"  Total columns: {total_columns}")
    log.info(f"  Unique domains: {len(domains)}")
    log.info(f"  Avg confidence: {avg_confidence:.2f}")
    
    return output_path
