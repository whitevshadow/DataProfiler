"""
PK Suppression Rule Engine

Prevents false PK candidates through negative evidence detection.

Critical rules:
1. Temporal Column Suppression
2. System Audit Column Suppression
3. Constant Column Suppression
4. Low Cardinality Suppression
5. Zero Entropy Suppression
"""

import re
import logging
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum


log = logging.getLogger(__name__)


class SuppressionSeverity(str, Enum):
    """Suppression rule severity levels."""
    CRITICAL = "critical"  # Immediate disqualification
    HIGH = "high"          # Strong penalty
    MEDIUM = "medium"      # Moderate penalty
    LOW = "low"            # Minor penalty


@dataclass
class SuppressionResult:
    """Result of a suppression rule evaluation."""
    suppress: bool
    reason: str
    severity: SuppressionSeverity


# ---------------------------------------------------------------------------
# Base Suppression Rule
# ---------------------------------------------------------------------------

class PKSuppressionRule:
    """Base class for PK suppression rules."""
    
    def __init__(self, name: str):
        self.name = name
    
    def evaluate(self, column_data: dict) -> SuppressionResult:
        """
        Evaluate suppression rule on column data.
        
        Args:
            column_data: Dict with keys:
                - column_name (str)
                - normalized_name (str)
                - physical_type (str)
                - semantic_type (Optional[str])
                - sample_values (List[Any])
                - null_ratio (float)
                - distinct_count (int)
                - entropy_normalized (float)
                - uniqueness_ratio (float)
                
        Returns:
            SuppressionResult
        """
        raise NotImplementedError()


# ---------------------------------------------------------------------------
# Rule 1: Temporal Column Suppression
# ---------------------------------------------------------------------------

class TemporalColumnSuppression(PKSuppressionRule):
    """Suppress temporal audit columns and sentinel timestamps."""
    
    TEMPORAL_PATTERNS = [
        r'^valid(from|to)$',
        r'^timestamp$',
        r'^effective_date$',
        r'^effectivedate$',
        r'^createdat$',
        r'^updatedat$',
        r'^deletedat$',
        r'^.*_timestamp$',
        r'^.*_datetime$',
        r'^created_at$',
        r'^updated_at$',
        r'^modified_at$',
        r'^deleted_at$',
        r'^last_edited_when$',
        r'^.*_date$',
    ]
    
    SENTINEL_VALUES = [
        '9999-12-31',
        '9999-12-31 23:59:59',
        '9999-12-31 23:59:59.999',
        '1900-01-01',
        '1900-01-01 00:00:00',
        '0001-01-01',
        '0001-01-01 00:00:00',
    ]
    
    def __init__(self):
        super().__init__("temporal_column_suppression")
    
    def evaluate(self, column_data: dict) -> SuppressionResult:
        column_name = column_data.get("normalized_name", "")
        physical_type = column_data.get("physical_type", "")
        sample_values = column_data.get("sample_values", [])
        
        # Check name pattern
        for pattern in self.TEMPORAL_PATTERNS:
            if re.match(pattern, column_name):
                return SuppressionResult(
                    suppress=True,
                    reason=f"Temporal audit column pattern '{column_name}'",
                    severity=SuppressionSeverity.CRITICAL
                )
        
        # Check for sentinel values in DATE/DATETIME columns
        if physical_type in ['DATE', 'DATETIME']:
            for sample in sample_values[:20]:  # Check first 20 samples
                sample_str = str(sample).strip()
                for sentinel in self.SENTINEL_VALUES:
                    if sentinel in sample_str:
                        return SuppressionResult(
                            suppress=True,
                            reason=f"Sentinel timestamp value '{sentinel}' detected",
                            severity=SuppressionSeverity.CRITICAL
                        )
        
        return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)


# ---------------------------------------------------------------------------
# Rule 2: System Audit Column Suppression
# ---------------------------------------------------------------------------

