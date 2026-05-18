"""
Semantic Clustering & Relationship Adjudicator

Uses DBSCAN clustering to group semantically related columns.
Provides relationship adjudication to distinguish:
    - TRUE FK (validated containment + semantic alignment)
    - SEMANTICALLY_RELATED (similar meaning, no FK relationship)
    - SHARED_ENTITY_DOMAIN (same business domain, no direct link)
    - POSSIBLE_REFERENCE (weak evidence, needs review)
    - FALSE_POSITIVE (rejected)

Core Principles:
    - Clustering is for SEMANTIC GROUPING only
    - Clusters are hints, NOT authoritative relationships
    - Final adjudication combines semantic + deterministic evidence
"""

from typing import List, Dict, Tuple, Any, Optional, Set
from dataclasses import dataclass
from enum import Enum
import numpy as np
from sklearn.cluster import DBSCAN
from relationships.semantic_column_descriptor import ColumnDescription


class RelationshipClass(str, Enum):
    """Classification of relationship types."""
    TRUE_FK = "TRUE_FK"  # Validated FK with containment + semantics
    SEMANTICALLY_RELATED = "SEMANTICALLY_RELATED"  # Similar meaning, no FK
    SHARED_ENTITY_DOMAIN = "SHARED_ENTITY_DOMAIN"  # Same business domain
    POSSIBLE_REFERENCE = "POSSIBLE_REFERENCE"  # Weak evidence
    FALSE_POSITIVE = "FALSE_POSITIVE"  # Rejected


@dataclass
class SemanticCluster:
    """A cluster of semantically related columns."""
    cluster_id: int
    columns: List[Tuple[str, str]]  # (table, column) pairs
    cluster_label: str
    centroid_description: str


@dataclass
class AdjudicatedRelationship:
    """A relationship with semantic adjudication."""
    fk_table: str
    fk_column: str
    pk_table: str
    pk_column: str
    
    # Classification
    relationship_class: RelationshipClass
    confidence: float
    
    # Evidence
    semantic_similarity: float
    containment_ratio: float
    type_compatibility: float
    
    # Reasoning
    adjudication_reasoning: List[str]
    semantic_cluster_id: Optional[int] = None
    suppression_warnings: List[str] = None


