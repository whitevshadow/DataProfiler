"""
Relationship Engine

Main orchestrator for FK relationship detection.

Pipeline:
    1. Load table profiles and PK candidates
    2. Generate candidate FK->PK pairs (avoid O(n²))
    3. Filter by type compatibility
    4. Build Bloom filters for PK sets
    5. Prune candidates using Bloom filters
    6. Validate containment (authoritative)
    7. Compute confidence scores
    8. Apply suppression rules
    9. Generate RelationshipReport

Execution Modes:
    - Full Scan: Exact validation (small datasets)
    - Sampled: Approximate validation (large datasets)
    - Hybrid: Bloom filter + selective full scan

Design Principles:
    - Deterministic-first (containment is truth)
    - Scalable to TB-scale data
    - Explainable relationship evidence
    - Reproducible with seeds
"""

import time
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime

from relationships.relationship_models import (
    Relationship,
    RelationshipReport,
    RelationshipType,
    RelationshipEvidence,
    RelationshipValidation,
    RelationshipExecutionMetadata,
    ColumnReference,
    CandidatePair,
)
from relationships.candidate_pair_generator import CandidatePairGenerator
from relationships.type_compatibility import check_type_compatibility
from relationships.bloom_filter_engine import BloomFilterEngine
from relationships.containment_validator import ContainmentValidator
from relationships.confidence_engine import ConfidenceEngine
from relationships.suppression_rules import FKSuppressionEngine