class SystemAuditColumnSuppression(PKSuppressionRule):
    """Suppress system-generated audit columns (user tracking, etc.)."""
    
    AUDIT_PATTERNS = [
        r'^lasteditedby$',
        r'^last_edited_by$',
        r'^createdby$',
        r'^modifiedby$',
        r'^updatedby$',
        r'^created_by$',
        r'^modified_by$',
        r'^updated_by$',
        r'^deleted_by$',
        r'^.*_user_id$',
        r'^.*_user$',
        r'^audit_.*',
    ]
    
    def __init__(self):
        super().__init__("system_audit_suppression")
    
    def evaluate(self, column_data: dict) -> SuppressionResult:
        column_name = column_data.get("normalized_name", "")
        
        for pattern in self.AUDIT_PATTERNS:
            if re.match(pattern, column_name):
                return SuppressionResult(
                    suppress=True,
                    reason=f"System audit column pattern '{column_name}'",
                    severity=SuppressionSeverity.CRITICAL
                )
        
        return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)


# ---------------------------------------------------------------------------
# Rule 3: Constant Column Suppression
# ---------------------------------------------------------------------------

class ConstantColumnSuppression(PKSuppressionRule):
    """Suppress columns with only 1 distinct value."""
    
    def __init__(self):
        super().__init__("constant_value_suppression")
    
    def evaluate(self, column_data: dict) -> SuppressionResult:
        distinct_count = column_data.get("distinct_count", 0)
        
        if distinct_count == 1:
            return SuppressionResult(
                suppress=True,
                reason="Constant column (1 distinct value)",
                severity=SuppressionSeverity.CRITICAL
            )
        
        return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)


# ---------------------------------------------------------------------------
# Rule 4: Low Cardinality Suppression
# ---------------------------------------------------------------------------

class LowCardinalitySuppression(PKSuppressionRule):
    """Suppress low-cardinality columns."""
    
    def __init__(self, min_distinct_threshold: int = 100):
        super().__init__("cardinality_threshold")
        self.min_distinct_threshold = min_distinct_threshold
    
    def evaluate(self, column_data: dict) -> SuppressionResult:
        distinct_count = column_data.get("distinct_count", 0)
        column_name = str(column_data.get("normalized_name", "")).lower()
        is_identifier_name = bool(
            re.search(r"(^id$|id$|_id$|key$|_key$|code$|identifier$)", column_name)
        )
        
        # Exemption for dimension tables (small tables where distinct == total)
        uniqueness_ratio = column_data.get("uniqueness_ratio", 0.0)
        row_count = column_data.get("sample_size", 0)
        if row_count <= 20 and uniqueness_ratio >= 0.99 and distinct_count >= 2 and is_identifier_name:
            return SuppressionResult(
                suppress=False,
                reason=(
                    f"Small-table identifier exemption "
                    f"({distinct_count} distinct, uniqueness {uniqueness_ratio:.2f})"
                ),
                severity=SuppressionSeverity.LOW
            )
        if row_count < 20 and distinct_count > 10 and uniqueness_ratio > 0.95:
            return SuppressionResult(
                suppress=False,
                reason=f"Small-table dimension exemption ({distinct_count} distinct, uniqueness {uniqueness_ratio:.2f})",
                severity=SuppressionSeverity.LOW
            )
        if uniqueness_ratio >= 0.99 and is_identifier_name:
            return SuppressionResult(
                suppress=False,
                reason="Identifier naming exemption for low-cardinality unique column",
                severity=SuppressionSeverity.LOW
            )
        if uniqueness_ratio >= 0.99 and distinct_count > 10:
            # Dimension table PK - allow it but warn
            return SuppressionResult(
                suppress=False,
                reason=f"Low cardinality ({distinct_count} < {self.min_distinct_threshold}) but dimension table exemption",
                severity=SuppressionSeverity.LOW
            )
        
        if distinct_count < self.min_distinct_threshold:
            return SuppressionResult(
                suppress=False,
                reason=f"Low cardinality ({distinct_count} < {self.min_distinct_threshold}); confidence reduced in scorer",
                severity=SuppressionSeverity.LOW
            )
        
        return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)


