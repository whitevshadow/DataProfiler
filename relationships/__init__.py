"""
Relationships Layer - Foreign Key Detection & Relationship Intelligence

This module provides enterprise-grade foreign key detection and relationship
inference capabilities for the SDIE (Semantic Data Intelligence Engine).

Core Principles:
- Deterministic-first validation (containment is truth)
- ANN for candidate retrieval only (NOT validation)
- Scalable to TB-scale datasets
- Explainable relationship evidence
- Reproducible and versioned

Architecture:
    Layer 1: Candidate Pair Generation (avoid O(n²))
    Layer 2: Type Compatibility Filtering
    Layer 3: Overlap Estimation & Bloom Filter Pruning
    Layer 4: Containment Validation (authoritative)
    Layer 5: Confidence Scoring & Evidence Fusion
    Layer 6: Suppression Rules (prevent invalid patterns)
    Layer 7: Relationship Report Generation

Semantic Enhancement (Optional):
    - Semantic column descriptions
    - ANN-based candidate retrieval
    - DBSCAN clustering
    - Relationship adjudication (TRUE_FK vs SEMANTICALLY_RELATED)
"""

from relationships.relationship_models import (
    RelationshipType,
    RelationshipEvidence,
    RelationshipValidation,
    RelationshipExecutionMetadata,
    Relationship,
    RelationshipReport,
    CandidatePair,
    TypeCompatibilityResult,
    ContainmentResult,
)

from relationships.relationship_engine import (
    RelationshipEngine,
    detect_relationships,
)

# Semantic enhancement components
from relationships.semantic_column_descriptor import (
    ColumnDescription,
    SemanticColumnDescriptor,
    generate_column_description,
)

from relationships.semantic_embedding_engine import (
    SemanticCandidate,
    SemanticEmbeddingEngine,
    ANNCandidateRetriever,
    SemanticCandidateManager,
    generate_semantic_candidates,
)

from relationships.semantic_clustering import (
    RelationshipClass,
    SemanticCluster,
    AdjudicatedRelationship,
    SemanticClusteringEngine,
    SemanticRelationshipAdjudicator,
    cluster_columns_by_semantics,
    adjudicate_relationship,
)

from relationships.semantic_relationship_engine import (
    SemanticRelationshipEngine,
    detect_relationships_with_semantics,
)

__version__ = "1.0.0"

__all__ = [
    # Core Models
    "RelationshipType",
    "RelationshipEvidence",
    "RelationshipValidation",
    "RelationshipExecutionMetadata",
    "Relationship",
    "RelationshipReport",
    "CandidatePair",
    "TypeCompatibilityResult",
    "ContainmentResult",
    # Core Engine
    "RelationshipEngine",
    "detect_relationships",
    # Semantic Models
    "ColumnDescription",
    "SemanticCandidate",
    "SemanticCluster",
    "AdjudicatedRelationship",
    "RelationshipClass",
    # Semantic Components
    "SemanticColumnDescriptor",
    "SemanticEmbeddingEngine",
    "ANNCandidateRetriever",
    "SemanticCandidateManager",
    "SemanticClusteringEngine",
    "SemanticRelationshipAdjudicator",
    "SemanticRelationshipEngine",
    # Convenience Functions
    "generate_column_description",
    "generate_semantic_candidates",
    "cluster_columns_by_semantics",
    "adjudicate_relationship",
    "detect_relationships_with_semantics",
]
