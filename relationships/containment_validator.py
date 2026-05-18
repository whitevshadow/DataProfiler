"""
Containment Validator

THE AUTHORITATIVE TRUTH LAYER for FK relationship validation.

Core Principle:
    FK values ⊆ PK values
    
    For a valid FK relationship, ALL FK values (excluding nulls)
    MUST exist in the PK value set.

Validation Methods:
    1. Full Scan: Check every FK value against PK set (exact)
    2. Sampled: Check sample of FK values (approximate)
    3. Set-based: Use set intersection (memory efficient)
    4. DuckDB: SQL-based validation (scalable)

Containment Metrics:
    - Containment Ratio: |FK ∩ PK| / |FK non-null|
    - Orphan Count: |FK - PK|
    - Orphan Ratio: orphans / total FK values
    - Referential Integrity Score: 1.0 - orphan_ratio

Acceptance Criteria:
    - containment_ratio >= 0.95 → strong FK
    - containment_ratio >= 0.85 → acceptable FK
    - containment_ratio < 0.85 → weak/rejected FK
"""

from typing import List, Set, Dict, Any, Optional
from relationships.relationship_models import ContainmentResult


class ContainmentValidator:
    """
    Validates FK containment using deterministic set operations.
    
    This is the authoritative validation layer - Bloom filters,
    ANN, and semantic similarity are ONLY for candidate retrieval.
    """
    
    def __init__(
        self,
        strong_containment_threshold: float = 0.95,
        acceptable_containment_threshold: float = 0.85,
    ):
        """
        Initialize containment validator.
        
        Args:
            strong_containment_threshold: Threshold for strong FK (0.95 = 95% containment)
            acceptable_containment_threshold: Minimum threshold for valid FK
        """
        self.strong_threshold = strong_containment_threshold
        self.acceptable_threshold = acceptable_containment_threshold
    
    def validate_containment_full(
        self,
        fk_values: List[Any],
        pk_values: List[Any],
    ) -> ContainmentResult:
        """
        Validate containment using full scan (exact validation).
        
        Args:
            fk_values: All FK column values
            pk_values: All PK column values
        
        Returns:
            ContainmentResult with exact containment metrics
        """
        # Build PK set for O(1) lookup
        pk_set = set(pk_values)
        pk_set.discard(None)  # Remove nulls from PK set
        
        # Count FK values
        total_fk = len(fk_values)
        fk_non_null = [v for v in fk_values if v is not None]
        total_fk_non_null = len(fk_non_null)
        
        if total_fk_non_null == 0:
            # All FK values are null - no relationship
            return ContainmentResult(
                contained=False,
                containment_ratio=0.0,
                orphan_count=0,
                orphan_ratio=0.0,
                total_fk_values=total_fk,
                distinct_fk_values=0,
                distinct_pk_values=len(pk_set),
                validation_method="full_scan",
                is_approximate=False,
            )
        
        # Check containment
        contained_count = 0
        orphan_count = 0
        orphans = []
        
        for fk_value in fk_non_null:
            if fk_value in pk_set:
                contained_count += 1
            else:
                orphan_count += 1
                orphans.append(fk_value)
        
        # Calculate metrics
        containment_ratio = contained_count / total_fk_non_null
        orphan_ratio = orphan_count / total_fk_non_null
        
        # Determine if contained
        contained = containment_ratio >= self.acceptable_threshold
        
        # Count distinct values
        distinct_fk = len(set(fk_non_null))
        distinct_pk = len(pk_set)
        
        return ContainmentResult(
            contained=contained,
            containment_ratio=containment_ratio,
            orphan_count=orphan_count,
            orphan_ratio=orphan_ratio,
            total_fk_values=total_fk,
            distinct_fk_values=distinct_fk,
            distinct_pk_values=distinct_pk,
            validation_method="full_scan",
            is_approximate=False,
        )
    
    def validate_containment_sampled(
        self,
        fk_sample: List[Any],
        pk_values: List[Any],
        total_fk_count: int,
    ) -> ContainmentResult:
        """
        Validate containment using FK sample (approximate validation).
        
        Args:
            fk_sample: Sample of FK column values
            pk_values: All PK column values (or representative sample)
            total_fk_count: Total count of FK values in full dataset
        
        Returns:
            ContainmentResult with approximate containment metrics
        """
        # Build PK set
        pk_set = set(pk_values)
        pk_set.discard(None)
        
        # Count FK sample
        fk_non_null = [v for v in fk_sample if v is not None]
        sample_size = len(fk_non_null)
        
        if sample_size == 0:
            return ContainmentResult(
                contained=False,
                containment_ratio=0.0,
                orphan_count=0,
                orphan_ratio=0.0,
                total_fk_values=total_fk_count,
                distinct_fk_values=0,
                distinct_pk_values=len(pk_set),
                validation_method="sampled",
                is_approximate=True,
            )
        
        # Check containment on sample
        contained_count = 0
        orphan_count_sample = 0
        
        for fk_value in fk_non_null:
            if fk_value in pk_set:
                contained_count += 1
            else:
                orphan_count_sample += 1
        
        # Estimate metrics
        containment_ratio = contained_count / sample_size
        orphan_ratio = orphan_count_sample / sample_size
        
        # Extrapolate orphan count to full dataset
        estimated_orphan_count = int(orphan_ratio * total_fk_count)
        
        contained = containment_ratio >= self.acceptable_threshold
        
        distinct_fk = len(set(fk_non_null))
        distinct_pk = len(pk_set)
        
        return ContainmentResult(
            contained=contained,
            containment_ratio=containment_ratio,
            orphan_count=estimated_orphan_count,
            orphan_ratio=orphan_ratio,
            total_fk_values=total_fk_count,
            distinct_fk_values=distinct_fk,
            distinct_pk_values=distinct_pk,
            validation_method="sampled",
            is_approximate=True,
        )
    
    def validate_containment_sets(
        self,
        fk_distinct_values: Set[Any],
        pk_distinct_values: Set[Any],
        total_fk_count: int,
    ) -> ContainmentResult:
        """
        Validate containment using distinct value sets (memory efficient).
        
        Args:
            fk_distinct_values: Set of distinct FK values
            pk_distinct_values: Set of distinct PK values
            total_fk_count: Total count of FK values
        
        Returns:
            ContainmentResult based on distinct value containment
        """
        # Remove nulls
        fk_set = set(fk_distinct_values)
        fk_set.discard(None)
        pk_set = set(pk_distinct_values)
        pk_set.discard(None)
        
        if not fk_set:
            return ContainmentResult(
                contained=False,
                containment_ratio=0.0,
                orphan_count=0,
                orphan_ratio=0.0,
                total_fk_values=total_fk_count,
                distinct_fk_values=0,
                distinct_pk_values=len(pk_set),
                validation_method="set_based",
                is_approximate=False,
            )
        
        # Compute intersection and orphans
        intersection = fk_set & pk_set
        orphans = fk_set - pk_set
        
        contained_count = len(intersection)
        orphan_count = len(orphans)
        
        # Containment based on distinct values
        containment_ratio = contained_count / len(fk_set)
        orphan_ratio = orphan_count / len(fk_set)
        
        contained = containment_ratio >= self.acceptable_threshold
        
        return ContainmentResult(
            contained=contained,
            containment_ratio=containment_ratio,
            orphan_count=orphan_count,
            orphan_ratio=orphan_ratio,
            total_fk_values=total_fk_count,
            distinct_fk_values=len(fk_set),
            distinct_pk_values=len(pk_set),
            validation_method="set_based",
            is_approximate=False,
        )
    
    def is_strong_containment(self, containment_ratio: float) -> bool:
        """Check if containment ratio indicates strong FK relationship."""
        return containment_ratio >= self.strong_threshold
    
    def is_acceptable_containment(self, containment_ratio: float) -> bool:
        """Check if containment ratio indicates acceptable FK relationship."""
        return containment_ratio >= self.acceptable_threshold
    
    def compute_referential_integrity_score(
        self,
        containment_ratio: float,
        orphan_ratio: float,
    ) -> float:
        """
        Compute referential integrity quality score.
        
        Args:
            containment_ratio: Fraction of FK values contained in PK
            orphan_ratio: Fraction of FK values with no matching PK
        
        Returns:
            Score from 0.0 (broken) to 1.0 (perfect integrity)
        """
        # Referential integrity = containment ratio
        # Penalize based on orphan ratio
        integrity_score = containment_ratio * (1.0 - orphan_ratio * 0.5)
        return max(0.0, min(1.0, integrity_score))


# Singleton instance
_containment_validator = ContainmentValidator()


def validate_containment(
    fk_values: List[Any],
    pk_values: List[Any],
    method: str = "full",
) -> ContainmentResult:
    """
    Convenience function to validate FK containment.
    
    Args:
        fk_values: FK column values
        pk_values: PK column values
        method: "full" or "sampled"
    
    Returns:
        ContainmentResult
    """
    if method == "sampled":
        return _containment_validator.validate_containment_sampled(
            fk_sample=fk_values,
            pk_values=pk_values,
            total_fk_count=len(fk_values) * 10,  # Estimate
        )
    else:
        return _containment_validator.validate_containment_full(
            fk_values=fk_values,
            pk_values=pk_values,
        )