class SemanticClusteringEngine:
    """
    Clusters columns using DBSCAN based on semantic embeddings.
    
    Clusters represent semantically related columns:
    - customer-related fields
    - geography-related fields
    - product-related fields
    
    Clusters are hints for relationship discovery, NOT authoritative links.
    """
    
    def __init__(
        self,
        eps: float = 0.5,
        min_samples: int = 2,
    ):
        """
        Initialize clustering engine.
        
        Args:
            eps: DBSCAN epsilon (distance threshold)
            min_samples: Minimum cluster size
        """
        self.eps = eps
        self.min_samples = min_samples
        self.clusterer = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine')
    
    def cluster_columns(
        self,
        descriptions: List[ColumnDescription],
        embeddings: np.ndarray,
    ) -> Dict[int, SemanticCluster]:
        """
        Cluster columns by semantic similarity.
        
        Args:
            descriptions: List of ColumnDescription objects
            embeddings: Embedding matrix
        
        Returns:
            Dict mapping cluster_id -> SemanticCluster
        """
        # Run DBSCAN
        cluster_labels = self.clusterer.fit_predict(embeddings)
        
        # Group columns by cluster
        clusters = {}
        for i, label in enumerate(cluster_labels):
            if label == -1:  # Noise point
                continue
            
            if label not in clusters:
                clusters[label] = []
            
            desc = descriptions[i]
            clusters[label].append((desc.table_name, desc.column_name))
        
        # Build SemanticCluster objects
        cluster_objects = {}
        for cluster_id, columns in clusters.items():
            # Get descriptions for this cluster
            cluster_descs = [
                desc for desc in descriptions
                if (desc.table_name, desc.column_name) in columns
            ]
            
            # Infer cluster label
            cluster_label = self._infer_cluster_label(cluster_descs)
            
            # Generate centroid description
            centroid_desc = self._generate_centroid_description(cluster_descs)
            
            cluster_objects[cluster_id] = SemanticCluster(
                cluster_id=cluster_id,
                columns=columns,
                cluster_label=cluster_label,
                centroid_description=centroid_desc,
            )
        
        return cluster_objects
    
    def _infer_cluster_label(self, descriptions: List[ColumnDescription]) -> str:
        """Infer a label for the cluster."""
        
        # Count semantic roles
        role_counts = {}
        for desc in descriptions:
            role = self._get_semantic_role(desc)
            role_counts[role] = role_counts.get(role, 0) + 1
        
        dominant_role = max(role_counts, key=role_counts.get)
        
        # Count entity references
        entity_counts = {}
        for desc in descriptions:
            entity = self._get_entity_reference(desc)
            if entity:
                entity_counts[entity] = entity_counts.get(entity, 0) + 1
        
        if entity_counts:
            dominant_entity = max(entity_counts, key=entity_counts.get)
            return f"{dominant_entity}_{dominant_role}_cluster"
        else:
            return f"{dominant_role}_cluster"
    
    def _generate_centroid_description(
        self,
        descriptions: List[ColumnDescription],
    ) -> str:
        """Generate a centroid description for the cluster."""
        
        # Collect common elements
        roles = set(self._get_semantic_role(desc) for desc in descriptions)
        entities = set(
            entity for entity in (self._get_entity_reference(desc) for desc in descriptions)
            if entity
        )
        
        parts = [f"{len(descriptions)} columns"]
        
        if len(roles) == 1:
            parts.append(f"all {list(roles)[0]}")
        else:
            parts.append(f"mixed roles: {', '.join(roles)}")
        
        if entities:
            parts.append(f"related to: {', '.join(entities)}")
        
        return " | ".join(parts)

    @staticmethod
    def _get_semantic_role(desc: Any) -> str:
        """Return a normalized role for deterministic or LLM descriptions."""
        if hasattr(desc, "semantic_role"):
            return (desc.semantic_role or "unknown").lower()

        domain = (getattr(desc, "data_domain", "") or "").lower()
        if domain in {"primary_key", "foreign_key", "identifier"}:
            return "identifier"
        if domain in {"measure", "dimension", "temporal", "geospatial", "audit"}:
            return domain
        return "unknown"

    @staticmethod
    def _get_entity_reference(desc: Any) -> Optional[str]:
        """Return an entity reference when available from either description shape."""
        if hasattr(desc, "entity_reference"):
            return desc.entity_reference

        relationships = getattr(desc, "likely_relationships", None) or []
        if relationships:
            target = relationships[0]
            if isinstance(target, dict):
                target = target.get("target") or target.get("table") or ""
            target = str(target)
            return target.split(".")[0].lower() if target else None

        column_name = (getattr(desc, "column_name", "") or "").lower()
        if column_name.endswith("id") and len(column_name) > 2:
            return column_name[:-2]

        return None


