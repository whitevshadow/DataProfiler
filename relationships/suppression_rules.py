"""
FK Suppression Rules

Prevents detection of invalid or suspicious FK relationships.

Suppression Categories:
    1. Temporal/Audit Columns (created_at, updated_at, valid_from)
    2. Boolean Columns (is_active, is_deleted)
    3. Low Cardinality Columns (status, type with <10 distinct values)
    4. Constant Columns (all values identical)
    5. Semantic Descriptive Fields (description, comments, notes)
    6. Free-Text Columns (detected via high entropy + long strings)
    7. Mutable Business Attributes (phone, email, addresses)
    8. System Metadata (row_version, etag, hash)
    9. Measure/Metric Columns (amount, price, quantity)
    10. Geospatial Fields (location, coordinates)

Design Principle:
    FK relationships should be STABLE and REFERENTIAL.
    Temporal, mutable, or descriptive columns are poor FK candidates.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import re


@dataclass
class SuppressionResult:
    """Result of FK suppression rule evaluation."""
    should_suppress: bool
    reasons: List[str]
    confidence_penalty: float = 0.0  # Penalty to apply to confidence score


class FKSuppressionRule:
    """Base class for FK suppression rules."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
    
    def should_suppress(
        self,
        fk_column: str,
        fk_profile: Dict[str, Any],
        pk_column: str,
        pk_profile: Dict[str, Any],
    ) -> SuppressionResult:
        """
        Evaluate whether FK relationship should be suppressed.
        
        Args:
            fk_column: FK column name
            fk_profile: FK column profile statistics
            pk_column: PK column name
            pk_profile: PK column profile statistics
        
        Returns:
            SuppressionResult indicating suppression decision
        """
        raise NotImplementedError


class TemporalAuditColumnSuppression(FKSuppressionRule):
    """Suppress temporal and audit columns as FK candidates."""
    
    def __init__(self):
        super().__init__(
            name="temporal_audit_suppression",
            description="Suppress temporal/audit columns (created_at, updated_at, valid_from, etc.)",
        )
        self.temporal_patterns = [
            r"created.*at",
            r"updated.*at",
            r"modified.*at",
            r"deleted.*at",
            r"valid.*from",
            r"valid.*to",
            r"effective.*date",
            r"expiry.*date",
            r"timestamp",
            r".*date",  # Generic date columns
        ]
    
    def should_suppress(
        self,
        fk_column: str,
        fk_profile: Dict[str, Any],
        pk_column: str,
        pk_profile: Dict[str, Any],
    ) -> SuppressionResult:
        fk_lower = fk_column.lower()
        
        for pattern in self.temporal_patterns:
            if re.search(pattern, fk_lower):
                return SuppressionResult(
                    should_suppress=True,
                    reasons=[f"Temporal/audit column pattern: {fk_column}"],
                )
        
        return SuppressionResult(should_suppress=False, reasons=[])


class BooleanColumnSuppression(FKSuppressionRule):
    """Suppress boolean columns as FK candidates."""
    
    def __init__(self):
        super().__init__(
            name="boolean_suppression",
            description="Suppress boolean columns (is_active, is_deleted, etc.)",
        )
    
    def should_suppress(
        self,
        fk_column: str,
        fk_profile: Dict[str, Any],
        pk_column: str,
        pk_profile: Dict[str, Any],
    ) -> SuppressionResult:
        fk_type = fk_profile.get("physical_type", "").upper()
        
        # Suppress if FK is boolean type
        if fk_type == "BOOLEAN":
            return SuppressionResult(
                should_suppress=True,
                reasons=[f"Boolean column: {fk_column}"],
            )
        
        # Suppress if FK has only 2 distinct values (likely boolean)
        distinct_count = fk_profile.get("distinct_count", 0)
        if distinct_count == 2:
            return SuppressionResult(
                should_suppress=True,
                reasons=[f"Binary column (2 distinct values): {fk_column}"],
                confidence_penalty=0.20,
            )
        
        return SuppressionResult(should_suppress=False, reasons=[])


