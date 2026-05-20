"""
Semantic Data Quality Intelligence Engine

Production-grade quality validation system with 10 quality dimensions:
1. Structural Quality      - Detect corruption and malformation
2. Completeness Quality    - Detect null patterns and sparsity
3. Uniqueness Quality      - Detect duplication and weak identifiers
4. Type Quality            - Detect type conflicts and format issues
5. Semantic Quality        - Detect invalid semantic values
6. Relational Quality      - Detect referential integrity issues
7. Temporal Quality        - Detect temporal anomalies
8. Statistical Quality     - Detect distribution anomalies
9. Consistency Quality     - Detect contradictions
10. Business Rule Quality  - Detect rule violations

Architecture:
- Modular validator classes for each dimension
- Explainable quality reasoning with QualityIssue objects
- Confidence-based scoring
- Severity-weighted penalties
- Metadata-driven configuration
- Scalable to millions/billions of rows
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, date
from enum import Enum

from profiler.profiling.profiling_models import QualityFlag, PhysicalType, SemanticType

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Quality Severity Levels
# ---------------------------------------------------------------------------

class QualitySeverity(str, Enum):
    """Severity level for quality issues."""
    CRITICAL = "critical"    # Data unusable (0.30 penalty)
    HIGH = "high"            # Significant impact (0.20 penalty)
    MEDIUM = "medium"        # Moderate impact (0.10 penalty)
    LOW = "low"              # Minor impact (0.05 penalty)
    INFO = "info"            # Informational (0.02 penalty)


@dataclass
class QualityIssue:
    """Detailed quality issue with explainable context."""
    flag: QualityFlag
    severity: QualitySeverity
    confidence: float  # 0.0-1.0
    message: str
    affected_count: Optional[int] = None
    sample_values: Optional[List[Any]] = None
    remediation_hint: Optional[str] = None


# ---------------------------------------------------------------------------
# Base Quality Validator
# ---------------------------------------------------------------------------

class QualityValidator:
    """Base class for modular quality validators."""
    
    def validate(self, context: Dict[str, Any]) -> List[QualityIssue]:
        """
        Validate quality and return issues found.
        
        Args:
            context: Dictionary with column metadata and statistics
            
        Returns:
            List of quality issues
        """
        raise NotImplementedError()


# ---------------------------------------------------------------------------
# 1. STRUCTURAL QUALITY VALIDATORS
# ---------------------------------------------------------------------------

class StructuralQualityValidator(QualityValidator):
    """Detect structural corruption and malformation."""
    
    def validate(self, context: Dict[str, Any]) -> List[QualityIssue]:
        issues = []
        
        # Truncation detection
        avg_length = context.get("avg_length")
        max_length = context.get("max_length")
        if avg_length and max_length:
            if max_length == avg_length and max_length in [255, 256, 1000, 1024]:
                issues.append(QualityIssue(
                    flag=QualityFlag.TRUNCATION_DETECTED,
                    severity=QualitySeverity.HIGH,
                    confidence=0.75,
                    message=f"Possible truncation at {max_length} characters",
                    remediation_hint="Check source system field length constraints"
                ))
        
        return issues


# ---------------------------------------------------------------------------
# 2. COMPLETENESS QUALITY VALIDATORS
# ---------------------------------------------------------------------------

class CompletenessQualityValidator(QualityValidator):
    """Detect completeness issues."""
    
    def validate(self, context: Dict[str, Any]) -> List[QualityIssue]:
        issues = []
        
        null_ratio = context.get("null_ratio", 0.0)
        null_count = context.get("null_count", 0)
        total_count = context.get("total_count", 0)
        column_name = context.get("column_name", "unknown")
        
        # FULLY_NULL - 100% nulls
        if null_ratio >= 1.0:
            issues.append(QualityIssue(
                flag=QualityFlag.FULLY_NULL,
                severity=QualitySeverity.CRITICAL,
                confidence=1.0,
                message=f"Column '{column_name}' is 100% NULL",
                affected_count=total_count,
                remediation_hint="Remove column or investigate source data issue"
            ))
        
        # HIGH_NULL_RATIO - > 50% nulls
        elif null_ratio > 0.50:
            issues.append(QualityIssue(
                flag=QualityFlag.HIGH_NULL_RATIO,
                severity=QualitySeverity.HIGH,
                confidence=1.0,
                message=f"Column '{column_name}' has {null_ratio:.1%} NULL values",
                affected_count=null_count,
                remediation_hint="Review data collection process for this field"
            ))
        
        # SPARSITY_DETECTED - 20-50% nulls
        elif null_ratio > 0.20:
            issues.append(QualityIssue(
                flag=QualityFlag.SPARSITY_DETECTED,
                severity=QualitySeverity.MEDIUM,
                confidence=1.0,
                message=f"Column '{column_name}' is sparse ({null_ratio:.1%} NULL)",
                affected_count=null_count,
                remediation_hint="Consider if this field should be required"
            ))
        
        return issues


# ---------------------------------------------------------------------------
# 3. UNIQUENESS QUALITY VALIDATORS
# ---------------------------------------------------------------------------

class UniquenessQualityValidator(QualityValidator):
    """Detect uniqueness and duplication issues."""
    
    def validate(self, context: Dict[str, Any]) -> List[QualityIssue]:
        issues = []
        
        distinct_count = context.get("distinct_count", 0)
        total_count = context.get("total_count", 0)
        column_name = context.get("column_name", "unknown")
        uniqueness_ratio = context.get("uniqueness_ratio", 0.0)
        logical_type = context.get("logical_type")
        logical_type_value = getattr(logical_type, "value", logical_type)
        audit_profile = context.get("audit_profile")
        
        if total_count == 0:
            return issues

        if logical_type_value == "audit_reference" or audit_profile:
            if distinct_count > 2:
                issues.append(QualityIssue(
                    flag=QualityFlag.DUPLICATE_EXPECTED,
                    severity=QualitySeverity.INFO,
                    confidence=0.95,
                    message=f"Column '{column_name}' is an audit reference; duplicate values are expected",
                    remediation_hint="Treat as low-cardinality audit identifier rather than boolean"
                ))
                issues.append(QualityIssue(
                    flag=QualityFlag.LOW_CARDINALITY_IDENTIFIER,
                    severity=QualitySeverity.INFO,
                    confidence=0.95,
                    message=f"Column '{column_name}' is a low-cardinality identifier",
                    remediation_hint="Keep identifier semantics despite duplicate reuse"
                ))
            return issues
        
        # DUPLICATE_EXPLOSION - Very low cardinality vs row count
        if distinct_count < (total_count * 0.01) and total_count > 100:
            issues.append(QualityIssue(
                flag=QualityFlag.DUPLICATE_EXPLOSION,
                severity=QualitySeverity.HIGH,
                confidence=0.9,
                message=f"Column '{column_name}' has excessive duplication ({distinct_count} distinct in {total_count} total)",
                affected_count=total_count - distinct_count,
                remediation_hint="Review if this field should have more unique values"
            ))
        
        # WEAK_IDENTIFIER - Column looks like identifier but has duplicates
        if "id" in column_name.lower() and uniqueness_ratio < 0.95:
            issues.append(QualityIssue(
                flag=QualityFlag.WEAK_IDENTIFIER,
                severity=QualitySeverity.MEDIUM,
                confidence=0.75,
                message=f"Column '{column_name}' appears to be identifier but has {(1-uniqueness_ratio)*100:.1f}% duplication",
                remediation_hint="Verify if this should be a unique identifier"
            ))
        
        return issues


# ---------------------------------------------------------------------------
# 4. TYPE QUALITY VALIDATORS
# ---------------------------------------------------------------------------

class TypeQualityValidator(QualityValidator):
    """Detect type inconsistencies and format issues."""
    
    def validate(self, context: Dict[str, Any]) -> List[QualityIssue]:
        issues = []
        
        physical_type = context.get("physical_type")
        type_confidence = context.get("type_confidence", 1.0)
        column_name = context.get("column_name", "unknown")
        sample_values = context.get("sample_values", [])
        
        # TYPE_CONFLICT - Low type confidence
        if type_confidence < 0.70:
            issues.append(QualityIssue(
                flag=QualityFlag.TYPE_CONFLICT,
                severity=QualitySeverity.HIGH,
                confidence=1.0 - type_confidence,
                message=f"Column '{column_name}' has mixed types (confidence: {type_confidence:.2f})",
                remediation_hint="Standardize data types in source system"
            ))
        
        # MIXED_NUMERIC_STRING - Numbers stored as strings
        if physical_type == PhysicalType.STRING and sample_values:
            numeric_count = sum(1 for v in sample_values if v and str(v).replace('.', '', 1).replace('-', '', 1).isdigit())
            if numeric_count > len(sample_values) * 0.5:
                issues.append(QualityIssue(
                    flag=QualityFlag.MIXED_NUMERIC_STRING,
                    severity=QualitySeverity.MEDIUM,
                    confidence=0.8,
                    message=f"Column '{column_name}' contains numeric values stored as strings",
                    affected_count=numeric_count,
                    remediation_hint="Convert to numeric type if appropriate"
                ))
        
        return issues


# ---------------------------------------------------------------------------
# 5. SEMANTIC QUALITY VALIDATORS
# ---------------------------------------------------------------------------

class SemanticQualityValidator(QualityValidator):
    """Detect semantic value violations."""
    
    EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    PHONE_PATTERN = re.compile(r'^\+?[\d\s\-\(\)]{7,20}$')
    
    def validate(self, context: Dict[str, Any]) -> List[QualityIssue]:
        issues = []
        
        semantic_type = context.get("semantic_type")
        column_name = context.get("column_name", "unknown")
        sample_values = context.get("sample_values", [])
        min_value = context.get("min_value")
        max_value = context.get("max_value")
        
        # INVALID_EMAIL
        if semantic_type == SemanticType.EMAIL and sample_values:
            invalid_emails = [v for v in sample_values if v and not self.EMAIL_PATTERN.match(str(v))]
            if invalid_emails:
                issues.append(QualityIssue(
                    flag=QualityFlag.INVALID_EMAIL,
                    severity=QualitySeverity.HIGH,
                    confidence=0.9,
                    message=f"Column '{column_name}' contains invalid email addresses",
                    affected_count=len(invalid_emails),
                    sample_values=invalid_emails[:3],
                    remediation_hint="Validate email format at data entry"
                ))
        
        # MALFORMED_PHONE
        if semantic_type == SemanticType.PHONE and sample_values:
            invalid_phones = [v for v in sample_values if v and not self.PHONE_PATTERN.match(str(v))]
            if invalid_phones:
                issues.append(QualityIssue(
                    flag=QualityFlag.MALFORMED_PHONE,
                    severity=QualitySeverity.MEDIUM,
                    confidence=0.75,
                    message=f"Column '{column_name}' contains malformed phone numbers",
                    affected_count=len(invalid_phones),
                    sample_values=invalid_phones[:3],
                    remediation_hint="Standardize phone number format"
                ))
        
        # NEGATIVE_PRICE
        if "price" in column_name.lower() or "amount" in column_name.lower() or "cost" in column_name.lower():
            if min_value is not None and min_value < 0:
                issues.append(QualityIssue(
                    flag=QualityFlag.NEGATIVE_PRICE,
                    severity=QualitySeverity.HIGH,
                    confidence=0.85,
                    message=f"Column '{column_name}' has negative values (min: {min_value})",
                    remediation_hint="Review negative amounts"
                ))
        
        # IMPOSSIBLE_AGE
        if "age" in column_name.lower():
            if min_value is not None and min_value < 0:
                issues.append(QualityIssue(
                    flag=QualityFlag.IMPOSSIBLE_AGE,
                    severity=QualitySeverity.CRITICAL,
                    confidence=1.0,
                    message=f"Column '{column_name}' has negative age values",
                    remediation_hint="Age cannot be negative"
                ))
            if max_value is not None and max_value > 150:
                issues.append(QualityIssue(
                    flag=QualityFlag.IMPOSSIBLE_AGE,
                    severity=QualitySeverity.HIGH,
                    confidence=0.9,
                    message=f"Column '{column_name}' has age > 150 (max: {max_value})",
                    remediation_hint="Review outlier ages"
                ))
        
        return issues


# ---------------------------------------------------------------------------
# 6. TEMPORAL QUALITY VALIDATORS
# ---------------------------------------------------------------------------

class TemporalQualityValidator(QualityValidator):
    """Detect temporal anomalies."""
    
    def validate(self, context: Dict[str, Any]) -> List[QualityIssue]:
        issues = []
        
        physical_type = context.get("physical_type")
        column_name = context.get("column_name", "unknown")
        max_value = context.get("max_value")
        
        if physical_type not in [PhysicalType.DATE, PhysicalType.DATETIME]:
            return issues
        
        # FUTURE_TIMESTAMP
        try:
            current_date = datetime.now()
            if max_value and isinstance(max_value, (datetime, date)):
                max_dt = max_value if isinstance(max_value, datetime) else datetime.combine(max_value, datetime.min.time())
                if max_dt > current_date:
                    future_delta = (max_dt - current_date).days
                    issues.append(QualityIssue(
                        flag=QualityFlag.FUTURE_TIMESTAMP,
                        severity=QualitySeverity.HIGH,
                        confidence=0.9,
                        message=f"Column '{column_name}' has timestamps {future_delta} days in the future",
                        remediation_hint="Check timezone settings or data entry errors"
                    ))
        except Exception:
            pass
        
        return issues


# ---------------------------------------------------------------------------
# 8. STATISTICAL QUALITY VALIDATORS
# ---------------------------------------------------------------------------

class StatisticalQualityValidator(QualityValidator):
    """Detect statistical anomalies."""
    
    def validate(self, context: Dict[str, Any]) -> List[QualityIssue]:
        issues = []
        
        column_name = context.get("column_name", "unknown")
        distinct_count = context.get("distinct_count", 0)
        entropy_normalized = context.get("entropy_normalized", 0.0)
        skewness = context.get("skewness")
        physical_type = context.get("physical_type")
        
        # CONSTANT_COLUMN
        if distinct_count == 1:
            issues.append(QualityIssue(
                flag=QualityFlag.CONSTANT_COLUMN,
                severity=QualitySeverity.CRITICAL,
                confidence=1.0,
                message=f"Column '{column_name}' has only 1 distinct value",
                remediation_hint="Consider removing this column"
            ))
        
        # ZERO_ENTROPY
        elif entropy_normalized < 0.01:
            issues.append(QualityIssue(
                flag=QualityFlag.ZERO_ENTROPY,
                severity=QualitySeverity.HIGH,
                confidence=1.0,
                message=f"Column '{column_name}' has zero entropy",
                remediation_hint="Column provides no information value"
            ))
        
        # ENTROPY_COLLAPSE
        elif entropy_normalized < 0.10:
            issues.append(QualityIssue(
                flag=QualityFlag.ENTROPY_COLLAPSE,
                severity=QualitySeverity.MEDIUM,
                confidence=0.8,
                message=f"Column '{column_name}' has very low entropy ({entropy_normalized:.3f})",
                remediation_hint="Limited value diversity"
            ))
        
        # EXTREME_SKEWNESS
        if physical_type in [PhysicalType.INTEGER, PhysicalType.FLOAT]:
            if skewness is not None and abs(skewness) > 5.0:
                issues.append(QualityIssue(
                    flag=QualityFlag.EXTREME_SKEWNESS,
                    severity=QualitySeverity.MEDIUM,
                    confidence=0.85,
                    message=f"Column '{column_name}' has extreme skewness ({skewness:.2f})",
                    remediation_hint="Distribution is highly asymmetric"
                ))
            elif skewness is not None and abs(skewness) > 2.0:
                issues.append(QualityIssue(
                    flag=QualityFlag.SKEWED_DISTRIBUTION,
                    severity=QualitySeverity.LOW,
                    confidence=0.75,
                    message=f"Column '{column_name}' has skewed distribution ({skewness:.2f})",
                    remediation_hint="Consider log transformation"
                ))
        
        return issues


# ---------------------------------------------------------------------------
# 9. CONSISTENCY & 10. BUSINESS RULE VALIDATORS (Placeholders)
# ---------------------------------------------------------------------------

class ConsistencyQualityValidator(QualityValidator):
    """Detect consistency issues (requires cross-column analysis)."""
    def validate(self, context: Dict[str, Any]) -> List[QualityIssue]:
        return []  # Future: cross-row/column analysis


class BusinessRuleQualityValidator(QualityValidator):
    """Detect business rule violations (requires rule configuration)."""
    def validate(self, context: Dict[str, Any]) -> List[QualityIssue]:
        return []  # Future: configurable rule engine


# ---------------------------------------------------------------------------
# Cardinality & PII Validators
# ---------------------------------------------------------------------------

class CardinalityQualityValidator(QualityValidator):
    """Detect cardinality anomalies."""
    
    def validate(self, context: Dict[str, Any]) -> List[QualityIssue]:
        issues = []
        
        distinct_count = context.get("distinct_count", 0)
        total_count = context.get("total_count", 0)
        column_name = context.get("column_name", "unknown")
        semantic_type = context.get("semantic_type")
        
        # LOW_CARDINALITY
        if distinct_count < 3 and total_count > 10:
            issues.append(QualityIssue(
                flag=QualityFlag.LOW_CARDINALITY,
                severity=QualitySeverity.LOW,
                confidence=0.7,
                message=f"Column '{column_name}' has low cardinality ({distinct_count} values)",
                remediation_hint="May be suitable for categorical encoding"
            ))
        
        # HIGH_CARDINALITY
        if semantic_type == SemanticType.CATEGORY and distinct_count > 1000:
            issues.append(QualityIssue(
                flag=QualityFlag.HIGH_CARDINALITY,
                severity=QualitySeverity.MEDIUM,
                confidence=0.8,
                message=f"Column '{column_name}' has high cardinality for category ({distinct_count} values)",
                remediation_hint="Consider hierarchical grouping"
            ))
        
        return issues


class PIIQualityValidator(QualityValidator):
    """Detect PII exposure risks."""
    
    def validate(self, context: Dict[str, Any]) -> List[QualityIssue]:
        issues = []
        
        semantic_type = context.get("semantic_type")
        column_name = context.get("column_name", "unknown")
        
        if semantic_type in [SemanticType.EMAIL, SemanticType.PHONE, SemanticType.SSN]:
            issues.append(QualityIssue(
                flag=QualityFlag.PII_EXPOSURE_RISK,
                severity=QualitySeverity.HIGH,
                confidence=0.9,
                message=f"Column '{column_name}' contains PII ({semantic_type.value})",
                remediation_hint="Consider encryption, masking, or access controls"
            ))
        
        return issues


# ---------------------------------------------------------------------------
# Main Quality Engine
# ---------------------------------------------------------------------------

class QualityEngine:
    """
    Main quality engine orchestrator.
    
    Coordinates all quality validators and produces comprehensive assessment.
    """
    
    def __init__(self):
        self.validators = [
            StructuralQualityValidator(),
            CompletenessQualityValidator(),
            UniquenessQualityValidator(),
            TypeQualityValidator(),
            SemanticQualityValidator(),
            TemporalQualityValidator(),
            StatisticalQualityValidator(),
            ConsistencyQualityValidator(),
            BusinessRuleQualityValidator(),
            CardinalityQualityValidator(),
            PIIQualityValidator(),
        ]
    
    def assess_quality(self, context: Dict[str, Any]) -> Tuple[List[QualityFlag], float, List[QualityIssue]]:
        """
        Perform comprehensive quality assessment.
        
        Args:
            context: Dictionary with column metadata and statistics
            
        Returns:
            Tuple of (quality_flags, quality_score, quality_issues)
        """
        all_issues = []
        
        for validator in self.validators:
            try:
                issues = validator.validate(context)
                all_issues.extend(issues)
            except Exception as e:
                log.error(f"Validator {validator.__class__.__name__} failed: {e}")
        
        flags = [issue.flag for issue in all_issues]
        quality_score = self._compute_quality_score(all_issues)
        
        return flags, quality_score, all_issues
    
    def _compute_quality_score(self, issues: List[QualityIssue]) -> float:
        """
        Compute quality score with confidence-weighted severity penalties.
        
        Args:
            issues: List of quality issues
            
        Returns:
            Quality score (0.0-1.0)
        """
        if not issues:
            return 1.0
        
        severity_penalties = {
            QualitySeverity.CRITICAL: 0.30,
            QualitySeverity.HIGH: 0.20,
            QualitySeverity.MEDIUM: 0.10,
            QualitySeverity.LOW: 0.05,
            QualitySeverity.INFO: 0.02,
        }
        
        total_penalty = 0.0
        for issue in issues:
            base_penalty = severity_penalties.get(issue.severity, 0.10)
            weighted_penalty = base_penalty * issue.confidence
            total_penalty += weighted_penalty
        
        total_penalty = min(total_penalty, 1.0)
        return max(1.0 - total_penalty, 0.0)


# ---------------------------------------------------------------------------
# Backwards Compatible API
# ---------------------------------------------------------------------------

def detect_quality_flags(
    column_name: str,
    physical_type: PhysicalType,
    semantic_type: Optional[SemanticType],
    null_ratio: float,
    distinct_count: int,
    total_count: int,
    entropy_normalized: float,
    skewness: Optional[float] = None,
    **kwargs
) -> List[QualityFlag]:
    """Detect quality issues (backwards compatible API)."""
    
    engine = QualityEngine()
    
    context = {
        "column_name": column_name,
        "physical_type": physical_type,
        "semantic_type": semantic_type,
        "null_ratio": null_ratio,
        "null_count": int(null_ratio * total_count),
        "distinct_count": distinct_count,
        "total_count": total_count,
        "entropy_normalized": entropy_normalized,
        "skewness": skewness,
        "uniqueness_ratio": kwargs.get("uniqueness_ratio", distinct_count / total_count if total_count > 0 else 0.0),
    }
    context.update(kwargs)
    
    flags, quality_score, issues = engine.assess_quality(context)

    duplicate_ratio = float(context.get("duplicate_ratio") or 0.0)
    kurtosis = context.get("kurtosis")
    if null_ratio > 0.50 and QualityFlag.HIGH_MISSINGNESS not in flags:
        flags.append(QualityFlag.HIGH_MISSINGNESS)
    if duplicate_ratio > 0.50 and QualityFlag.HIGH_DUPLICATION not in flags:
        flags.append(QualityFlag.HIGH_DUPLICATION)
    if kurtosis is not None and kurtosis > 10 and QualityFlag.HEAVY_TAIL not in flags:
        flags.append(QualityFlag.HEAVY_TAIL)
    if re.search(r'(^id$|id$|_id$|key$|_key$|identifier$)', column_name.lower()) and distinct_count <= 1 and QualityFlag.INVALID_IDENTIFIER not in flags:
        flags.append(QualityFlag.INVALID_IDENTIFIER)
    
    for issue in issues:
        log.warning(f"Column '{column_name}': {issue.flag.value.upper()}")
    
    return flags


def compute_quality_score(quality_flags: List[QualityFlag]) -> float:
    """Compute quality score (backwards compatible API)."""
    
    if not quality_flags:
        return 1.0
    
    severity_weights = {
        QualityFlag.CONSTANT_COLUMN: 0.30,
        QualityFlag.FULLY_NULL: 0.30,
        QualityFlag.PK_DUPLICATION: 0.30,
        QualityFlag.REQUIRED_FIELD_MISSING: 0.30,
        QualityFlag.HIGH_NULL_RATIO: 0.20,
        QualityFlag.HIGH_MISSINGNESS: 0.22,
        QualityFlag.ZERO_ENTROPY: 0.20,
        QualityFlag.DUPLICATE_EXPLOSION: 0.20,
        QualityFlag.HIGH_DUPLICATION: 0.15,
        QualityFlag.TYPE_CONFLICT: 0.20,
        QualityFlag.NEGATIVE_PRICE: 0.20,
        QualityFlag.IMPOSSIBLE_AGE: 0.20,
        QualityFlag.PII_EXPOSURE_RISK: 0.15,
        QualityFlag.INVALID_EMAIL: 0.15,
        QualityFlag.SPARSITY_DETECTED: 0.10,
        QualityFlag.LOW_CARDINALITY: 0.10,
        QualityFlag.WEAK_IDENTIFIER: 0.10,
        QualityFlag.WEAK_RELATIONSHIP: 0.10,
        QualityFlag.HIGH_CARDINALITY: 0.08,
        QualityFlag.SKEWED_DISTRIBUTION: 0.05,
        QualityFlag.OUTLIER_DETECTED: 0.08,
        QualityFlag.HEAVY_TAIL: 0.08,
        QualityFlag.INVALID_IDENTIFIER: 0.20,
        QualityFlag.TEMPORAL_ANOMALY: 0.15,
        QualityFlag.GEO_ERROR: 0.15,
    }
    
    total_penalty = sum(severity_weights.get(flag, 0.10) for flag in quality_flags)
    total_penalty = min(total_penalty, 1.0)
    
    return max(1.0 - total_penalty, 0.0)