class SemanticRelationshipAdjudicator:
    """
    Adjudicates relationship classification combining semantic + deterministic evidence.
    
    Decision Logic:
        - containment_ratio >= 0.95 + semantic_similarity >= 0.70 → TRUE_FK
        - containment_ratio >= 0.85 + semantic_similarity >= 0.60 → TRUE_FK
        - containment_ratio < 0.50 + semantic_similarity >= 0.80 → SEMANTICALLY_RELATED
        - containment_ratio < 0.50 + semantic_similarity < 0.40 → FALSE_POSITIVE
        - Edge cases → POSSIBLE_REFERENCE
    """
    
    def __init__(
        self,
        true_fk_containment_threshold: float = 0.85,
        true_fk_semantic_threshold: float = 0.60,
        semantic_related_threshold: float = 0.75,
    ):
        """
        Initialize adjudicator.
        
        Args:
            true_fk_containment_threshold: Min containment for TRUE_FK
            true_fk_semantic_threshold: Min semantic similarity for TRUE_FK
            semantic_related_threshold: Min similarity for SEMANTICALLY_RELATED
        """
        self.true_fk_containment_threshold = true_fk_containment_threshold
        self.true_fk_semantic_threshold = true_fk_semantic_threshold
        self.semantic_related_threshold = semantic_related_threshold
    
    def adjudicate(
        self,
        fk_table: str,
        fk_column: str,
        pk_table: str,
        pk_column: str,
        semantic_similarity: float,
        containment_ratio: float,
        type_compatibility: float,
        confidence: float,
        fk_description: ColumnDescription,
        pk_description: ColumnDescription,
        semantic_cluster_id: Optional[int] = None,
        suppression_warnings: List[str] = None,
    ) -> AdjudicatedRelationship:
        """
        Adjudicate relationship class.
        
        Args:
            fk_table: FK table
            fk_column: FK column
            pk_table: PK table
            pk_column: PK column
            semantic_similarity: ANN similarity score
            containment_ratio: FK ⊆ PK ratio
            type_compatibility: Type compatibility score
            confidence: Overall confidence
            fk_description: FK ColumnDescription
            pk_description: PK ColumnDescription
            semantic_cluster_id: Cluster ID (if any)
            suppression_warnings: Suppression warnings
        
        Returns:
            AdjudicatedRelationship
        """
        # Determine relationship class
        relationship_class, reasoning = self._classify_relationship(
            semantic_similarity=semantic_similarity,
            containment_ratio=containment_ratio,
            type_compatibility=type_compatibility,
            confidence=confidence,
            fk_description=fk_description,
            pk_description=pk_description,
            suppression_warnings=suppression_warnings or [],
        )
        
        return AdjudicatedRelationship(
            fk_table=fk_table,
            fk_column=fk_column,
            pk_table=pk_table,
            pk_column=pk_column,
            relationship_class=relationship_class,
            confidence=confidence,
            semantic_similarity=semantic_similarity,
            containment_ratio=containment_ratio,
            type_compatibility=type_compatibility,
            adjudication_reasoning=reasoning,
            semantic_cluster_id=semantic_cluster_id,
            suppression_warnings=suppression_warnings,
        )
    
    def _classify_relationship(
        self,
        semantic_similarity: float,
        containment_ratio: float,
        type_compatibility: float,
        confidence: float,
        fk_description: ColumnDescription,
        pk_description: ColumnDescription,
        suppression_warnings: List[str],
    ) -> Tuple[RelationshipClass, List[str]]:
        """
        Classify relationship and generate reasoning.
        
        Returns:
            (RelationshipClass, reasoning)
        """
        reasoning = []
        
        # RULE 1: Strong containment + good semantics → TRUE_FK
        if (containment_ratio >= 0.95 and
            semantic_similarity >= self.true_fk_semantic_threshold):
            reasoning.append(f"Perfect containment ({containment_ratio:.2f})")
            reasoning.append(f"Strong semantic alignment ({semantic_similarity:.2f})")
            reasoning.append("Validated as TRUE foreign key relationship")
            return RelationshipClass.TRUE_FK, reasoning
        
        # RULE 2: Good containment + adequate semantics → TRUE_FK
        if (containment_ratio >= self.true_fk_containment_threshold and
            semantic_similarity >= self.true_fk_semantic_threshold and
            type_compatibility >= 0.5):
            reasoning.append(f"Strong containment ({containment_ratio:.2f})")
            reasoning.append(f"Adequate semantic similarity ({semantic_similarity:.2f})")
            reasoning.append(f"Type compatible ({type_compatibility:.2f})")
            reasoning.append("Validated as TRUE foreign key relationship")
            return RelationshipClass.TRUE_FK, reasoning
        
        # RULE 3: Weak containment + high semantics → SEMANTICALLY_RELATED
        if (containment_ratio < 0.50 and
            semantic_similarity >= self.semantic_related_threshold):
            reasoning.append(f"High semantic similarity ({semantic_similarity:.2f})")
            reasoning.append(f"Low containment ({containment_ratio:.2f})")
            reasoning.append("Semantically related but NOT a foreign key")
            reasoning.append("May be: synonyms, shared domain, or parallel concepts")
            return RelationshipClass.SEMANTICALLY_RELATED, reasoning
        
        # RULE 4: Shared entity reference + weak containment → SHARED_ENTITY_DOMAIN
        fk_entity = SemanticClusteringEngine._get_entity_reference(fk_description)
        pk_entity = SemanticClusteringEngine._get_entity_reference(pk_description)
        if (fk_entity and
            pk_entity and
            fk_entity == pk_entity and
            containment_ratio < 0.70):
            reasoning.append(f"Both reference '{fk_entity}' entity")
            reasoning.append(f"Insufficient containment ({containment_ratio:.2f})")
            reasoning.append("Shared business entity domain, not direct FK")
            return RelationshipClass.SHARED_ENTITY_DOMAIN, reasoning
        
        # RULE 5: Suppression warnings → likely FALSE_POSITIVE
        if suppression_warnings:
            reasoning.append(f"Suppression warnings: {', '.join(suppression_warnings[:2])}")
            reasoning.append("Relationship suppressed due to invalid patterns")
            return RelationshipClass.FALSE_POSITIVE, reasoning
        
        # RULE 6: Low everything → FALSE_POSITIVE
        if (containment_ratio < 0.50 and
            semantic_similarity < 0.40 and
            confidence < 0.60):
            reasoning.append(f"Low containment ({containment_ratio:.2f})")
            reasoning.append(f"Low semantic similarity ({semantic_similarity:.2f})")
            reasoning.append(f"Low confidence ({confidence:.2f})")
            reasoning.append("Insufficient evidence for relationship")
            return RelationshipClass.FALSE_POSITIVE, reasoning
        
        # RULE 7: Moderate containment + moderate semantics → POSSIBLE_REFERENCE
        if (containment_ratio >= 0.50 and containment_ratio < self.true_fk_containment_threshold):
            reasoning.append(f"Moderate containment ({containment_ratio:.2f})")
            reasoning.append(f"Semantic similarity ({semantic_similarity:.2f})")
            reasoning.append("Possible reference - requires manual review")
            return RelationshipClass.POSSIBLE_REFERENCE, reasoning
        
        # DEFAULT: FALSE_POSITIVE
        reasoning.append("Insufficient evidence for validated relationship")
        return RelationshipClass.FALSE_POSITIVE, reasoning


