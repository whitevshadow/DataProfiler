"""
Foreign Key Detector

Distinguishes relational references (FKs) from entity anchors (PKs).

Key Principle:
    A column may be unique in a sample BUT still be a foreign key reference
    rather than a primary key anchor.

FK Detection Strategy:
    1. Naming pattern analysis (customerid, cityid, personid)
    2. Relational reference semantics
    3. Entity type inference
    4. Distinguish self-referential from cross-referential
"""

import re
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


log = logging.getLogger(__name__)


class RelationalRole(str, Enum):
    """Relational role classification for columns."""
    PRIMARY_KEY = "primary_key"
    FOREIGN_KEY = "foreign_key"
    ATTRIBUTE = "attribute"
    AUDIT_FIELD = "audit_field"
    TEMPORAL_FIELD = "temporal_field"
    MEASURE = "measure"
    DIMENSION = "dimension"
    GEO_FIELD = "geo_field"
    UNKNOWN = "unknown"


class LogicalType(str, Enum):
    """Logical type classification."""
    IDENTIFIER = "identifier"
    MEASURE = "measure"
    DIMENSION = "dimension"
    TIMESTAMP = "timestamp"
    AUDIT = "audit"
    CATEGORY = "category"
    REFERENCE = "reference"
    DESCRIPTION = "description"
    GEOSPATIAL = "geospatial"
    CONTACT = "contact"
    UNKNOWN = "unknown"


@dataclass
class FKEvidence:
    """Evidence supporting FK classification."""
    fk_confidence: float
    is_fk_candidate: bool
    referenced_entity: Optional[str]
    fk_pattern_match: float
    entity_mismatch_score: float
    reasoning: List[str]
    warnings: List[str]


@dataclass
class RelationalClassification:
    """Complete relational role classification."""
    relational_role: RelationalRole
    logical_type: LogicalType
    confidence: float
    reasoning: List[str]


# ---------------------------------------------------------------------------
# FK Detection Patterns
# ---------------------------------------------------------------------------

class FKPatternDetector:
    """Detect foreign key patterns in column names."""
    
    # Common FK naming patterns
    FK_PATTERNS = [
        # Explicit FK patterns
        r'^(.+)id$',           # customerid, cityid, personid
        r'^(.+)_id$',          # customer_id, city_id
        r'^fk_(.+)$',          # fk_customer, fk_city
        
        # Reference patterns
        r'^(.+)ref$',          # customerref
        r'^(.+)_ref$',         # customer_ref
        r'^(.+)key$',          # customerkey
        r'^(.+)_key$',         # customer_key
    ]
    
    # Self-referential patterns (likely PK, not FK)
    SELF_REFERENTIAL_PATTERNS = [
        r'^id$',
        r'^(.+)id$',  # If entity name matches table name
    ]
    
    @staticmethod
    def extract_referenced_entity(column_name: str, table_name: str) -> Optional[Tuple[str, float]]:
        """
        Extract referenced entity name and confidence.
        
        Returns:
            (entity_name, confidence) or None
        """
        column_lower = column_name.lower()
        table_lower = table_name.lower() if table_name else ""
        
        # Check for explicit FK patterns
        for pattern in FKPatternDetector.FK_PATTERNS:
            match = re.match(pattern, column_lower)
            if match:
                entity = match.group(1)
                
                # Check if self-referential (likely PK)
                if entity == table_lower or entity == table_lower.rstrip('s'):
                    return None  # Self-referential, likely PK
                
                # Check if entity name is meaningful
                if len(entity) > 2:  # Avoid single-letter matches
                    confidence = 0.9 if 'id' in pattern else 0.7
                    return (entity, confidence)
        
        return None
    
    @staticmethod
    def is_self_referential(column_name: str, table_name: str) -> bool:
        """Check if column is self-referential (likely PK, not FK)."""
        if not table_name:
            return False
        
        column_lower = column_name.lower()
        table_lower = table_name.lower()
        
        # Remove common prefixes/suffixes for matching
        table_clean = table_lower.replace("application_", "").replace("sales_", "").replace("warehouse_", "").replace("purchasing_", "")
        
        # Extract entity name from column (remove 'id' suffix)
        if column_lower.endswith("id"):
            column_entity = column_lower[:-2]  # Remove 'id'
        elif column_lower.endswith("_id"):
            column_entity = column_lower[:-3]  # Remove '_id'
        else:
            column_entity = column_lower
        
        # Normalize table name (remove common plural suffixes)
        table_variants = [
            table_clean,
            table_clean.rstrip('s'),  # customers → customer
            table_clean.rstrip('es'),  # cities → citi
            table_clean.rstrip('ies') + 'y' if table_clean.endswith('ies') else table_clean,  # cities → city
        ]
        
        # Check if column entity matches any table variant
        for table_variant in table_variants:
            if column_entity == table_variant:
                return True
            # Also check if table matches column + s/es
            if table_clean == column_entity + 's' or table_clean == column_entity + 'es':
                return True
        
        # Exact match: id column
        if column_lower == "id":
            return True
        
        return False


