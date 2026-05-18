"""
Low Cardinality Intelligence Layer (LCIL)

Semantic enrichment for low-cardinality categorical/dimension columns.
Runs after profile generation and before LLM descriptions/relationship detection.
"""

from profiler.lcil.engine import enrich_low_cardinality_intelligence
from profiler.lcil.models import (
    LCILInsight,
    LCILReport,
    LCILCandidate,
    GraphNode,
    GraphEdge,
)

__all__ = [
    "enrich_low_cardinality_intelligence",
    "LCILInsight",
    "LCILReport",
    "LCILCandidate",
    "GraphNode",
    "GraphEdge",
]