# ---------------------------------------------------------------------------
# Rule 5: Zero Entropy Suppression
# ---------------------------------------------------------------------------

class ZeroEntropySuppression(PKSuppressionRule):
    """Suppress zero-entropy columns (no information)."""
    
    def __init__(self, min_entropy_threshold: float = 0.01):
        super().__init__("zero_entropy_suppression")
        self.min_entropy_threshold = min_entropy_threshold
    
    def evaluate(self, column_data: dict) -> SuppressionResult:
        entropy_normalized = column_data.get("entropy_normalized", 0.0)
        
        if entropy_normalized < self.min_entropy_threshold:
            return SuppressionResult(
                suppress=True,
                reason=f"Zero entropy (entropy_normalized={entropy_normalized:.4f})",
                severity=SuppressionSeverity.CRITICAL
            )
        
        return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)


# ---------------------------------------------------------------------------
# Rule 6: Semantic Instability Suppression
# ---------------------------------------------------------------------------

class SemanticInstabilitySuppression(PKSuppressionRule):
    """Suppress semantically unstable descriptive fields."""
    
    UNSTABLE_PATTERNS = [
        r'^.*name$',
        r'^.*_name$',
        r'^name$',
        r'^.*title$',
        r'^title$',
        r'^.*description$',
        r'^description$',
        r'^.*label$',
        r'^label$',
        r'^.*comment$',
        r'^comment$',
        r'^.*text$',
        r'^.*notes$',
        r'^.*remarks$',
    ]
    
    def __init__(self):
        super().__init__("semantic_instability_suppression")
    
    def evaluate(self, column_data: dict) -> SuppressionResult:
        column_name = column_data.get("normalized_name", "")
        physical_type = column_data.get("physical_type", "")
        
        # Only apply to STRING types
        if physical_type != "STRING":
            return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)
        
        # Check for unstable name patterns
        for pattern in self.UNSTABLE_PATTERNS:
            if re.match(pattern, column_name):
                return SuppressionResult(
                    suppress=True,
                    reason=f"Semantically unstable descriptive field '{column_name}'",
                    severity=SuppressionSeverity.HIGH
                )
        
        return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)


# ---------------------------------------------------------------------------
# Rule 7: Type Affinity Adjustment
# ---------------------------------------------------------------------------

class TypeAffinityRule(PKSuppressionRule):
    """Penalize STRING types, prefer INTEGER/UUID types for PKs."""
    
    def __init__(self):
        super().__init__("type_affinity_adjustment")
    
    def evaluate(self, column_data: dict) -> SuppressionResult:
        physical_type = column_data.get("physical_type", "")
        column_name = column_data.get("normalized_name", "")
        
        # Prefer INTEGER/UUID types
        if physical_type in ["INTEGER", "UUID"]:
            return SuppressionResult(
                suppress=False,
                reason="Preferred PK type (INTEGER/UUID)",
                severity=SuppressionSeverity.LOW
            )
        
        # STRING types should be scrutinized
        if physical_type == "STRING":
            # Natural keys (codes, identifiers) are acceptable
            if any(pattern in column_name for pattern in ['code', 'key', 'id', 'identifier']):
                return SuppressionResult(
                    suppress=False,
                    reason="Natural key pattern in STRING column",
                    severity=SuppressionSeverity.LOW
                )
            else:
                # Generic STRING without key pattern - add penalty
                return SuppressionResult(
                    suppress=False,
                    reason="STRING type without key pattern - low affinity",
                    severity=SuppressionSeverity.MEDIUM
                )
        
        return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)


# ---------------------------------------------------------------------------
# Rule 8: Measure/Metric Suppression
# ---------------------------------------------------------------------------

