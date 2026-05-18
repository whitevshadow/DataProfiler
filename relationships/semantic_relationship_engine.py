"""
Semantic Relationship Engine

Integrates semantic intelligence with deterministic validation for FK detection.

Architecture:
    1. Generate semantic column descriptions
    2. Generate embeddings for ANN retrieval
    3. Retrieve semantic candidates (high recall)
    4. Cluster columns by semantic similarity
    5. Validate candidates deterministically (containment)
    6. Score with combined semantic + deterministic evidence
    7. Adjudicate relationship classification

Core Principles:
    - ANN similarity = CANDIDATE GENERATION only
    - Deterministic validation = AUTHORITATIVE TRUTH
    - Containment dominates semantic similarity (0.45 vs 0.20 weight)
    - Explainable adjudication (TRUE_FK vs SEMANTICALLY_RELATED)
"""

import time
import uuid
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from relationships.semantic_column_descriptor import (
    SemanticColumnDescriptor,
    ColumnDescription,
)
from relationships.semantic_embedding_engine import (
    SemanticCandidateManager,
    SemanticCandidate,
)
from relationships.semantic_clustering import (
    SemanticClusteringEngine,
    SemanticRelationshipAdjudicator,
    RelationshipClass,
    AdjudicatedRelationship,
)
from relationships.containment_validator import ContainmentValidator
from relationships.confidence_engine import ConfidenceEngine
from relationships.type_compatibility import check_type_compatibility
from relationships.relationship_models import RelationshipReport


