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
from typing import Tuple, Dict, Any, List, Optional

from profiler.profiling.profiling_models import PKEvidence
from profiler.profiling.suppression_rules import apply_pk_suppressions

log = logging.getLogger(__name__)

AUDIT_IDENTIFIER_RE = re.compile(
    r"(createdby|modifiedby|lasteditedby|deletedby|approvedby|reviewedby|editorid|creatorid|updatedby)$",
    re.IGNORECASE,
)


def _singularize_entity_name(value: str) -> str:
    token = (value or "").lower().strip()
    irregular = {
        "people": "person",
        "men": "man",
        "women": "woman",
        "children": "child",
    }
    if token in irregular:
        return irregular[token]
    if token.endswith("ies"):
        return token[:-3] + "y"
    if token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def extract_table_root(table_name: str) -> str:
    """Extract the table root/owner identifier from table name.

    Examples:
        sales_orders -> order
        sales_invoicelines -> invoiceline
        purchasing_purchaseorderlines -> purchaseorderline
        warehouse_colors -> color
        Application_Cities -> city
    """
    normalized = (table_name or "").lower().strip()
    for prefix in ["sales_", "purchasing_", "warehouse_", "application_"]:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    return _singularize_entity_name(normalized)


def extract_column_root(column_name: str) -> str:
    """Extract root entity from identifier columns like customerid or customer_id."""
    col = (column_name or "").lower().strip()
    for suffix in ("_id", "id", "_key", "key"):
        if col.endswith(suffix):
            col = col[: -len(suffix)]
            break
    return _singularize_entity_name(col)