class RelationshipEngine:
    """
    Main engine for detecting FK relationships.
    
    Orchestrates the full pipeline from candidate generation
    to validated relationships.
    """
    
    def __init__(
        self,
        acceptance_threshold: float = 0.75,
        use_bloom_filters: bool = True,
        validation_method: str = "full",  # "full", "sampled", "hybrid"
        deterministic_seed: Optional[int] = None,
    ):
        """
        Initialize relationship engine.
        
        Args:
            acceptance_threshold: Minimum confidence for accepting relationships
            use_bloom_filters: Enable Bloom filter pruning
            validation_method: "full", "sampled", or "hybrid"
            deterministic_seed: Random seed for reproducibility
        """
        self.acceptance_threshold = acceptance_threshold
        self.use_bloom_filters = use_bloom_filters
        self.validation_method = validation_method
        self.deterministic_seed = deterministic_seed
        
        # Initialize engines
        self.candidate_generator = CandidatePairGenerator()
        self.bloom_engine = BloomFilterEngine()
        self.containment_validator = ContainmentValidator()
        self.confidence_engine = ConfidenceEngine()
        self.suppression_engine = FKSuppressionEngine()
    
    def detect_relationships(
        self,
        table_profiles: Dict[str, Dict[str, Any]],
        pk_candidates: Dict[str, List[Dict[str, Any]]],
        canonical_tables: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> RelationshipReport:
        """
        Detect FK relationships across tables.
        
        Args:
            table_profiles: Dict mapping table_name -> table profile (with column stats)
            pk_candidates: Dict mapping table_name -> list of PK candidate dicts
            canonical_tables: Optional dict of CanonicalTable data for sample values
        
        Returns:
            RelationshipReport with detected relationships
        """
        start_time = time.time()
        
        # Generate report ID
        report_id = f"rel_{uuid.uuid4().hex[:12]}"
        
        # Step 1: Generate candidate pairs
        print(f"Generating candidate FK->PK pairs...")
        candidates = self.candidate_generator.generate_candidates(
            table_profiles=table_profiles,
            pk_candidates=pk_candidates,
        )
        print(f"Generated {len(candidates)} candidate pairs")
        
        # Step 2: Validate each candidate
        print(f"Validating candidates...")
        relationships = []
        
        for candidate in candidates:
            relationship = self._validate_candidate(
                candidate=candidate,
                table_profiles=table_profiles,
                canonical_tables=canonical_tables,
            )
            
            if relationship:
                relationships.append(relationship)
        
        # Step 3: Build relationship report
        elapsed = time.time() - start_time
        
        report = RelationshipReport(
            relationship_report_id=report_id,
            schema_version="v1.0.0",
            artifact_type="RelationshipReport",
            generation_timestamp=datetime.utcnow().isoformat() + "Z",
            relationships=relationships,
            total_relationships_detected=len(relationships),
            total_relationships_accepted=sum(1 for r in relationships if r.accepted),
            total_relationships_rejected=sum(1 for r in relationships if not r.accepted),
            total_tables_analyzed=len(table_profiles),
            total_candidate_pairs_evaluated=len(candidates),
            execution_engine="python",
            execution_time_seconds=elapsed,
            graph_node_count=len(table_profiles),
            graph_edge_count=sum(1 for r in relationships if r.accepted),
        )
        
        print(f"Detection complete: {report.total_relationships_accepted} relationships accepted")
        
        return report
    
    def _validate_candidate(
        self,
        candidate: CandidatePair,
        table_profiles: Dict[str, Dict[str, Any]],
        canonical_tables: Optional[Dict[str, Dict[str, Any]]],
    ) -> Optional[Relationship]:
        """
        Validate a single FK candidate.
        
        Args:
            candidate: CandidatePair to validate
            table_profiles: Table profiles
            canonical_tables: Canonical table data (for sample values)
        
        Returns:
            Relationship if valid, None if suppressed/rejected
        """
        # Get column profiles
        fk_profile = self._get_column_profile(
            candidate.fk_table, candidate.fk_column, table_profiles
        )
        pk_profile = self._get_column_profile(
            candidate.pk_table, candidate.pk_column, table_profiles
        )
        
        if not fk_profile or not pk_profile:
            return None
        
        # Step 1: Apply suppression rules
        suppression_result = self.suppression_engine.evaluate(
            fk_column=candidate.fk_column,
            fk_profile=fk_profile,
            pk_column=candidate.pk_column,
            pk_profile=pk_profile,
        )
        
        if suppression_result.should_suppress:
            # Create rejected relationship
            return self._create_rejected_relationship(
                candidate, suppression_result.reasons
            )
        
        # Step 2: Check type compatibility
        type_result = check_type_compatibility(candidate.fk_type, candidate.pk_type)
        if not type_result.compatible:
            return None
        
        # Step 3: Get sample values for validation
        fk_values = self._get_sample_values(
            candidate.fk_table, candidate.fk_column, canonical_tables
        )
        pk_values = self._get_sample_values(
            candidate.pk_table, candidate.pk_column, canonical_tables
        )
        
        if not fk_values or not pk_values:
            return None
        
        # Step 4: Bloom filter pruning (optional)
        bloom_passed = True
        if self.use_bloom_filters and len(pk_values) > 1000:
            bloom = self.bloom_engine.build_bloom_filter(pk_values)
            bloom_passed = not self.bloom_engine.should_reject_candidate(
                fk_sample=fk_values[:1000],  # Use sample for Bloom test
                bloom=bloom,
                rejection_threshold=0.10,
            )
            
            if not bloom_passed:
                return None  # Reject early
        
        # Step 5: Containment validation (AUTHORITATIVE)
        containment = self.containment_validator.validate_containment_full(
            fk_values=fk_values,
            pk_values=pk_values,
        )
        
        # Step 6: Compute confidence
        null_count = fk_profile.get("null_count", 0)
        total_count = fk_profile.get("row_count", len(fk_values))
        null_ratio = null_count / total_count if total_count > 0 else 0.0
        
        cardinality_ratio = 0.0
        if containment.distinct_pk_values > 0:
            cardinality_ratio = containment.distinct_fk_values / containment.distinct_pk_values
        
        overlap_ratio = containment.containment_ratio  # Simplified
        
        confidence = self.confidence_engine.compute_confidence(
            containment_ratio=containment.containment_ratio,
            overlap_ratio=overlap_ratio,
            type_compatibility_score=type_result.compatibility_score,
            pk_confidence=candidate.pk_confidence,
            naming_similarity=candidate.naming_similarity,
            null_ratio_fk=null_ratio,
            cardinality_ratio=cardinality_ratio,
        )
        
        # Apply suppression penalty
        confidence -= suppression_result.confidence_penalty
        confidence = max(0.0, confidence)
        
        # Step 7: Acceptance decision
        accepted = (
            confidence >= self.acceptance_threshold and
            containment.contained
        )
        
        # Step 8: Build relationship object
        relationship = self._create_relationship(
            candidate=candidate,
            containment=containment,
            confidence=confidence,
            accepted=accepted,
            type_result=type_result,
            null_ratio=null_ratio,
            cardinality_ratio=cardinality_ratio,
            bloom_passed=bloom_passed,
            suppression_reasons=suppression_result.reasons,
        )
        
        return relationship
    
    def _get_column_profile(
        self,
        table: str,
        column: str,
        table_profiles: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Get column profile from table profiles."""
        table_profile = table_profiles.get(table)
        if not table_profile:
            return None
        
        columns = table_profile.get("columns", [])
        for col in columns:
            if col.get("column_name") == column:
                return col
        
        return None
    
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
    
    def _create_relationship(
        self,
        candidate: CandidatePair,
        containment: Any,
        confidence: float,
        accepted: bool,
        type_result: Any,
        null_ratio: float,
        cardinality_ratio: float,
        bloom_passed: bool,
        suppression_reasons: List[str],
    ) -> Relationship:
        """Create a Relationship object from validation results."""
        
        # Build evidence
        evidence = RelationshipEvidence(
            containment_ratio=containment.containment_ratio,
            overlap_ratio=containment.containment_ratio,  # Simplified
            type_match=(candidate.fk_type == candidate.pk_type),
            type_compatibility_score=type_result.compatibility_score,
            pk_confidence=candidate.pk_confidence,
            naming_similarity=candidate.naming_similarity,
            cardinality_ratio=cardinality_ratio,
            null_ratio_fk=null_ratio,
            is_approximate=containment.is_approximate,
            bloom_filter_passed=bloom_passed,
            orphan_count=containment.orphan_count,
        )
        
        # Build validation
        validation = RelationshipValidation(
            containment_validated=containment.contained,
            orphan_count=containment.orphan_count,
            orphan_ratio=containment.orphan_ratio,
            referential_integrity_score=1.0 - containment.orphan_ratio,
            validation_method=containment.validation_method,
            has_orphans=(containment.orphan_count > 0),
            is_weak_reference=(containment.containment_ratio < 0.95),
            is_ambiguous=False,
            warnings=[],
        )
        
        # Build execution metadata
        exec_metadata = RelationshipExecutionMetadata(
            engine="python",
            sampling_strategy="full_scan",
            is_approximate=containment.is_approximate,
            deterministic_seed=self.deterministic_seed,
            profiler_version="1.0.0",
            relationship_rule_version="1.0.0",
            detection_timestamp=datetime.utcnow().isoformat() + "Z",
        )
        
        # Determine relationship type
        rel_type = RelationshipType.FOREIGN_KEY
        if candidate.fk_table == candidate.pk_table:
            rel_type = RelationshipType.SELF_REFERENTIAL
        
        # Build column references
        from_col = ColumnReference(
            table=candidate.fk_table,
            column=candidate.fk_column,
            physical_type=candidate.fk_type,
        )
        to_col = ColumnReference(
            table=candidate.pk_table,
            column=candidate.pk_column,
            physical_type=candidate.pk_type,
        )
        
        # Create relationship
        rel_id = f"fk_{uuid.uuid4().hex[:8]}"
        
        return Relationship(
            relationship_id=rel_id,
            relationship_type=rel_type,
            from_column=from_col,
            to_column=to_col,
            confidence=confidence,
            accepted=accepted,
            evidence=evidence,
            validation=validation,
            execution_metadata=exec_metadata,
            composite_key=False,
            suppression_reasons=suppression_reasons,
        )
    
    def _create_rejected_relationship(
        self,
        candidate: CandidatePair,
        suppression_reasons: List[str],
    ) -> Relationship:
        """Create a rejected relationship object."""
        
        # Build minimal evidence
        evidence = RelationshipEvidence(
            containment_ratio=0.0,
            overlap_ratio=0.0,
            type_match=False,
            type_compatibility_score=0.0,
            pk_confidence=candidate.pk_confidence,
            naming_similarity=candidate.naming_similarity,
            cardinality_ratio=0.0,
            null_ratio_fk=0.0,
        )
        
        validation = RelationshipValidation(
            containment_validated=False,
            orphan_count=0,
            orphan_ratio=0.0,
            referential_integrity_score=0.0,
            validation_method="suppressed",
            warnings=suppression_reasons,
        )
        
        exec_metadata = RelationshipExecutionMetadata(
            engine="python",
            sampling_strategy="none",
            is_approximate=False,
            detection_timestamp=datetime.utcnow().isoformat() + "Z",
        )
        
        from_col = ColumnReference(
            table=candidate.fk_table,
            column=candidate.fk_column,
            physical_type=candidate.fk_type,
        )
        to_col = ColumnReference(
            table=candidate.pk_table,
            column=candidate.pk_column,
            physical_type=candidate.pk_type,
        )
        
        rel_id = f"fk_rejected_{uuid.uuid4().hex[:8]}"
        
        return Relationship(
            relationship_id=rel_id,
            relationship_type=RelationshipType.UNKNOWN,
            from_column=from_col,
            to_column=to_col,
            confidence=0.0,
            accepted=False,
            evidence=evidence,
            validation=validation,
            execution_metadata=exec_metadata,
            suppression_reasons=suppression_reasons,
        )


def detect_relationships(
    table_profiles: Dict[str, Dict[str, Any]],
    pk_candidates: Dict[str, List[Dict[str, Any]]],
    canonical_tables: Optional[Dict[str, Dict[str, Any]]] = None,
    acceptance_threshold: float = 0.75,
) -> RelationshipReport:
    """
    Convenience function to detect relationships.
    
    Args:
        table_profiles: Table profiles with column statistics
        pk_candidates: PK candidates per table
        canonical_tables: Optional canonical table data
        acceptance_threshold: Minimum confidence for acceptance
    
    Returns:
        RelationshipReport
    """
    engine = RelationshipEngine(acceptance_threshold=acceptance_threshold)
    return engine.detect_relationships(
        table_profiles=table_profiles,
        pk_candidates=pk_candidates,
        canonical_tables=canonical_tables,
    )
