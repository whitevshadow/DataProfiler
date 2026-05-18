"""
Primary Key Detector with Suppression Rules

Scores columns as primary key candidates using weighted formula:
- Uniqueness: 45%
- Non-null: 25%
- Entropy: 15%
- Type stability: 10%
- Name pattern: 5%

Threshold: 0.70 for PK candidate

V2: Integrated suppression rules to prevent false positives:
- Temporal columns (validfrom, validto, sentinel timestamps)
- System audit columns (lasteditedby, created_by)
- Constant columns (distinct_count == 1)
- Low cardinality columns (< 100 distinct)
- Zero entropy columns
"""

import re
import logging
from typing import Tuple, Dict, Any

from profiler.profiling.profiling_models import PKEvidence
from profiler.profiling.suppression_rules import apply_pk_suppressions

log = logging.getLogger(__name__)


def compute_pk_score(
    column_name: str,
    uniqueness_ratio: float,
    null_ratio: float,
    entropy_normalized: float,
    type_confidence: float,
    distinct_count: int,
    sample_size: int,
    physical_type: str = "UNKNOWN",
    sample_values: list = None
) -> Tuple[float, PKEvidence, bool]:
    """
    Compute primary key confidence score with suppression rules.
    
    Formula:
        pk_score = (
            uniqueness_ratio * 0.45 +
            (1 - null_ratio) * 0.25 +
            entropy_normalized * 0.15 +
            type_confidence * 0.10 +
            name_pattern_score * 0.05
        ) - suppression_penalty
    
    V2: Applies suppression rules to prevent false positives.
    
    Args:
        column_name: Column name (normalized)
        uniqueness_ratio: Distinct / total (0-1)
        null_ratio: Nulls / total (0-1)
        entropy_normalized: Normalized entropy (0-1)
        type_confidence: Type inference confidence (0-1)
        distinct_count: Number of distinct values
        sample_size: Total sample size
        physical_type: Physical data type (for temporal detection)
        sample_values: Sample values (for sentinel detection)
        
    Returns:
        (pk_score, evidence, is_candidate)
    """
    
    # STEP 1: Apply suppression rules
    column_data = {
        "column_name": column_name,
        "normalized_name": column_name,
        "physical_type": physical_type,
        "sample_values": sample_values or [],
        "null_ratio": null_ratio,
        "distinct_count": distinct_count,
        "entropy_normalized": entropy_normalized,
        "uniqueness_ratio": uniqueness_ratio,
        "sample_size": sample_size,
    }
    
    suppression_results = apply_pk_suppressions(column_data)
    
    # If critical suppression, immediately disqualify
    if suppression_results["should_suppress"]:
        log.warning(f"Column '{column_name}' suppressed as PK candidate")
        for suppression in suppression_results["negative_evidence"]["suppressions"]:
            log.warning(f"  {suppression}")
        
        return (0.0, PKEvidence(
            uniqueness_score=0.0,
            non_null_score=0.0,
            entropy_score=0.0,
            type_stability_score=0.0,
            name_pattern_score=0.0,
            reasons=[],
            warnings=suppression_results["negative_evidence"]["suppressions"]
        ), False)
    
    # 1. Uniqueness score (0-1)
    uniqueness_score = uniqueness_ratio
    
    # 2. Non-null score (0-1)
    non_null_score = 1.0 - null_ratio
    
    # 3. Entropy score (0-1)
    entropy_score = entropy_normalized
    
    # 4. Type stability (consistent type)
    type_stability = type_confidence
    
    # 5. Name pattern matching
    name = column_name.lower()
    name_patterns = [
        r'^id$',
        r'^.*_id$',
        r'^.*key$',
        r'^.*_key$',
        r'^.*code$',
        r'^pk_.*',
        r'^primary_.*',
        r'^.*identifier$',
    ]
    
    name_match = any(re.match(pattern, name) for pattern in name_patterns)
    name_pattern_score = 1.0 if name_match else 0.0
    
    # STEP 2: Compute positive evidence score
    base_score = (
        uniqueness_score * 0.45 +
        non_null_score * 0.25 +
        entropy_score * 0.15 +
        type_stability * 0.10 +
        name_pattern_score * 0.05
    )
    
    # STEP 3: Apply penalties for high/medium/low suppressions
    penalty = 0.0
    for suppression in suppression_results["suppressions"]:
        if suppression.severity.value == "high":
            penalty += 0.25  # Semantic instability - strong penalty
        elif suppression.severity.value == "medium":
            penalty += 0.10  # Low cardinality
        elif suppression.severity.value == "low":
            penalty += 0.05  # Minor issues
    
    pk_score = max(0.0, base_score - penalty)
    
    # Build evidence
    reasons = []
    warnings = []
    
    # Add suppression warnings
    for rule_status in suppression_results["suppression_rules_applied"]:
        if "WARNING" in rule_status or "FAILED" in rule_status:
            warnings.append(rule_status)
    
    # Uniqueness evidence
    if uniqueness_score >= 0.99:
        reasons.append("All values are unique")
    elif uniqueness_score >= 0.95:
        reasons.append(f"Very high uniqueness ({uniqueness_score:.1%})")
    elif uniqueness_score < 0.90:
        warnings.append(f"Uniqueness only {uniqueness_score:.1%}")
    
    # Non-null evidence
    if non_null_score == 1.0:
        reasons.append("No null values")
    elif non_null_score >= 0.95:
        reasons.append(f"Very few nulls ({null_ratio:.1%})")
    else:
        null_count = int(sample_size * null_ratio)
        warnings.append(f"Contains {null_count} nulls ({null_ratio:.1%})")
    
    # Entropy evidence
    if entropy_score >= 0.95:
        reasons.append("High entropy (low redundancy)")
    elif entropy_score < 0.50:
        warnings.append(f"Low entropy ({entropy_score:.2f})")
    
    # Type stability
    if type_stability >= 0.95:
        reasons.append("Consistent data type")
    elif type_stability < 0.80:
        warnings.append(f"Type inconsistency detected ({type_stability:.2f})")
    
    # Name pattern
    if name_match:
        reasons.append(f"Name matches PK pattern: '{column_name}'")
    
    # Distinct count
    if distinct_count == sample_size and sample_size > 10:
        reasons.append(f"All {sample_size} values are distinct")
    
    evidence = PKEvidence(
        uniqueness_score=uniqueness_score,
        non_null_score=non_null_score,
        entropy_score=entropy_score,
        type_stability_score=type_stability,
        name_pattern_score=name_pattern_score,
        reasons=reasons,
        warnings=warnings
    )
    
    # Threshold: 0.70 for PK candidate (after penalties)
    is_candidate = pk_score >= 0.70 and not suppression_results["should_suppress"]
    
    log.debug(
        f"PK score for '{column_name}': {pk_score:.3f} "
        f"(U:{uniqueness_score:.2f}, N:{non_null_score:.2f}, E:{entropy_score:.2f}) "
        f"Suppressed: {suppression_results['should_suppress']}"
    )

    
    return (pk_score, evidence, is_candidate)


def rank_pk_candidates(columns_with_scores: list) -> list:
    """
    Rank PK candidates by score.
    
    Args:
        columns_with_scores: List of (column_name, pk_score, evidence)
        
    Returns:
        Sorted list (highest score first)
    """
    return sorted(
        columns_with_scores,
        key=lambda x: x[1],  # Sort by pk_score
        reverse=True
    )