# Convenience functions

def cluster_columns_by_semantics(
    descriptions: List[ColumnDescription],
    embeddings: np.ndarray,
    eps: float = 0.5,
) -> Dict[int, SemanticCluster]:
    """
    Convenience function to cluster columns.
    
    Args:
        descriptions: Column descriptions
        embeddings: Embedding matrix
        eps: DBSCAN epsilon
    
    Returns:
        Dict of SemanticCluster objects
    """
    engine = SemanticClusteringEngine(eps=eps)
    return engine.cluster_columns(descriptions, embeddings)


def adjudicate_relationship(
    fk_table: str,
    fk_column: str,
    pk_table: str,
    pk_column: str,
    semantic_similarity: float,
    containment_ratio: float,
    type_compatibility: float,
    confidence: float,
    fk_description: ColumnDescription,
    pk_description: ColumnDescription,
) -> AdjudicatedRelationship:
    """
    Convenience function to adjudicate relationship.
    
    Args:
        See SemanticRelationshipAdjudicator.adjudicate
    
    Returns:
        AdjudicatedRelationship
    """
    adjudicator = SemanticRelationshipAdjudicator()
    return adjudicator.adjudicate(
        fk_table, fk_column, pk_table, pk_column,
        semantic_similarity, containment_ratio, type_compatibility,
        confidence, fk_description, pk_description,
    )