class SemanticRelationshipEngine:
    """
    Semantic-enhanced FK relationship detection engine.
    
    Combines:
    - Semantic column descriptions
    - ANN-based candidate retrieval
    - DBSCAN clustering
    - Deterministic containment validation
    - Weighted confidence scoring
    - Relationship adjudication
    """
    
    def __init__(
        self,
        use_semantic_candidates: bool = True,
        use_clustering: bool = True,
        min_semantic_similarity: float = 0.30,
        acceptance_threshold: float = 0.75,
    ):
        """
        Initialize semantic relationship engine.
        
        Args:
            use_semantic_candidates: Use ANN for candidate retrieval
            use_clustering: Use DBSCAN for semantic clustering
            min_semantic_similarity: Min ANN similarity threshold
            acceptance_threshold: Min confidence for acceptance
        """
        self.use_semantic_candidates = use_semantic_candidates
        self.use_clustering = use_clustering
        self.min_semantic_similarity = min_semantic_similarity
        self.acceptance_threshold = acceptance_threshold
        
        # Initialize components
        self.descriptor = SemanticColumnDescriptor()
        self.candidate_manager = SemanticCandidateManager(
            min_similarity=min_semantic_similarity
        )
        self.clustering_engine = SemanticClusteringEngine()
        self.containment_validator = ContainmentValidator()
        self.confidence_engine = ConfidenceEngine(use_semantic_signals=True)
        self.adjudicator = SemanticRelationshipAdjudicator()
    
    def detect_relationships_with_semantics(
        self,
        table_profiles: Dict[str, Dict[str, Any]],
        pk_candidates: Dict[str, List[Dict[str, Any]]],
        canonical_tables: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Tuple[RelationshipReport, List[AdjudicatedRelationship]]:
        """
        Detect FK relationships using semantic intelligence + deterministic validation.
        
        Args:
            table_profiles: Table profiles with column statistics
            pk_candidates: PK candidates per table
            canonical_tables: Canonical table data with sample values
        
        Returns:
            (RelationshipReport, List[AdjudicatedRelationship])
        """
        start_time = time.time()
        
        print("\n" + "=" * 80)
        print("SEMANTIC RELATIONSHIP DETECTION ENGINE")
        print("=" * 80)
        
        # STAGE 1: Generate semantic column descriptions
        print("\n[STAGE 1] Generating semantic column descriptions...")
        all_descriptions = self._generate_descriptions(
            table_profiles, pk_candidates
        )
        print(f"Generated {len(all_descriptions)} column descriptions")
        
        # STAGE 2: Generate semantic candidates via ANN
        print("\n[STAGE 2] Retrieving semantic candidates via ANN...")
        semantic_candidates = []
        if self.use_semantic_candidates:
            pk_candidate_columns = self._extract_pk_columns(pk_candidates)
            semantic_candidates = self.candidate_manager.generate_semantic_candidates(
                all_descriptions, pk_candidate_columns
            )
            print(f"Retrieved {len(semantic_candidates)} semantic candidates")
        else:
            print("Semantic candidate retrieval disabled")
        
        # STAGE 3: Cluster columns by semantics
        print("\n[STAGE 3] Clustering columns by semantic similarity...")
        clusters = {}
        if self.use_clustering and len(all_descriptions) > 2:
            # Get embeddings from candidate manager
            embeddings = self.candidate_manager.embedding_engine.fit_and_transform(
                all_descriptions
            )
            clusters = self.clustering_engine.cluster_columns(
                all_descriptions, embeddings
            )
            print(f"Found {len(clusters)} semantic clusters")
            for cluster_id, cluster in clusters.items():
                print(f"  Cluster {cluster_id}: {cluster.cluster_label} ({len(cluster.columns)} columns)")
        else:
            print("Clustering disabled or insufficient columns")
        
        # STAGE 4: Validate candidates deterministically
        print("\n[STAGE 4] Validating candidates with deterministic containment...")
        adjudicated_relationships = []
        
        for candidate in semantic_candidates:
            adjudicated = self._validate_and_adjudicate_candidate(
                candidate=candidate,
                all_descriptions=all_descriptions,
                canonical_tables=canonical_tables,
                pk_candidates=pk_candidates,
                clusters=clusters,
            )
            
            if adjudicated:
                adjudicated_relationships.append(adjudicated)
        
        print(f"Validated {len(adjudicated_relationships)} relationships")
        
        # STAGE 5: Build relationship report
        print("\n[STAGE 5] Generating relationship report...")
        report = self._build_report(
            adjudicated_relationships,
            table_profiles,
            semantic_candidates,
            start_time,
        )
        
        print("\n" + "=" * 80)
        print(f"DETECTION COMPLETE")
        print(f"  TRUE_FK: {sum(1 for r in adjudicated_relationships if r.relationship_class == RelationshipClass.TRUE_FK)}")
        print(f"  SEMANTICALLY_RELATED: {sum(1 for r in adjudicated_relationships if r.relationship_class == RelationshipClass.SEMANTICALLY_RELATED)}")
        print(f"  POSSIBLE_REFERENCE: {sum(1 for r in adjudicated_relationships if r.relationship_class == RelationshipClass.POSSIBLE_REFERENCE)}")
        print(f"  FALSE_POSITIVE: {sum(1 for r in adjudicated_relationships if r.relationship_class == RelationshipClass.FALSE_POSITIVE)}")
        print(f"  Time: {time.time() - start_time:.3f}s")
        print("=" * 80)
        
        return report, adjudicated_relationships
    
    def _generate_descriptions(
        self,
        table_profiles: Dict[str, Dict[str, Any]],
        pk_candidates: Dict[str, List[Dict[str, Any]]],
    ) -> List[ColumnDescription]:
        """Generate semantic descriptions for all columns."""
        
        descriptions = []
        
        for table_name, profile in table_profiles.items():
            table_pk_candidates = pk_candidates.get(table_name, [])
            pk_column_names = {pk["column"] for pk in table_pk_candidates}
            
            for col_profile in profile.get("columns", []):
                col_name = col_profile["column_name"]
                is_pk = col_name in pk_column_names
                
                desc = self.descriptor.generate_description(
                    column_name=col_name,
                    table_name=table_name,
                    column_profile=col_profile,
                    is_pk_candidate=is_pk,
                )
                descriptions.append(desc)
        
        return descriptions
    
    def _extract_pk_columns(
        self,
        pk_candidates: Dict[str, List[Dict[str, Any]]],
    ) -> List[Tuple[str, str]]:
        """Extract (table, column) pairs for PK candidates."""
        
        pk_columns = []
        for table, candidates in pk_candidates.items():
            for candidate in candidates:
                if candidate.get("accepted", True):
                    pk_columns.append((table, candidate["column"]))
        
        return pk_columns
    
    def _validate_and_adjudicate_candidate(
        self,
        candidate: SemanticCandidate,
        all_descriptions: List[ColumnDescription],
        canonical_tables: Optional[Dict[str, Dict[str, Any]]],
        pk_candidates: Dict[str, List[Dict[str, Any]]],
        clusters: Dict[int, Any],
    ) -> Optional[AdjudicatedRelationship]:
        """Validate a semantic candidate and adjudicate relationship class."""
        
        # Get column descriptions
        fk_desc = next(
            (d for d in all_descriptions
             if d.table_name == candidate.fk_table and d.column_name == candidate.fk_column),
            None
        )
        pk_desc = next(
            (d for d in all_descriptions
             if d.table_name == candidate.pk_table and d.column_name == candidate.pk_column),
            None
        )
        
        if not fk_desc or not pk_desc:
            return None
        
        # Get sample values for containment validation
        fk_values = self._get_sample_values(
            candidate.fk_table, candidate.fk_column, canonical_tables
        )
        pk_values = self._get_sample_values(
            candidate.pk_table, candidate.pk_column, canonical_tables
        )
        
        if not fk_values or not pk_values:
            # No sample values - can't validate containment
            return None
        
        # Perform containment validation (AUTHORITATIVE)
        containment = self.containment_validator.validate_containment_full(
            fk_values=fk_values,
            pk_values=pk_values,
        )
        
        # Get type compatibility
        type_result = check_type_compatibility(
            fk_desc.column_name, pk_desc.column_name
        )
        
        # Get PK confidence
        pk_confidence = 0.95  # Default
        for pk in pk_candidates.get(candidate.pk_table, []):
            if pk["column"] == candidate.pk_column:
                pk_confidence = pk.get("confidence", 0.95)
                break
        
        # Compute confidence with semantic signal
        confidence = self.confidence_engine.compute_confidence(
            containment_ratio=containment.containment_ratio,
            overlap_ratio=containment.containment_ratio,  # Simplified
            type_compatibility_score=type_result.compatibility_score,
            pk_confidence=pk_confidence,
            naming_similarity=0.5,  # Placeholder
            semantic_similarity=candidate.semantic_similarity,
        )
        
        # Adjudicate relationship class
        adjudicated = self.adjudicator.adjudicate(
            fk_table=candidate.fk_table,
            fk_column=candidate.fk_column,
            pk_table=candidate.pk_table,
            pk_column=candidate.pk_column,
            semantic_similarity=candidate.semantic_similarity,
            containment_ratio=containment.containment_ratio,
            type_compatibility=type_result.compatibility_score,
            confidence=confidence,
            fk_description=fk_desc,
            pk_description=pk_desc,
        )
        
        return adjudicated
    
    def _get_sample_values(
        self,
        table: str,
        column: str,
        canonical_tables: Optional[Dict[str, Dict[str, Any]]],
    ) -> Optional[List[Any]]:
        """Extract sample values for a column."""
        if not canonical_tables or table not in canonical_tables:
            return None
        
        canonical = canonical_tables[table]
        columns = canonical.get("columns", [])
        
        for col in columns:
            if col.get("normalized_name") == column or col.get("original_name") == column:
                return col.get("sample_values", [])
        
        return None
    
    def _build_report(
        self,
        adjudicated_relationships: List[AdjudicatedRelationship],
        table_profiles: Dict[str, Dict[str, Any]],
        semantic_candidates: List[SemanticCandidate],
        start_time: float,
    ) -> RelationshipReport:
        """Build RelationshipReport from adjudicated relationships."""
        
        # Count by class
        true_fk_count = sum(
            1 for r in adjudicated_relationships
            if r.relationship_class == RelationshipClass.TRUE_FK
        )
        
        report_id = f"semantic_rel_{uuid.uuid4().hex[:12]}"
        elapsed = time.time() - start_time
        
        report = RelationshipReport(
            relationship_report_id=report_id,
            schema_version="v1.0.0_semantic",
            artifact_type="SemanticRelationshipReport",
            generation_timestamp=datetime.utcnow().isoformat() + "Z",
            relationships=[],  # Convert adjudicated to Relationship objects if needed
            total_relationships_detected=len(adjudicated_relationships),
            total_relationships_accepted=true_fk_count,
            total_relationships_rejected=len(adjudicated_relationships) - true_fk_count,
            total_tables_analyzed=len(table_profiles),
            total_candidate_pairs_evaluated=len(semantic_candidates),
            execution_engine="semantic_python",
            execution_time_seconds=elapsed,
        )
        
        return report


# Convenience function

def detect_relationships_with_semantics(
    table_profiles: Dict[str, Dict[str, Any]],
    pk_candidates: Dict[str, List[Dict[str, Any]]],
    canonical_tables: Optional[Dict[str, Dict[str, Any]]] = None,
    min_semantic_similarity: float = 0.30,
    acceptance_threshold: float = 0.75,
) -> Tuple[RelationshipReport, List[AdjudicatedRelationship]]:
    """
    Convenience function for semantic relationship detection.
    
    Args:
        table_profiles: Table profiles
        pk_candidates: PK candidates
        canonical_tables: Canonical tables with sample values
        min_semantic_similarity: Min ANN similarity
        acceptance_threshold: Min confidence threshold
    
    Returns:
        (RelationshipReport, List[AdjudicatedRelationship])
    """
    engine = SemanticRelationshipEngine(
        min_semantic_similarity=min_semantic_similarity,
        acceptance_threshold=acceptance_threshold,
    )
    return engine.detect_relationships_with_semantics(
        table_profiles, pk_candidates, canonical_tables
    )