class MeasureMetricSuppression(PKSuppressionRule):
    """Suppress columns that are measures, metrics, or aggregated values."""
    
    MEASURE_PATTERNS = [
        r'^.*population$',
        r'^.*amount$',
        r'^.*price$',
        r'^.*quantity$',
        r'^.*score$',
        r'^.*percentage$',
        r'^.*percent$',
        r'^.*count$',
        r'^.*total$',
        r'^.*sum$',
        r'^.*average$',
        r'^.*avg$',
        r'^.*min$',
        r'^.*max$',
        r'^.*balance$',
        r'^.*value$',
        r'^.*revenue$',
        r'^.*cost$',
        r'^.*weight$',
        r'^.*volume$',
        r'^.*size$',
        r'^.*length$',
        r'^.*width$',
        r'^.*height$',
        r'^.*rate$',
    ]
    
    def __init__(self):
        super().__init__("measure_metric_suppression")
    
    def evaluate(self, column_data: dict) -> SuppressionResult:
        column_name = column_data.get("normalized_name", "")
        physical_type = column_data.get("physical_type", "")
        
        # Measures are typically numeric
        if physical_type not in ["INTEGER", "FLOAT", "DECIMAL", "NUMERIC", "DOUBLE"]:
            return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)
        
        # Check for measure/metric patterns
        for pattern in self.MEASURE_PATTERNS:
            if re.match(pattern, column_name):
                return SuppressionResult(
                    suppress=True,
                    reason=f"Measure/metric column '{column_name}' - not a stable identifier",
                    severity=SuppressionSeverity.HIGH
                )
        
        return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)


# ---------------------------------------------------------------------------
# Rule 9: Geospatial Field Suppression
# ---------------------------------------------------------------------------

class GeospatialFieldSuppression(PKSuppressionRule):
    """Suppress geospatial coordinate and geometry columns."""
    
    GEOSPATIAL_PATTERNS = [
        r'^.*location$',
        r'^.*coordinates$',
        r'^.*coord$',
        r'^.*geom$',
        r'^.*geometry$',
        r'^.*polygon$',
        r'^.*point$',
        r'^.*latitude$',
        r'^.*lat$',
        r'^.*longitude$',
        r'^.*lng$',
        r'^.*lon$',
        r'^.*geolocation$',
        r'^.*geopoint$',
        r'^.*shape$',
    ]
    
    GEOSPATIAL_VALUE_PATTERNS = [
        r'^POINT\(',
        r'^POLYGON\(',
        r'^LINESTRING\(',
        r'^MULTIPOINT\(',
        r'^MULTIPOLYGON\(',
        r'^\{.*"type":\s*"(Point|Polygon|LineString|Feature)"',  # GeoJSON
    ]
    
    def __init__(self):
        super().__init__("geospatial_field_suppression")
    
    def evaluate(self, column_data: dict) -> SuppressionResult:
        column_name = column_data.get("normalized_name", "")
        sample_values = column_data.get("sample_values", [])
        
        # Check column name patterns
        for pattern in self.GEOSPATIAL_PATTERNS:
            if re.match(pattern, column_name):
                return SuppressionResult(
                    suppress=True,
                    reason=f"Geospatial field '{column_name}' - not suitable as PK",
                    severity=SuppressionSeverity.CRITICAL
                )
        
        # Check sample values for geospatial data
        if sample_values:
            sample_str = str(sample_values[0]) if len(sample_values) > 0 else ""
            for pattern in self.GEOSPATIAL_VALUE_PATTERNS:
                if re.search(pattern, sample_str):
                    return SuppressionResult(
                        suppress=True,
                        reason=f"Geospatial data detected in '{column_name}'",
                        severity=SuppressionSeverity.CRITICAL
                    )
        
        return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)


# ---------------------------------------------------------------------------
# Rule 10: Boolean Column Suppression (NEW)
# ---------------------------------------------------------------------------