# ---------------------------------------------------------------------------
# FK Detector
# ---------------------------------------------------------------------------

class FKDetector:
    """Detect foreign key candidates using semantic and statistical evidence."""
    
    def __init__(self):
        self.pattern_detector = FKPatternDetector()
    
    def compute_fk_score(
        self,
        column_name: str,
        table_name: Optional[str],
        physical_type: str,
        uniqueness_ratio: float,
        null_ratio: float,
        entropy_normalized: float,
        is_pk_candidate: bool,
        pk_confidence: float,
    ) -> FKEvidence:
        """
        Compute FK confidence score and evidence.
        
        FK Detection Logic:
            1. Check naming patterns for FK references
            2. If self-referential → likely PK, not FK
            3. If cross-referential + high uniqueness → likely FK
            4. Distinguish entity anchor from relational reference
        
        Args:
            column_name: Normalized column name
            table_name: Table name (for self-referential detection)
            physical_type: Physical data type
            uniqueness_ratio: Uniqueness ratio (0.0 - 1.0)
            null_ratio: Null ratio (0.0 - 1.0)
            entropy_normalized: Normalized entropy (0.0 - 1.0)
            is_pk_candidate: Whether column is flagged as PK candidate
            pk_confidence: PK confidence score
        
        Returns:
            FKEvidence with confidence and reasoning
        """
        reasoning = []
        warnings = []
        
        # Check if self-referential (entity anchor, not FK)
        if self.pattern_detector.is_self_referential(column_name, table_name):
            return FKEvidence(
                fk_confidence=0.0,
                is_fk_candidate=False,
                referenced_entity=None,
                fk_pattern_match=0.0,
                entity_mismatch_score=0.0,
                reasoning=["Self-referential identifier - likely PRIMARY KEY, not FK"],
                warnings=[]
            )
        
        # Extract referenced entity
        entity_match = self.pattern_detector.extract_referenced_entity(column_name, table_name)
        
        if entity_match is None:
            # No FK pattern detected
            return FKEvidence(
                fk_confidence=0.0,
                is_fk_candidate=False,
                referenced_entity=None,
                fk_pattern_match=0.0,
                entity_mismatch_score=0.0,
                reasoning=["No FK naming pattern detected"],
                warnings=[]
            )
        
        referenced_entity, pattern_confidence = entity_match
        
        # FK pattern detected - compute confidence
        reasoning.append(f"FK pattern detected: references '{referenced_entity}' entity")
        
        # Compute FK confidence components
        fk_pattern_score = pattern_confidence
        
        # Type affinity (FKs are typically INTEGER/UUID)
        type_affinity = 0.9 if physical_type in ["INTEGER", "UUID"] else 0.5
        
        # Entropy (FKs may have lower entropy than PKs due to reuse)
        entropy_score = min(entropy_normalized, 0.8)  # FKs often have moderate entropy
        
        # Non-null score (FKs may have nulls, unlike PKs)
        non_null_score = 1.0 - null_ratio
        
        # Uniqueness penalty (FKs are often NOT unique in full table)
        # High uniqueness in sample may be misleading
        if uniqueness_ratio > 0.95:
            warnings.append("High uniqueness in sample - may be unique FK or small sample size")
        
        # Compute weighted FK confidence
        fk_confidence = (
            fk_pattern_score * 0.50 +      # FK naming is strongest signal
            type_affinity * 0.20 +         # Type matters
            entropy_score * 0.15 +         # Moderate entropy expected
            non_null_score * 0.15          # Non-null preferred but not required
        )
        
        # Entity mismatch score (cross-reference vs self-reference)
        entity_mismatch_score = 1.0  # Cross-referential
        
        # Build reasoning
        reasoning.append(f"FK naming pattern confidence: {fk_pattern_score:.2f}")
        reasoning.append(f"References external entity: {referenced_entity}")
        reasoning.append(f"Type affinity (INTEGER/UUID preferred): {type_affinity:.2f}")
        
        if uniqueness_ratio > 0.95:
            reasoning.append(f"High uniqueness ({uniqueness_ratio:.2%}) - likely unique FK or small sample")
        else:
            reasoning.append(f"Moderate uniqueness ({uniqueness_ratio:.2%}) - typical FK pattern")
        
        # Determine FK candidacy
        is_fk_candidate = (
            fk_confidence >= 0.70 and
            entity_mismatch_score > 0.5  # Cross-referential
        )
        
        return FKEvidence(
            fk_confidence=fk_confidence,
            is_fk_candidate=is_fk_candidate,
            referenced_entity=referenced_entity,
            fk_pattern_match=fk_pattern_score,
            entity_mismatch_score=entity_mismatch_score,
            reasoning=reasoning,
            warnings=warnings
        )


