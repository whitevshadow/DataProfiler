"""
Type Compatibility Engine

Determines whether two columns can form a valid FK->PK relationship
based on their physical data types.

Core Principles:
- Reject impossible type pairings early (e.g., STRING <-> BOOLEAN)
- Support type coercion where semantically valid (e.g., INTEGER <-> BIGINT)
- Provide compatibility scores, not just binary yes/no
- Normalize UUIDs and handle string representations

Type Compatibility Matrix:
    INTEGER ↔ INTEGER: 1.0 (exact match)
    INTEGER ↔ BIGINT: 0.9 (coercion, safe)
    INTEGER ↔ STRING: 0.3 (possible if string contains integers)
    STRING ↔ STRING: 1.0 (exact match)
    UUID ↔ UUID: 1.0 (exact match)
    UUID ↔ STRING: 0.8 (coercion, common)
    BOOLEAN ↔ INTEGER: 0.0 (reject)
    TIMESTAMP ↔ DATE: 0.7 (coercion)
"""

from typing import Dict, Set, Tuple
from relationships.relationship_models import TypeCompatibilityResult, PhysicalType


class TypeCompatibilityEngine:
    """
    Engine for determining type compatibility between FK and PK columns.
    
    Uses a compatibility matrix with explicit rules for each type pair.
    """
    
    def __init__(self):
        """Initialize the type compatibility engine."""
        self.compatibility_matrix = self._build_compatibility_matrix()
        self.coercion_rules = self._build_coercion_rules()
    
    def check_compatibility(
        self,
        fk_type: str,
        pk_type: str,
    ) -> TypeCompatibilityResult:
        """
        Check if FK type is compatible with PK type.
        
        Args:
            fk_type: Physical type of FK column
            pk_type: Physical type of PK column
        
        Returns:
            TypeCompatibilityResult with compatibility score and reasoning
        """
        # Normalize types
        fk_type_normalized = self._normalize_type(fk_type)
        pk_type_normalized = self._normalize_type(pk_type)
        
        # Check exact match first
        if fk_type_normalized == pk_type_normalized:
            return TypeCompatibilityResult(
                compatible=True,
                compatibility_score=1.0,
                coercion_required=False,
                reasoning=f"Exact type match: {fk_type_normalized}",
            )
        
        # Check compatibility matrix
        pair_key = (fk_type_normalized, pk_type_normalized)
        if pair_key in self.compatibility_matrix:
            score, coercion_required = self.compatibility_matrix[pair_key]
            compatible = score >= 0.5  # Threshold for compatibility
            
            coercion_strategy = None
            if coercion_required:
                coercion_strategy = self.coercion_rules.get(pair_key, "automatic")
            
            reasoning = self._build_reasoning(
                fk_type_normalized,
                pk_type_normalized,
                score,
                coercion_required,
            )
            
            return TypeCompatibilityResult(
                compatible=compatible,
                compatibility_score=score,
                coercion_required=coercion_required,
                coercion_strategy=coercion_strategy,
                reasoning=reasoning,
            )
        
        # Unknown type pair - conservative rejection
        return TypeCompatibilityResult(
            compatible=False,
            compatibility_score=0.0,
            reasoning=f"Unknown type pair: {fk_type_normalized} <-> {pk_type_normalized}",
        )
    
    def _normalize_type(self, type_str: str) -> str:
        """Normalize type string to standard form."""
        type_upper = type_str.upper().strip()
        
        # Map variants to canonical forms
        type_mappings = {
            "INT": "INTEGER",
            "INT64": "BIGINT",
            "LONG": "BIGINT",
            "FLOAT64": "DOUBLE",
            "VARCHAR": "STRING",
            "TEXT": "STRING",
            "CHAR": "STRING",
            "DATETIME": "TIMESTAMP",
            "TIMESTAMP_MS": "TIMESTAMP",
            "TIMESTAMP_NS": "TIMESTAMP",
            "BOOL": "BOOLEAN",
        }
        
        return type_mappings.get(type_upper, type_upper)
    
    def _build_compatibility_matrix(self) -> Dict[Tuple[str, str], Tuple[float, bool]]:
        """
        Build type compatibility matrix.
        
        Returns:
            Dict mapping (fk_type, pk_type) -> (compatibility_score, coercion_required)
        """
        matrix = {}
        
        # INTEGER family
        matrix[("INTEGER", "BIGINT")] = (0.95, True)
        matrix[("INTEGER", "FLOAT")] = (0.7, True)
        matrix[("INTEGER", "DOUBLE")] = (0.7, True)
        matrix[("INTEGER", "STRING")] = (0.3, True)  # Possible if string contains integers
        matrix[("INTEGER", "DECIMAL")] = (0.8, True)
        
        matrix[("BIGINT", "INTEGER")] = (0.85, True)  # Risky if values exceed INT range
        matrix[("BIGINT", "FLOAT")] = (0.6, True)
        matrix[("BIGINT", "DOUBLE")] = (0.7, True)
        matrix[("BIGINT", "STRING")] = (0.3, True)
        matrix[("BIGINT", "DECIMAL")] = (0.8, True)
        
        # FLOAT/DOUBLE family
        matrix[("FLOAT", "DOUBLE")] = (0.95, False)
        matrix[("DOUBLE", "FLOAT")] = (0.9, True)  # Precision loss
        matrix[("FLOAT", "INTEGER")] = (0.5, True)
        matrix[("FLOAT", "STRING")] = (0.3, True)
        matrix[("DOUBLE", "INTEGER")] = (0.5, True)
        matrix[("DOUBLE", "STRING")] = (0.3, True)
        
        # STRING family
        matrix[("STRING", "INTEGER")] = (0.2, True)  # Rarely valid
        matrix[("STRING", "BIGINT")] = (0.2, True)
        matrix[("STRING", "UUID")] = (0.85, False)  # Common: UUID stored as string
        matrix[("STRING", "DATE")] = (0.4, True)
        matrix[("STRING", "TIMESTAMP")] = (0.4, True)
        
        # UUID family
        matrix[("UUID", "STRING")] = (0.9, False)  # Very common
        matrix[("STRING", "UUID")] = (0.85, False)
        
        # DATE/TIMESTAMP family
        matrix[("DATE", "TIMESTAMP")] = (0.85, True)
        matrix[("TIMESTAMP", "DATE")] = (0.75, True)  # Precision loss
        matrix[("DATE", "STRING")] = (0.4, True)
        matrix[("TIMESTAMP", "STRING")] = (0.4, True)
        
        # DECIMAL family
        matrix[("DECIMAL", "INTEGER")] = (0.7, True)
        matrix[("DECIMAL", "BIGINT")] = (0.7, True)
        matrix[("DECIMAL", "FLOAT")] = (0.8, True)
        matrix[("DECIMAL", "DOUBLE")] = (0.85, True)
        matrix[("DECIMAL", "STRING")] = (0.3, True)
        
        # BOOLEAN - mostly incompatible
        matrix[("BOOLEAN", "INTEGER")] = (0.2, True)  # 0/1 encoding
        matrix[("BOOLEAN", "STRING")] = (0.2, True)  # "true"/"false"
        matrix[("INTEGER", "BOOLEAN")] = (0.1, True)  # Unlikely FK relationship
        
        # JSON/ARRAY - generally incompatible for FK relationships
        matrix[("JSON", "STRING")] = (0.3, True)
        matrix[("ARRAY", "STRING")] = (0.2, True)
        
        return matrix
    
    def _build_coercion_rules(self) -> Dict[Tuple[str, str], str]:
        """
        Build coercion strategy rules.
        
        Returns:
            Dict mapping (fk_type, pk_type) -> coercion_strategy
        """
        return {
            ("INTEGER", "BIGINT"): "cast_to_bigint",
            ("BIGINT", "INTEGER"): "safe_cast_check_overflow",
            ("INTEGER", "STRING"): "cast_to_string",
            ("STRING", "UUID"): "parse_uuid",
            ("UUID", "STRING"): "uuid_to_string",
            ("DATE", "TIMESTAMP"): "date_to_timestamp",
            ("TIMESTAMP", "DATE"): "truncate_to_date",
            ("FLOAT", "DOUBLE"): "promote_precision",
            ("DOUBLE", "FLOAT"): "reduce_precision",
        }
    
    def _build_reasoning(
        self,
        fk_type: str,
        pk_type: str,
        score: float,
        coercion_required: bool,
    ) -> str:
        """Build human-readable reasoning for compatibility decision."""
        if score >= 0.9:
            reason = f"Highly compatible: {fk_type} → {pk_type}"
        elif score >= 0.7:
            reason = f"Compatible with {'coercion' if coercion_required else 'minor adjustment'}: {fk_type} → {pk_type}"
        elif score >= 0.5:
            reason = f"Marginally compatible: {fk_type} → {pk_type} (requires validation)"
        elif score >= 0.3:
            reason = f"Low compatibility: {fk_type} → {pk_type} (risky)"
        else:
            reason = f"Incompatible: {fk_type} ↮ {pk_type}"
        
        if coercion_required and score >= 0.5:
            reason += " (coercion required)"
        
        return reason
    
    def get_compatible_type_families(self, base_type: str) -> Set[str]:
        """
        Get all types compatible with the given base type.
        
        Args:
            base_type: The type to find compatible types for
        
        Returns:
            Set of compatible type strings
        """
        normalized = self._normalize_type(base_type)
        compatible = {normalized}  # Always compatible with self
        
        for (fk_type, pk_type), (score, _) in self.compatibility_matrix.items():
            if pk_type == normalized and score >= 0.5:
                compatible.add(fk_type)
            if fk_type == normalized and score >= 0.5:
                compatible.add(pk_type)
        
        return compatible


# Singleton instance for reuse
_type_compatibility_engine = TypeCompatibilityEngine()


def check_type_compatibility(fk_type: str, pk_type: str) -> TypeCompatibilityResult:
    """
    Convenience function to check type compatibility.
    
    Args:
        fk_type: Physical type of FK column
        pk_type: Physical type of PK column
    
    Returns:
        TypeCompatibilityResult with compatibility assessment
    """
    return _type_compatibility_engine.check_compatibility(fk_type, pk_type)


def get_compatible_types(base_type: str) -> Set[str]:
    """
    Get all types compatible with the given base type.
    
    Args:
        base_type: The type to find compatible types for
    
    Returns:
        Set of compatible type strings
    """
    return _type_compatibility_engine.get_compatible_type_families(base_type)