class BooleanColumnSuppression(PKSuppressionRule):
    """Suppress boolean/flag columns that happen to be unique in sample."""
    
    BOOLEAN_PATTERNS = [
        r'^is[a-z].*',                    # isEmployee, isActive, ispermittedtologon
        r'^has[a-z].*',                   # hasPermission, hasAccess
        r'^can[a-z].*',                   # canEdit, canDelete
        r'^.*_(flag|enabled|disabled)$',  # status_flag, is_enabled
        r'^.*preferences$',               # userpreferences (JSON/TEXT)
        r'^.*fields$',                    # customfields (JSON/TEXT)
        r'^.*languages$',                 # otherlanguages (JSON/TEXT)
    ]

    IDENTIFIER_EXEMPT_PATTERNS = [
        r'(id|key|code|identifier|number)$',
        r'(createdby|modifiedby|lasteditedby|editedby|approvedby|deletedby|reviewedby|insertedby|updatedby)$',
        r'(userid|editorid|creatorid)$',
    ]
    
    def __init__(self):
        super().__init__("boolean_column_suppression")
    
    def evaluate(self, column_data: dict) -> SuppressionResult:
        column_name = column_data.get("normalized_name", "")
        distinct_count = column_data.get("distinct_count", 0)
        sample_size = column_data.get("sample_size", 0)
        uniqueness_ratio = column_data.get("uniqueness_ratio", 0.0)
        
        # Check boolean naming patterns
        for pattern in self.BOOLEAN_PATTERNS:
            if re.match(pattern, column_name):
                # Boolean columns should NEVER be PK candidates
                return SuppressionResult(
                    suppress=True,
                    reason=f"Boolean/flag column pattern '{column_name}' - not a stable identifier",
                    severity=SuppressionSeverity.CRITICAL
                )
        
        # Suppress columns with accidental uniqueness in small samples (non-ID names)
        if uniqueness_ratio == 1.0 and sample_size < 200:
            # Check if name suggests it's NOT meant to be an identifier
            if not any(re.search(pattern, column_name) for pattern in self.IDENTIFIER_EXEMPT_PATTERNS):
                return SuppressionResult(
                    suppress=True,
                    reason=f"Accidental uniqueness in small sample (n={sample_size}) for non-ID column '{column_name}'",
                    severity=SuppressionSeverity.HIGH
                )
        
        return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)


# ---------------------------------------------------------------------------
# Rule 11: Low-Stability Business Attribute Suppression
# ---------------------------------------------------------------------------

class LowStabilityBusinessAttributeSuppression(PKSuppressionRule):
    """Suppress mutable business attributes (phone, email, URL, address)."""
    
    UNSTABLE_BUSINESS_PATTERNS = [
        r'^.*phone.*$',
        r'^.*fax.*$',
        r'^.*email.*$',
        r'^.*url$',
        r'^.*website.*$',
        r'^.*address.*$',
        r'^.*street.*$',
        r'^.*city$',
        r'^.*country$',
        r'^.*region$',
        r'^.*contact.*$',
        r'^.*mobile.*$',
    ]
    
    # Postal codes can be STRING or INTEGER - always suppress
    POSTAL_CODE_PATTERNS = [
        r'^.*postal.*$',
        r'^.*zip.*$',
        r'^.*postcode.*$',
    ]
    
    def __init__(self):
        super().__init__("low_stability_business_attribute_suppression")
    
    def evaluate(self, column_data: dict) -> SuppressionResult:
        column_name = column_data.get("normalized_name", "")
        physical_type = column_data.get("physical_type", "")
        
        # Postal codes are mutable regardless of type
        for pattern in self.POSTAL_CODE_PATTERNS:
            if re.match(pattern, column_name):
                return SuppressionResult(
                    suppress=True,
                    reason=f"Postal/zip code '{column_name}' - mutable business attribute",
                    severity=SuppressionSeverity.CRITICAL  # Postal codes are never valid PKs
                )
        
        # Other unstable attributes (apply only to STRING types)
        if physical_type != "STRING":
            return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)
        
        # Check for unstable business attribute patterns
        for pattern in self.UNSTABLE_BUSINESS_PATTERNS:
            if re.match(pattern, column_name):
                return SuppressionResult(
                    suppress=True,
                    reason=f"Low-stability business attribute '{column_name}' - high mutability",
                    severity=SuppressionSeverity.HIGH
                )
        
        return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)


