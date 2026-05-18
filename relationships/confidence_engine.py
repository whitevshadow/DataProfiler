"""
Confidence Scoring Engine

Fuses multiple evidence signals into a unified FK relationship confidence score.

Evidence Signals:
    1. Containment Ratio (MOST IMPORTANT) - 0.45 weight
    2. Overlap Ratio - 0.25 weight
    3. Type Compatibility - 0.15 weight
    4. PK Confidence - 0.10 weight
    5. Naming Similarity - 0.05 weight

Confidence Thresholds:
    >= 0.95: Extremely confident FK relationship
    >= 0.85: Strong FK relationship
    >= 0.75: Acceptable FK relationship
    >= 0.60: Weak FK relationship (flag for review)
    < 0.60: Rejected FK relationship

Design Principle:
    Containment ratio MUST dominate the score.
    Even with perfect naming, types, and PK confidence,
    low containment ratio should result in rejection.
"""

from typing import Dict, Any, Optional
from relationships.relationship_models import RelationshipEvidence


class ConfidenceEngine:
    """
    Computes FK relationship confidence by fusing multiple evidence signals.
    
    Uses weighted scoring where containment ratio dominates all other signals.
    
    Enhanced with semantic similarity support (optional).
    """
    
    def __init__(
        self,
        containment_weight: float = 0.45,
        semantic_similarity_weight: float = 0.20,
        type_compatibility_weight: float = 0.15,
        pk_confidence_weight: float = 0.10,
        naming_similarity_weight: float = 0.10,
        use_semantic_signals: bool = False,
    ):
        """
        Initialize confidence engine with signal weights.
        
        Args:
            containment_weight: Weight for FK ⊆ PK containment ratio (DOMINANT)
            semantic_similarity_weight: Weight for ANN semantic similarity
            type_compatibility_weight: Weight for type compatibility
            pk_confidence_weight: Weight for PK candidate confidence
            naming_similarity_weight: Weight for column naming similarity
            use_semantic_signals: Whether to use semantic similarity in scoring
        """
        self.use_semantic_signals = use_semantic_signals
        
        if use_semantic_signals:
            # Semantic-enhanced weighting (containment still dominant)
            self.weights = {
                "containment": containment_weight,
                "semantic_similarity": semantic_similarity_weight,
                "type_compatibility": type_compatibility_weight,
                "pk_confidence": pk_confidence_weight,
                "naming_similarity": naming_similarity_weight,
            }
        else:
            # Traditional weighting (backward compatible)
            self.weights = {
                "containment": containment_weight,
                "overlap": 0.25,  # Used instead of semantic_similarity
                "type_compatibility": type_compatibility_weight,
                "pk_confidence": pk_confidence_weight,
                "naming_similarity": naming_similarity_weight,
            }
    
    def compute_confidence(
        self,
        containment_ratio: float,
        overlap_ratio: float,
        type_compatibility_score: float,
        pk_confidence: float,
        naming_similarity: float,
        null_ratio_fk: float = 0.0,
        cardinality_ratio: Optional[float] = None,
        semantic_similarity: Optional[float] = None,
    ) -> float:
        """
        Compute FK relationship confidence score.
        
        Args:
            containment_ratio: |FK ∩ PK| / |FK| (0.0-1.0) - DOMINANT
            overlap_ratio: |FK ∩ PK| / |PK| (0.0-1.0)
            type_compatibility_score: Type compatibility (0.0-1.0)
            pk_confidence: PK candidate confidence (0.0-1.0)
            naming_similarity: Column naming similarity (0.0-1.0)
            null_ratio_fk: Ratio of nulls in FK column (0.0-1.0)
            cardinality_ratio: |FK distinct| / |PK distinct| (optional)
            semantic_similarity: ANN semantic similarity (0.0-1.0, optional)
        
        Returns:
            Confidence score from 0.0 to 1.0
        """
        # Weighted sum of evidence signals
        if self.use_semantic_signals and semantic_similarity is not None:
            # Semantic-enhanced scoring
            confidence = (
                containment_ratio * self.weights["containment"] +
                semantic_similarity * self.weights["semantic_similarity"] +
                type_compatibility_score * self.weights["type_compatibility"] +
                pk_confidence * self.weights["pk_confidence"] +
                naming_similarity * self.weights["naming_similarity"]
            )
        else:
            # Traditional scoring (backward compatible)
            confidence = (
                containment_ratio * self.weights["containment"] +
                overlap_ratio * self.weights["overlap"] +
                type_compatibility_score * self.weights["type_compatibility"] +
                pk_confidence * self.weights["pk_confidence"] +
                naming_similarity * self.weights["naming_similarity"]
            )
        
        # Apply penalties
        confidence = self._apply_penalties(
            confidence,
            containment_ratio,
            null_ratio_fk,
            cardinality_ratio,
        )
        
        # Clamp to [0.0, 1.0]
        return max(0.0, min(1.0, confidence))
    
    def _apply_penalties(
        self,
        base_confidence: float,
        containment_ratio: float,
        null_ratio_fk: float,
        cardinality_ratio: Optional[float],
    ) -> float:
        """
        Apply penalties for suspicious patterns.
        
        Args:
            base_confidence: Base confidence before penalties
            containment_ratio: FK containment ratio
            null_ratio_fk: Null ratio in FK column
            cardinality_ratio: FK distinct / PK distinct
        
        Returns:
            Adjusted confidence after penalties
        """
        confidence = base_confidence
        
        # CRITICAL: Containment ratio dominates
        # If containment < 0.70, cap confidence at 0.60
        if containment_ratio < 0.70:
            confidence = min(confidence, 0.60)
        
        # Penalty for high null ratio in FK
        # FKs with >50% nulls are suspicious
        if null_ratio_fk > 0.5:
            penalty = (null_ratio_fk - 0.5) * 0.20
            confidence -= penalty
        
        # Penalty for suspicious cardinality ratio
        # FK distinct should not exceed PK distinct
        if cardinality_ratio is not None and cardinality_ratio > 1.0:
            # This indicates FK has more distinct values than PK (impossible for valid FK)
            penalty = min(0.30, (cardinality_ratio - 1.0) * 0.50)
            confidence -= penalty
        
        return confidence
    
    def build_evidence(
        self,
        containment_ratio: float,
        overlap_ratio: float,
        type_match: bool,
        type_compatibility_score: float,
        pk_confidence: float,
        naming_similarity: float,
        cardinality_ratio: float,
        null_ratio_fk: float,
        is_approximate: bool = False,
        sample_size_fk: Optional[int] = None,
        sample_size_pk: Optional[int] = None,
        bloom_filter_passed: bool = True,
        orphan_count: Optional[int] = None,
        semantic_similarity: Optional[float] = None,
    ) -> RelationshipEvidence:
        """
        Build a complete RelationshipEvidence object.
        
        Args:
            containment_ratio: FK containment in PK
            overlap_ratio: Overlap between FK and PK
            type_match: Whether types exactly match
            type_compatibility_score: Type compatibility score
            pk_confidence: PK candidate confidence
            naming_similarity: Column name similarity
            cardinality_ratio: FK distinct / PK distinct
            null_ratio_fk: Null ratio in FK column
            is_approximate: Whether validation used sampling
            sample_size_fk: FK sample size (if applicable)
            sample_size_pk: PK sample size (if applicable)
            bloom_filter_passed: Whether Bloom filter test passed
            orphan_count: Count of orphaned FK values
            semantic_similarity: ANN semantic similarity (if used)
        
        Returns:
            RelationshipEvidence instance
        """
        return RelationshipEvidence(
            containment_ratio=containment_ratio,
            overlap_ratio=overlap_ratio,
            type_match=type_match,
            type_compatibility_score=type_compatibility_score,
            pk_confidence=pk_confidence,
            naming_similarity=naming_similarity,
            cardinality_ratio=cardinality_ratio,
            null_ratio_fk=null_ratio_fk,
            is_approximate=is_approximate,
            sample_size_fk=sample_size_fk,
            sample_size_pk=sample_size_pk,
            bloom_filter_passed=bloom_filter_passed,
            orphan_count=orphan_count,
            semantic_similarity=semantic_similarity,
        )
    
    def classify_confidence_level(self, confidence: float) -> str:
        """
        Classify confidence score into human-readable level.
        
        Args:
            confidence: Confidence score (0.0-1.0)
        
        Returns:
            Classification string
        """
        if confidence >= 0.95:
            return "extremely_confident"
        elif confidence >= 0.85:
            return "strong"
        elif confidence >= 0.75:
            return "acceptable"
        elif confidence >= 0.60:
            return "weak"
        else:
            return "rejected"
    
    def should_accept(
        self,
        confidence: float,
        acceptance_threshold: float = 0.75,
    ) -> bool:
        """
        Determine whether to accept FK relationship.
        
        Args:
            confidence: Computed confidence score
            acceptance_threshold: Minimum confidence for acceptance
        
        Returns:
            True if relationship should be accepted, False otherwise
        """
        return confidence >= acceptance_threshold
    
    def explain_confidence(
        self,
        containment_ratio: float,
        overlap_ratio: float,
        type_compatibility_score: float,
        pk_confidence: float,
        naming_similarity: float,
        semantic_similarity: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Generate explainable breakdown of confidence score.
        
        Args:
            containment_ratio: FK containment in PK
            overlap_ratio: Overlap ratio
            type_compatibility_score: Type compatibility
            pk_confidence: PK confidence
            naming_similarity: Naming similarity
            semantic_similarity: Semantic similarity (optional)
        
        Returns:
            Dict with per-signal contributions
        """
        contributions = {
            "containment_contribution": round(
                containment_ratio * self.weights["containment"], 4
            ),
        }
        
        if self.use_semantic_signals and semantic_similarity is not None:
            contributions["semantic_similarity_contribution"] = round(
                semantic_similarity * self.weights["semantic_similarity"], 4
            )
        else:
            contributions["overlap_contribution"] = round(
                overlap_ratio * self.weights["overlap"], 4
            )
        
        contributions["type_contribution"] = round(
            type_compatibility_score * self.weights["type_compatibility"], 4
        )
        contributions["pk_confidence_contribution"] = round(
            pk_confidence * self.weights["pk_confidence"], 4
        )
        contributions["naming_contribution"] = round(
            naming_similarity * self.weights["naming_similarity"], 4
        )
        
        total = sum(contributions.values())
        contributions["total_confidence"] = round(total, 4)
        
        # Identify dominant signal (exclude total_confidence from consideration)
        signal_contributions = {
            k: v for k, v in contributions.items()
            if k != "total_confidence"
        }
        
        if signal_contributions and max(signal_contributions.values()) > 0:
            max_contribution = max(signal_contributions.values())
            dominant_signal = [
                k for k, v in signal_contributions.items()
                if v == max_contribution
            ][0]
        else:
            dominant_signal = "none"
        
        contributions["dominant_signal"] = dominant_signal
        
        return contributions


# Singleton instance
_confidence_engine = ConfidenceEngine()


def compute_fk_confidence(
    containment_ratio: float,
    overlap_ratio: float,
    type_compatibility_score: float,
    pk_confidence: float,
    naming_similarity: float,
    null_ratio_fk: float = 0.0,
    cardinality_ratio: Optional[float] = None,
    semantic_similarity: Optional[float] = None,
    use_semantic_signals: bool = False,
) -> float:
    """
    Convenience function to compute FK confidence.
    
    Args:
        containment_ratio: FK containment in PK
        overlap_ratio: Overlap ratio
        type_compatibility_score: Type compatibility
        pk_confidence: PK confidence
        naming_similarity: Naming similarity
        null_ratio_fk: FK null ratio
        cardinality_ratio: FK distinct / PK distinct
        semantic_similarity: ANN semantic similarity (optional)
        use_semantic_signals: Whether to use semantic similarity
    
    Returns:
        Confidence score from 0.0 to 1.0
    """
    engine = ConfidenceEngine(use_semantic_signals=use_semantic_signals)
    return engine.compute_confidence(
        containment_ratio=containment_ratio,
        overlap_ratio=overlap_ratio,
        type_compatibility_score=type_compatibility_score,
        pk_confidence=pk_confidence,
        naming_similarity=naming_similarity,
        null_ratio_fk=null_ratio_fk,
        cardinality_ratio=cardinality_ratio,
        semantic_similarity=semantic_similarity,
    )