def compute_pk_score(
    column_name: str,
    uniqueness_ratio: float,
    null_ratio: float,
    entropy_normalized: float,
    type_confidence: float,
    distinct_count: int,
    sample_size: int,
    physical_type: str = "UNKNOWN",
    sample_values: Optional[list] = None,
    table_name: Optional[str] = None
) -> Tuple[float, PKEvidence, bool]:
    """
    Compute primary key confidence score with suppression rules and table ownership.
    
    Formula (V3 with table ownership):
        pk_score = (
            uniqueness_ratio * 0.40 +
            (1 - null_ratio) * 0.20 +
            entropy_normalized * 0.15 +
            table_name_match * 0.15 +
            type_confidence * 0.10
        ) - suppression_penalty
    
    V3: Adds table-name ownership matching to prefer root identifiers.
    
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
        table_name: Table name for ownership matching
        
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
        "table_name": table_name,
    }
    
    suppression_results = apply_pk_suppressions(column_data)

    uniqueness_score = max(0.0, min(1.0, uniqueness_ratio))
    non_null_score = max(0.0, min(1.0, 1.0 - null_ratio))
    entropy_score = max(0.0, min(1.0, entropy_normalized))
    type_stability = max(0.0, min(1.0, type_confidence))

    # Table ownership matching
    name = column_name.lower()
    table_root = extract_table_root(table_name) if table_name else ""
    column_root = extract_column_root(column_name)
    is_identifier = bool(re.match(r"(^id$|.*id$|.*_id$|.*key$|.*_key$)", name))
    is_audit_identifier = bool(AUDIT_IDENTIFIER_RE.search(name))
    
    # Strong match: column = <tableroot>id
    exact_root_match = (name in {f"{table_root}id", f"{table_root}_id"}) if table_root else False
    
    # Partial match: column ends with id/key and starts with table root.
    # This keeps a strong ownership signal without over-matching unrelated IDs.
    partial_root_match = False
    if table_root and not exact_root_match:
        partial_root_match = name.startswith(table_root) and (name.endswith("id") or name.endswith("key"))
    
    # Generic identifier pattern (weaker)
    name_patterns = [
        r'^id$',
        r'^.*id$',
        r'^.*_id$',
        r'^.*key$',
        r'^.*_key$',
        r'^.*code$',
        r'^pk_.*',
        r'^primary_.*',
        r'^.*identifier$',
    ]
    generic_id_match = any(re.match(pattern, name) for pattern in name_patterns)
    
    owner_match = bool(table_root and column_root == table_root and is_identifier)

    # Table-name match score: 1.0 for exact root match, 0.6 for partial, 0.3 for generic ID, 0.0 otherwise
    if exact_root_match:
        table_name_match_score = 1.0
    elif partial_root_match:
        table_name_match_score = 0.6
    elif generic_id_match:
        table_name_match_score = 0.3
    else:
        table_name_match_score = 0.0
    
    name_match = exact_root_match or partial_root_match or generic_id_match

    type_upper = str(physical_type or "").upper()

    # Owner-dominant scoring (PK_REPAIR): ownership is strongest signal.
    ownership_score = 1.0 if owner_match else 0.0
    naming_score = 1.0 if owner_match else (0.7 if name_match else 0.0)

    base_score = (
        ownership_score * 0.40 +
        uniqueness_score * 0.20 +
        non_null_score * 0.15 +
        entropy_score * 0.10 +
        naming_score * 0.10 +
        type_stability * 0.05
    )

    penalty = 0.0
    for suppression in suppression_results["suppressions"]:
        if suppression.severity.value == "critical":
            penalty += 1.0
        elif suppression.severity.value == "high":
            penalty += 0.35
        elif suppression.severity.value == "medium":
            penalty += 0.20
        elif suppression.severity.value == "low":
            penalty += 0.05

    if sample_size < 20:
        penalty += 0.05
    elif sample_size < 200:
        penalty += 0.03

    # Low-cardinality should reduce confidence, not hard-block owner identifiers.
    if distinct_count < 100:
        if distinct_count < 5:
            low_cardinality_penalty = 0.08
        elif distinct_count < 20:
            low_cardinality_penalty = 0.05
        else:
            low_cardinality_penalty = 0.03

        if owner_match and uniqueness_score >= 0.99 and non_null_score >= 0.99:
            low_cardinality_penalty *= 0.25

        penalty += low_cardinality_penalty

    if uniqueness_ratio == 1.0 and sample_size < 200 and not name_match:
        penalty += 0.10

    # Owner exception: duplicates/history should not kill owner identifiers.
    if owner_match and not is_audit_identifier:
        penalty *= 0.25

    pk_score = max(0.0, min(1.0, base_score - penalty))

    if is_audit_identifier:
        pk_score = 0.0
    
    # Build evidence
    reasons = []
    warnings = []
    
    suppression_reasons = [s.reason for s in suppression_results["suppressions"]]
    warnings.extend(suppression_reasons)
    
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
    
    # Table ownership evidence
    if owner_match:
        reasons.append(f"Owner identifier match: '{column_name}' owns '{table_name}'")
    elif exact_root_match:
        reasons.append(f"Exact table-root match: '{column_name}' owns '{table_name}'")
    elif partial_root_match:
        reasons.append(f"Partial table-root match: '{column_name}' in '{table_name}'")
    elif name_match:
        reasons.append(f"Generic identifier pattern: '{column_name}'")
    
    if type_upper in {"INTEGER", "UUID"}:
        reasons.append("Integer/UUID identifier type")
    if _has_consistent_format(sample_values or []):
        reasons.append("Consistent formatting")
    
    # Distinct count
    if distinct_count == sample_size and sample_size > 10:
        reasons.append(f"All {sample_size} values are distinct")
    elif sample_size < 20 and distinct_count == sample_size:
        warnings.append("Small-sample uniqueness may be unstable")
    
    negative_evidence = list(warnings)
    positive_evidence = list(reasons)

    # Fixed threshold: candidate only when final score reaches 0.70 and there
    # are no critical suppressions.
    owner_override = owner_match and not is_audit_identifier and non_null_score >= 0.60
    if owner_override and pk_score < 0.75:
        pk_score = 0.75

    is_candidate = (
        (pk_score >= 0.70 and not suppression_results["should_suppress"] and name_match)
        or owner_override
    )

    if is_audit_identifier:
        is_candidate = False

    if not is_candidate and not negative_evidence:
        if pk_score < 0.70:
            negative_evidence.append(f"PK score below threshold ({pk_score:.2f} < 0.70)")
        elif not name_match:
            negative_evidence.append("Identifier naming pattern absent")
        if uniqueness_score < 0.95:
            negative_evidence.append("Insufficient uniqueness for PK")

    evidence = PKEvidence(
        pk_score=pk_score,
        pk_candidate=is_candidate,
        pk_confidence=pk_score,
        suppressed=suppression_results["should_suppress"],
        suppression_reasons=suppression_reasons,
        positive_evidence=positive_evidence,
        negative_evidence=negative_evidence,
        uniqueness_score=uniqueness_score,
        non_null_score=non_null_score,
        entropy_score=entropy_score,
        type_stability_score=type_stability,
        name_pattern_score=naming_score,
        reasons=reasons,
        warnings=warnings
    )
    
    log.debug(
        f"PK score for '{column_name}': {pk_score:.3f} "
        f"(U:{uniqueness_score:.2f}, N:{non_null_score:.2f}, E:{entropy_score:.2f}) "
        f"Suppressed: {suppression_results['should_suppress']}"
    )

    
    return (pk_score, evidence, is_candidate)


def _has_consistent_format(values: list) -> bool:
    """Return True when sampled non-null values share a stable coarse shape."""
    non_null = [str(v).strip() for v in values if v is not None and str(v).strip()]
    if len(non_null) < 3:
        return False

    def shape(value: str) -> str:
        chars = []
        for char in value:
            if char.isdigit():
                chars.append("9")
            elif char.isalpha():
                chars.append("A")
            else:
                chars.append(char)
        return "".join(chars)

    shapes = {shape(v) for v in non_null[:50]}
    return len(shapes) == 1


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


def select_single_pk(candidates: List[Tuple[str, float, PKEvidence]], table_name: Optional[str] = None) -> List[str]:
    """
    Enforce single PK selection: choose only the top anchor PK per table.
    
    Args:
        candidates: List of (column_name, pk_score, evidence) tuples
        table_name: Table name for ownership verification
        
    Returns:
        List containing at most one PK column name
    """
    if not candidates:
        return []
    
    # Sort by score
    ranked = rank_pk_candidates(candidates)
    
    # If only one candidate, return it
    if len(ranked) == 1:
        return [ranked[0][0]]
    
    # Multiple candidates: prefer table-root match
    table_root = extract_table_root(table_name) if table_name else ""
    
    for col_name, score, evidence in ranked:
        col_lower = col_name.lower()
        # Exact root match wins immediately
        if table_root and col_lower == f"{table_root}id":
            return [col_name]
    
    # No exact root match: return highest scorer
    return [ranked[0][0]]