class TransactionalIdentifierSuppression(PKSuppressionRule):
    """Suppress highly unique identifiers on transactional tables."""

    TRANSACTIONAL_PATTERNS = [
        r'^orderid$',
        r'^invoiceid$',
        r'^transactionid$',
        r'^.*order.*id$',
        r'^.*invoice.*id$',
        r'^.*transaction.*id$',
        r'^.*line.*id$',
    ]

    def __init__(self):
        super().__init__("transactional_identifier_suppression")

    def evaluate(self, column_data: dict) -> SuppressionResult:
        column_name = column_data.get("normalized_name", "")
        sample_size = column_data.get("sample_size", 0)
        distinct_count = column_data.get("distinct_count", 0)
        uniqueness_ratio = column_data.get("uniqueness_ratio", 0.0)

        if sample_size < 20:
            return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)

        if not any(re.match(pattern, column_name) for pattern in self.TRANSACTIONAL_PATTERNS):
            return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)

        if distinct_count > 100 and uniqueness_ratio >= 0.95:
            return SuppressionResult(
                suppress=False,
                reason=f"Transactional identifier '{column_name}' handled by table-root ownership scoring",
                severity=SuppressionSeverity.LOW
            )

        return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)


class NonRootIdentifierSuppression(PKSuppressionRule):
    """Suppress identifier columns that don't match the table root.
    
    When a table has multiple ID-like columns, only the table-root identifier
    should be considered for PK. All others are FK candidates.
    
    Example:
        Table: sales_orders (root: order)
        - orderid -> allowed (matches root)
        - customerid -> suppress (FK candidate)
        - salespersonpersonid -> suppress (FK candidate)
    """
    
    def __init__(self):
        super().__init__("non_root_identifier_suppression")
    
    def _extract_table_root(self, table_name: str) -> str:
        """Extract table root name."""
        normalized = table_name.lower().strip()
        irregular = {
            'people': 'person',
            'men': 'man',
            'women': 'woman',
            'children': 'child',
        }
        for prefix in ['sales_', 'purchasing_', 'warehouse_', 'application_']:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break
        if normalized in irregular:
            return irregular[normalized]
        if normalized.endswith('ies'):
            return normalized[:-3] + 'y'
        if normalized.endswith('s') and not normalized.endswith('ss'):
            return normalized[:-1]
        return normalized
    
    def evaluate(self, column_data: dict) -> SuppressionResult:
        column_name = column_data.get("normalized_name", "")
        table_name = column_data.get("table_name", "")
        
        if not table_name:
            return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)
        
        col_lower = column_name.lower()
        
        # Check if column is identifier-like
        if not (col_lower.endswith('id') or col_lower.endswith('key')):
            return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)
        
        # Extract table root
        table_root = self._extract_table_root(table_name)
        
        # Check for exact root match
        if col_lower == f"{table_root}id":
            return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)

        # Allow prefix-root identifiers (defensive match for mildly varied naming).
        if col_lower.startswith(table_root) and (col_lower.endswith("id") or col_lower.endswith("key")):
            return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)
        
        # Check for generic standalone ID (allowed as potential PK)
        if col_lower == "id":
            return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)
        
        # Non-root identifier: suppress as PK, it's likely an FK
        return SuppressionResult(
            suppress=True,
            reason=f"Non-root identifier '{column_name}' in table '{table_name}' (root: '{table_root}') - likely FK",
            severity=SuppressionSeverity.HIGH
        )


# ---------------------------------------------------------------------------
# Suppression Engine
# ---------------------------------------------------------------------------