# ---------------------------------------------------------------------------
# Relational Role Classifier
# ---------------------------------------------------------------------------

class RelationalRoleClassifier:
    """Classify columns into relational roles."""
    
    @staticmethod
    def classify_role(
        column_name: str,
        physical_type: str,
        is_pk_candidate: bool,
        is_fk_candidate: bool,
        pk_confidence: float,
        fk_confidence: float,
        is_temporal: bool,
        is_audit: bool,
        is_measure: bool,
        is_geospatial: bool,
    ) -> RelationalClassification:
        """
        Classify column into relational role.
        
        Priority order:
            1. PRIMARY_KEY (self-referential identifier)
            2. FOREIGN_KEY (cross-referential identifier)
            3. AUDIT_FIELD (system audit columns)
            4. TEMPORAL_FIELD (timestamps)
            5. MEASURE (numeric aggregates)
            6. GEO_FIELD (geospatial data)
            7. DIMENSION (categorical attributes)
            8. ATTRIBUTE (descriptive fields)
        """
        reasoning = []
        
        # Rule 1: PRIMARY_KEY takes precedence over FK ONLY if clearly self-referential
        if is_pk_candidate and pk_confidence >= 0.70:
            if is_fk_candidate:
                # Both PK and FK patterns - disambiguate based on entity context
                # If FK confidence is high and it's cross-referential, treat as FK
                if fk_confidence >= 0.85 and pk_confidence - fk_confidence < 0.10:
                    # Close scores + high FK confidence = FK wins
                    return RelationalClassification(
                        relational_role=RelationalRole.FOREIGN_KEY,
                        logical_type=LogicalType.REFERENCE,
                        confidence=fk_confidence,
                        reasoning=[
                            f"Foreign key (FK confidence {fk_confidence:.2f}, PK confidence {pk_confidence:.2f})",
                            "Cross-referential pattern detected - likely FK, not entity anchor",
                            "Relational reference to external entity"
                        ]
                    )
                elif pk_confidence > fk_confidence + 0.10:
                    # PK significantly stronger
                    return RelationalClassification(
                        relational_role=RelationalRole.PRIMARY_KEY,
                        logical_type=LogicalType.IDENTIFIER,
                        confidence=pk_confidence,
                        reasoning=[
                            f"Primary key (PK confidence {pk_confidence:.2f} > FK confidence {fk_confidence:.2f})",
                            "Entity anchor for this table"
                        ]
                    )
                else:
                    # Ambiguous - default to FK for cross-references
                    return RelationalClassification(
                        relational_role=RelationalRole.FOREIGN_KEY,
                        logical_type=LogicalType.REFERENCE,
                        confidence=fk_confidence,
                        reasoning=[
                            f"Foreign key (ambiguous: PK={pk_confidence:.2f}, FK={fk_confidence:.2f})",
                            "Defaulting to FK for cross-referential pattern"
                        ]
                    )
            else:
                return RelationalClassification(
                    relational_role=RelationalRole.PRIMARY_KEY,
                    logical_type=LogicalType.IDENTIFIER,
                    confidence=pk_confidence,
                    reasoning=[
                        f"Primary key (confidence: {pk_confidence:.2f})",
                        "Entity anchor for this table"
                    ]
                )
        
        # Rule 2: FOREIGN_KEY
        if is_fk_candidate and fk_confidence >= 0.70:
            return RelationalClassification(
                relational_role=RelationalRole.FOREIGN_KEY,
                logical_type=LogicalType.REFERENCE,
                confidence=fk_confidence,
                reasoning=[
                    f"Foreign key (confidence: {fk_confidence:.2f})",
                    "Relational reference to external entity"
                ]
            )
        
        # Rule 3: AUDIT_FIELD
        if is_audit:
            return RelationalClassification(
                relational_role=RelationalRole.AUDIT_FIELD,
                logical_type=LogicalType.AUDIT,
                confidence=1.0,
                reasoning=["System audit column", "Tracks data lineage and modifications"]
            )
        
        # Rule 4: TEMPORAL_FIELD
        if is_temporal:
            return RelationalClassification(
                relational_role=RelationalRole.TEMPORAL_FIELD,
                logical_type=LogicalType.TIMESTAMP,
                confidence=1.0,
                reasoning=["Temporal/timestamp column", "Tracks temporal validity"]
            )
        
        # Rule 5: MEASURE
        if is_measure:
            return RelationalClassification(
                relational_role=RelationalRole.MEASURE,
                logical_type=LogicalType.MEASURE,
                confidence=0.9,
                reasoning=["Numeric measure/metric", "Aggregable business value"]
            )
        
        # Rule 6: GEO_FIELD
        if is_geospatial:
            return RelationalClassification(
                relational_role=RelationalRole.GEO_FIELD,
                logical_type=LogicalType.GEOSPATIAL,
                confidence=1.0,
                reasoning=["Geospatial field", "Contains location/coordinate data"]
            )
        
        # Rule 7: DIMENSION (categorical attributes)
        if physical_type == "STRING":
            return RelationalClassification(
                relational_role=RelationalRole.DIMENSION,
                logical_type=LogicalType.CATEGORY,
                confidence=0.7,
                reasoning=["String attribute", "Likely categorical dimension"]
            )
        
        # Rule 8: ATTRIBUTE (default)
        return RelationalClassification(
            relational_role=RelationalRole.ATTRIBUTE,
            logical_type=LogicalType.UNKNOWN,
            confidence=0.5,
            reasoning=["General attribute", "No specific role detected"]
        )


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------