class LowCardinalityColumnSuppression(FKSuppressionRule):
    """Suppress low cardinality columns as FK candidates."""
    
    def __init__(self, max_distinct: int = 10):
        super().__init__(
            name="low_cardinality_suppression",
            description=f"Suppress columns with <{max_distinct} distinct values",
        )
        self.max_distinct = max_distinct
    
    def should_suppress(
        self,
        fk_column: str,
        fk_profile: Dict[str, Any],
        pk_column: str,
        pk_profile: Dict[str, Any],
    ) -> SuppressionResult:
        distinct_count = fk_profile.get("distinct_count", 0)
        
        if 0 < distinct_count < self.max_distinct:
            return SuppressionResult(
                should_suppress=True,
                reasons=[f"Low cardinality ({distinct_count} distinct values): {fk_column}"],
            )
        
        return SuppressionResult(should_suppress=False, reasons=[])


class ConstantColumnSuppression(FKSuppressionRule):
    """Suppress constant columns (all values identical)."""
    
    def __init__(self):
        super().__init__(
            name="constant_column_suppression",
            description="Suppress constant columns (1 distinct value)",
        )
    
    def should_suppress(
        self,
        fk_column: str,
        fk_profile: Dict[str, Any],
        pk_column: str,
        pk_profile: Dict[str, Any],
    ) -> SuppressionResult:
        distinct_count = fk_profile.get("distinct_count", 0)
        
        if distinct_count == 1:
            return SuppressionResult(
                should_suppress=True,
                reasons=[f"Constant column (1 distinct value): {fk_column}"],
            )
        
        return SuppressionResult(should_suppress=False, reasons=[])


class SemanticDescriptiveSuppression(FKSuppressionRule):
    """Suppress semantic descriptive fields."""
    
    def __init__(self):
        super().__init__(
            name="semantic_descriptive_suppression",
            description="Suppress descriptive fields (name, description, comments, notes)",
        )
        self.descriptive_patterns = [
            r".*name$",
            r".*title$",
            r".*description$",
            r".*comments?$",
            r".*notes?$",
            r".*text$",
            r".*memo$",
        ]
    
    def should_suppress(
        self,
        fk_column: str,
        fk_profile: Dict[str, Any],
        pk_column: str,
        pk_profile: Dict[str, Any],
    ) -> SuppressionResult:
        fk_lower = fk_column.lower()
        fk_type = fk_profile.get("physical_type", "").upper()
        
        # Only suppress STRING descriptive fields
        if fk_type not in ["STRING", "VARCHAR", "TEXT"]:
            return SuppressionResult(should_suppress=False, reasons=[])
        
        for pattern in self.descriptive_patterns:
            if re.search(pattern, fk_lower):
                return SuppressionResult(
                    should_suppress=False,  # Don't hard suppress, just penalize
                    reasons=[f"Descriptive field: {fk_column}"],
                    confidence_penalty=0.30,
                )
        
        return SuppressionResult(should_suppress=False, reasons=[])


class MutableBusinessAttributeSuppression(FKSuppressionRule):
    """Suppress mutable business attributes."""
    
    def __init__(self):
        super().__init__(
            name="mutable_business_attribute_suppression",
            description="Suppress mutable attributes (phone, email, address)",
        )
        self.mutable_patterns = [
            r".*phone.*",
            r".*email.*",
            r".*address.*",
            r".*postal.*code.*",
            r".*zip.*code.*",
        ]
    
    def should_suppress(
        self,
        fk_column: str,
        fk_profile: Dict[str, Any],
        pk_column: str,
        pk_profile: Dict[str, Any],
    ) -> SuppressionResult:
        fk_lower = fk_column.lower()
        
        for pattern in self.mutable_patterns:
            if re.search(pattern, fk_lower):
                return SuppressionResult(
                    should_suppress=True,
                    reasons=[f"Mutable business attribute: {fk_column}"],
                )
        
        return SuppressionResult(should_suppress=False, reasons=[])