class PKSuppressionEngine:
    """
    Applies suppression rules and computes negative evidence.
    """
    
    def __init__(self, rules: Optional[List[PKSuppressionRule]] = None):
        if rules is None:
            # Default rule set with comprehensive suppression logic
            self.rules = [
                TemporalColumnSuppression(),           # Rule 1: Temporal/audit timestamps
                SystemAuditColumnSuppression(),        # Rule 2: System audit columns
                ConstantColumnSuppression(),           # Rule 3: Constant value columns
                LowCardinalitySuppression(min_distinct_threshold=100),  # Rule 4: Low cardinality
                ZeroEntropySuppression(min_entropy_threshold=0.01),     # Rule 5: Zero entropy
                SemanticInstabilitySuppression(),      # Rule 6: Names/descriptions
                TypeAffinityRule(),                    # Rule 7: Type preferences
                MeasureMetricSuppression(),            # Rule 8: Measures/metrics
                GeospatialFieldSuppression(),          # Rule 9: Geospatial data
                BooleanColumnSuppression(),            # Rule 10: Boolean/flag columns
                LowStabilityBusinessAttributeSuppression(),  # Rule 11: Phone/email/address
                NonRootIdentifierSuppression(),        # Rule 12: Non-root identifiers (FK candidates)
            ]
        else:
            self.rules = rules
    
    def apply_suppressions(self, column_data: dict) -> dict:
        """
        Apply all suppression rules and return results.
        
        Returns:
            {
                "should_suppress": bool,
                "suppressions": List[SuppressionResult],
                "critical_suppressions": List[SuppressionResult],
                "suppression_rules_applied": List[str],
                "negative_evidence": {
                    "temporal_column": bool,
                    "system_audit_column": bool,
                    "constant_column": bool,
                    "low_cardinality": bool,
                    "zero_entropy": bool,
                    "suppressions": List[str]
                }
            }
        """
        suppressions = []
        suppression_rules_applied = []
        
        # Apply each rule
        for rule in self.rules:
            result = rule.evaluate(column_data)
            
            if result.suppress:
                suppressions.append(result)
                log.warning(f"❌ {rule.name}: {result.reason}")
            
            # Track all rules applied (with pass/fail status)
            status = "FAILED" if result.suppress else "PASSED"
            suppression_rules_applied.append(f"{rule.name}: {status}")
        
        # Identify critical suppressions
        critical_suppressions = [
            s for s in suppressions if s.severity == SuppressionSeverity.CRITICAL
        ]
        
        # Build negative evidence
        negative_evidence = {
            "temporal_column": any("temporal" in s.reason.lower() for s in suppressions),
            "system_audit_column": any("audit" in s.reason.lower() for s in suppressions),
            "constant_column": any("constant" in s.reason.lower() for s in suppressions),
            "low_cardinality": any("cardinality" in s.reason.lower() for s in suppressions),
            "sentinel_value_detected": any("sentinel" in s.reason.lower() for s in suppressions),
            "semantically_unstable": any("unstable" in s.reason.lower() or "descriptive" in s.reason.lower() for s in suppressions),
            "low_type_affinity": any("affinity" in s.reason.lower() for s in suppressions),
            "measure_metric": any("measure" in s.reason.lower() or "metric" in s.reason.lower() for s in suppressions),
            "geospatial_field": any("geospatial" in s.reason.lower() or "coordinate" in s.reason.lower() for s in suppressions),
            "low_stability_business_attribute": any("mutability" in s.reason.lower() or "business attribute" in s.reason.lower() for s in suppressions),
            "composite_required": False,  # Future
            "suppressions": [
                f"❌ {s.severity.value.upper()}: {s.reason}"
                for s in suppressions
            ]
        }
        
        return {
            "should_suppress": len(critical_suppressions) > 0,
            "suppressions": suppressions,
            "critical_suppressions": critical_suppressions,
            "suppression_rules_applied": suppression_rules_applied,
            "negative_evidence": negative_evidence,
        }


# ---------------------------------------------------------------------------
# Default Suppression Engine Instance
# ---------------------------------------------------------------------------

# Global instance with default rules
default_suppression_engine = PKSuppressionEngine()


def apply_pk_suppressions(column_data: dict) -> dict:
    """
    Convenience function to apply default suppression rules.
    
    Args:
        column_data: Column statistics and metadata
        
    Returns:
        Suppression results dict
    """
    return default_suppression_engine.apply_suppressions(column_data)