def detect_foreign_key(
    column_name: str,
    table_name: Optional[str],
    physical_type: str,
    uniqueness_ratio: float,
    null_ratio: float,
    entropy_normalized: float,
    is_pk_candidate: bool,
    pk_confidence: float,
) -> FKEvidence:
    """Convenience function for FK detection."""
    detector = FKDetector()
    return detector.compute_fk_score(
        column_name=column_name,
        table_name=table_name,
        physical_type=physical_type,
        uniqueness_ratio=uniqueness_ratio,
        null_ratio=null_ratio,
        entropy_normalized=entropy_normalized,
        is_pk_candidate=is_pk_candidate,
        pk_confidence=pk_confidence,
    )


def classify_relational_role(
    column_name: str,
    physical_type: str,
    is_pk_candidate: bool,
    is_fk_candidate: bool,
    pk_confidence: float,
    fk_confidence: float,
    is_temporal: bool = False,
    is_audit: bool = False,
    is_measure: bool = False,
    is_geospatial: bool = False,
) -> RelationalClassification:
    """Convenience function for relational role classification."""
    return RelationalRoleClassifier.classify_role(
        column_name=column_name,
        physical_type=physical_type,
        is_pk_candidate=is_pk_candidate,
        is_fk_candidate=is_fk_candidate,
        pk_confidence=pk_confidence,
        fk_confidence=fk_confidence,
        is_temporal=is_temporal,
        is_audit=is_audit,
        is_measure=is_measure,
        is_geospatial=is_geospatial,
    )