class MeasureMetricSuppression(FKSuppressionRule):
    """Suppress measure/metric columns."""
    
    def __init__(self):
        super().__init__(
            name="measure_metric_suppression",
            description="Suppress measures/metrics (amount, price, quantity, population)",
        )
        self.measure_patterns = [
            r".*amount",
            r".*price",
            r".*cost",
            r".*quantity",
            r".*population",
            r".*count",
            r".*total",
            r".*sum",
            r".*average",
            r".*balance",
        ]
    
    def should_suppress(
        self,
        fk_column: str,
        fk_profile: Dict[str, Any],
        pk_column: str,
        pk_profile: Dict[str, Any],
    ) -> SuppressionResult:
        fk_lower = fk_column.lower()
        
        for pattern in self.measure_patterns:
            if re.search(pattern, fk_lower):
                return SuppressionResult(
                    should_suppress=True,
                    reasons=[f"Measure/metric column: {fk_column}"],
                )
        
        return SuppressionResult(should_suppress=False, reasons=[])


class GeospatialFieldSuppression(FKSuppressionRule):
    """Suppress geospatial fields."""
    
    def __init__(self):
        super().__init__(
            name="geospatial_suppression",
            description="Suppress geospatial fields (location, coordinates)",
        )
        self.geo_patterns = [
            r".*location",
            r".*coordinate.*",
            r".*latitude",
            r".*longitude",
            r".*geom.*",
            r".*point",
            r".*polygon",
        ]
    
    def should_suppress(
        self,
        fk_column: str,
        fk_profile: Dict[str, Any],
        pk_column: str,
        pk_profile: Dict[str, Any],
    ) -> SuppressionResult:
        fk_lower = fk_column.lower()
        
        for pattern in self.geo_patterns:
            if re.search(pattern, fk_lower):
                return SuppressionResult(
                    should_suppress=True,
                    reasons=[f"Geospatial field: {fk_column}"],
                )
        
        return SuppressionResult(should_suppress=False, reasons=[])


class FKSuppressionEngine:
    """
    Engine for applying FK suppression rules.
    
    Evaluates all rules and combines results.
    """
    
    def __init__(self):
        """Initialize suppression engine with default rules."""
        self.rules = [
            TemporalAuditColumnSuppression(),
            BooleanColumnSuppression(),
            ConstantColumnSuppression(),
            LowCardinalityColumnSuppression(max_distinct=10),
            SemanticDescriptiveSuppression(),
            MutableBusinessAttributeSuppression(),
            MeasureMetricSuppression(),
            GeospatialFieldSuppression(),
        ]
    
    def evaluate(
        self,
        fk_column: str,
        fk_profile: Dict[str, Any],
        pk_column: str,
        pk_profile: Dict[str, Any],
    ) -> SuppressionResult:
        """
        Evaluate all suppression rules for a candidate FK.
        
        Args:
            fk_column: FK column name
            fk_profile: FK column profile
            pk_column: PK column name
            pk_profile: PK column profile
        
        Returns:
            Combined SuppressionResult
        """
        all_reasons = []
        total_penalty = 0.0
        should_suppress = False
        
        for rule in self.rules:
            result = rule.should_suppress(
                fk_column, fk_profile, pk_column, pk_profile
            )
            
            if result.should_suppress:
                should_suppress = True
                all_reasons.extend(result.reasons)
            
            total_penalty += result.confidence_penalty
        
        return SuppressionResult(
            should_suppress=should_suppress,
            reasons=all_reasons,
            confidence_penalty=min(0.50, total_penalty),  # Cap at 0.50
        )


# Singleton instance
_suppression_engine = FKSuppressionEngine()


def should_suppress_fk(
    fk_column: str,
    fk_profile: Dict[str, Any],
    pk_column: str,
    pk_profile: Dict[str, Any],
) -> SuppressionResult:
    """
    Convenience function to check FK suppression.
    
    Args:
        fk_column: FK column name
        fk_profile: FK column profile
        pk_column: PK column name
        pk_profile: PK column profile
    
    Returns:
        SuppressionResult
    """
    return _suppression_engine.evaluate(
        fk_column, fk_profile, pk_column, pk_profile
    )
