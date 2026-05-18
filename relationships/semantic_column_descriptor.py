"""
Semantic Column Description Generator

Generates rich semantic descriptions for columns based on:
- Column name patterns
- Data type
- Statistical properties
- Sample values
- Identifier characteristics
- Relationship hints

Descriptions are deterministic, structured, and semantically informative.

Core Principle:
    Descriptions encode business meaning, semantic role, and relationship hints
    for downstream ANN/embedding-based candidate retrieval.
"""

from typing import Dict, List, Any, Optional
import re
from dataclasses import dataclass


@dataclass
class ColumnDescription:
    """Rich semantic description of a column."""
    column_name: str
    table_name: str
    semantic_role: str  # "identifier", "measure", "dimension", "temporal", "audit"
    business_meaning: str
    identifier_type: Optional[str] = None  # "primary", "foreign", "natural", "surrogate"
    entity_reference: Optional[str] = None  # Referenced entity name
    relationship_hints: List[str] = None
    statistical_summary: str = ""
    data_examples: List[str] = None
    
    def to_embedding_text(self) -> str:
        """
        Generate embedding-friendly text representation.
        
        This text will be embedded for ANN similarity search.
        """
        parts = [
            f"Column: {self.column_name}",
            f"Table: {self.table_name}",
            f"Role: {self.semantic_role}",
            f"Meaning: {self.business_meaning}",
        ]
        
        if self.identifier_type:
            parts.append(f"Identifier: {self.identifier_type}")
        
        if self.entity_reference:
            parts.append(f"References: {self.entity_reference}")
        
        if self.relationship_hints:
            parts.append(f"Hints: {', '.join(self.relationship_hints)}")
        
        if self.statistical_summary:
            parts.append(f"Stats: {self.statistical_summary}")
        
        if self.data_examples:
            examples = ', '.join(str(ex) for ex in self.data_examples[:5])
            parts.append(f"Examples: {examples}")
        
        return " | ".join(parts)


class SemanticColumnDescriptor:
    """
    Generates semantic descriptions for columns.
    
    Uses pattern matching, statistical analysis, and heuristics
    to infer business meaning and relationship hints.
    """
    
    def __init__(self):
        """Initialize semantic descriptor."""
        self.identifier_patterns = self._build_identifier_patterns()
        self.measure_patterns = self._build_measure_patterns()
        self.temporal_patterns = self._build_temporal_patterns()
        self.audit_patterns = self._build_audit_patterns()
        self.dimension_patterns = self._build_dimension_patterns()
    
    def generate_description(
        self,
        column_name: str,
        table_name: str,
        column_profile: Dict[str, Any],
        is_pk_candidate: bool = False,
    ) -> ColumnDescription:
        """
        Generate semantic description for a column.
        
        Args:
            column_name: Column name
            table_name: Table name
            column_profile: Column statistics (distinct_count, null_ratio, etc.)
            is_pk_candidate: Whether column is a PK candidate
        
        Returns:
            ColumnDescription with rich semantic information
        """
        col_lower = column_name.lower()
        
        # Determine semantic role
        semantic_role = self._infer_semantic_role(
            col_lower, column_profile, is_pk_candidate
        )
        
        # Generate business meaning
        business_meaning = self._generate_business_meaning(
            column_name, table_name, semantic_role, column_profile
        )
        
        # Infer identifier type
        identifier_type = None
        entity_reference = None
        if semantic_role == "identifier":
            identifier_type = self._infer_identifier_type(
                col_lower, table_name, is_pk_candidate, column_profile
            )
            entity_reference = self._extract_entity_reference(
                col_lower, table_name
            )
        
        # Generate relationship hints
        relationship_hints = self._generate_relationship_hints(
            column_name, table_name, semantic_role, identifier_type, entity_reference
        )
        
        # Statistical summary
        statistical_summary = self._generate_statistical_summary(column_profile)
        
        # Data examples
        data_examples = column_profile.get("sample_values", [])[:5]
        
        return ColumnDescription(
            column_name=column_name,
            table_name=table_name,
            semantic_role=semantic_role,
            business_meaning=business_meaning,
            identifier_type=identifier_type,
            entity_reference=entity_reference,
            relationship_hints=relationship_hints,
            statistical_summary=statistical_summary,
            data_examples=data_examples,
        )
    
    def _infer_semantic_role(
        self,
        col_lower: str,
        profile: Dict[str, Any],
        is_pk_candidate: bool,
    ) -> str:
        """Infer semantic role: identifier, measure, dimension, temporal, audit."""
        
        # Check temporal patterns
        if self._matches_pattern(col_lower, self.temporal_patterns):
            return "temporal"
        
        # Check audit patterns
        if self._matches_pattern(col_lower, self.audit_patterns):
            return "audit"
        
        # Check identifier patterns
        if self._matches_pattern(col_lower, self.identifier_patterns):
            return "identifier"
        
        # Check measure patterns
        if self._matches_pattern(col_lower, self.measure_patterns):
            return "measure"
        
        # Check dimension patterns
        if self._matches_pattern(col_lower, self.dimension_patterns):
            return "dimension"
        
        # Statistical heuristics
        physical_type = profile.get("physical_type", "").upper()
        distinct_count = profile.get("distinct_count", 0)
        row_count = profile.get("row_count", 1)
        
        # High uniqueness → identifier
        if row_count > 0:
            uniqueness = distinct_count / row_count
            if uniqueness > 0.95 and physical_type in ["INTEGER", "BIGINT", "UUID", "STRING"]:
                return "identifier"
        
        # Numeric + high variation → measure
        if physical_type in ["FLOAT", "DOUBLE", "DECIMAL"] and distinct_count > 100:
            return "measure"
        
        # Low cardinality → dimension
        if distinct_count < 100:
            return "dimension"
        
        return "attribute"
    
    def _generate_business_meaning(
        self,
        column_name: str,
        table_name: str,
        semantic_role: str,
        profile: Dict[str, Any],
    ) -> str:
        """Generate business meaning description."""
        
        col_lower = column_name.lower()
        physical_type = profile.get("physical_type", "UNKNOWN")
        distinct_count = profile.get("distinct_count", 0)
        
        if semantic_role == "identifier":
            entity = self._extract_entity_reference(col_lower, table_name)
            if entity:
                if self._is_self_referential(entity, table_name):
                    return f"Stable {physical_type} identifier representing {table_name} entities. Acts as primary entity anchor."
                else:
                    return f"Foreign reference identifier pointing to {entity} entity. Links {table_name} records to {entity} table."
            else:
                return f"Unique {physical_type} identifier with {distinct_count} distinct values."
        
        elif semantic_role == "temporal":
            if "valid" in col_lower:
                return "Temporal audit timestamp indicating record validity period for slowly changing dimensions."
            elif "created" in col_lower:
                return "System timestamp recording when the record was initially created."
            elif "updated" in col_lower or "modified" in col_lower:
                return "System timestamp tracking most recent record modification."
            else:
                return "Temporal field tracking time-based information."
        
        elif semantic_role == "audit":
            if "edited" in col_lower or "updated" in col_lower:
                return "Audit field recording user identity who last modified the record."
            elif "created" in col_lower:
                return "Audit field recording user identity who created the record."
            else:
                return "System audit field tracking metadata changes."
        
        elif semantic_role == "measure":
            return f"Numeric measure/metric field ({physical_type}) representing quantitative business data with {distinct_count} distinct values."
        
        elif semantic_role == "dimension":
            return f"Categorical dimension field with {distinct_count} distinct categories for grouping and filtering."
        
        else:
            return f"{physical_type} attribute field with {distinct_count} distinct values."
    
    def _infer_identifier_type(
        self,
        col_lower: str,
        table_name: str,
        is_pk_candidate: bool,
        profile: Dict[str, Any],
    ) -> str:
        """Infer identifier type: primary, foreign, natural, surrogate."""
        
        entity = self._extract_entity_reference(col_lower, table_name)
        
        # Self-referential → likely primary
        if entity and self._is_self_referential(entity, table_name):
            if is_pk_candidate:
                return "primary_surrogate" if "id" in col_lower else "primary_natural"
            else:
                return "candidate_primary"
        
        # Cross-referential → likely foreign
        if entity and not self._is_self_referential(entity, table_name):
            return "foreign_reference"
        
        # High uniqueness + PK candidate → primary
        row_count = profile.get("row_count", 1)
        distinct_count = profile.get("distinct_count", 0)
        if row_count > 0:
            uniqueness = distinct_count / row_count
            if uniqueness > 0.99 and is_pk_candidate:
                return "primary_surrogate"
        
        return "identifier"
    
    def _extract_entity_reference(
        self,
        col_lower: str,
        table_name: str,
    ) -> Optional[str]:
        """Extract referenced entity name from column."""
        
        # Remove common suffixes
        entity = col_lower
        for suffix in ["_id", "id", "_key", "key", "_fk", "fk", "_no", "no"]:
            if entity.endswith(suffix):
                entity = entity[:-len(suffix)]
                break
        
        # Remove prefixes (delivery_city_id → city)
        if "_" in entity:
            parts = entity.split("_")
            # Take last meaningful part
            entity = parts[-1] if parts else entity
        
        if entity and len(entity) > 2:
            return entity
        
        return None
    
    def _is_self_referential(self, entity: str, table_name: str) -> bool:
        """Check if entity matches table name."""
        table_normalized = self._normalize_table_name(table_name)
        return entity == table_normalized
    
    def _normalize_table_name(self, table_name: str) -> str:
        """Normalize table name for matching."""
        name = table_name.lower()
        
        # Remove prefixes
        for prefix in ["application_", "sales_", "purchasing_", "warehouse_"]:
            if name.startswith(prefix):
                name = name[len(prefix):]
        
        # Handle plurals
        if name.endswith("ies"):
            name = name[:-3] + "y"
        elif name.endswith("es"):
            name = name[:-2]
        elif name.endswith("s"):
            name = name[:-1]
        
        return name
    
    def _generate_relationship_hints(
        self,
        column_name: str,
        table_name: str,
        semantic_role: str,
        identifier_type: Optional[str],
        entity_reference: Optional[str],
    ) -> List[str]:
        """Generate relationship hints for embedding."""
        
        hints = []
        
        if semantic_role == "identifier":
            if identifier_type == "primary_surrogate" or identifier_type == "primary_natural":
                hints.append(f"primary_key_for_{self._normalize_table_name(table_name)}")
            
            if identifier_type == "foreign_reference" and entity_reference:
                hints.append(f"references_{entity_reference}_entity")
                hints.append(f"foreign_key_to_{entity_reference}")
        
        if semantic_role == "temporal":
            hints.append("temporal_audit_field")
            hints.append("not_suitable_for_relationships")
        
        if semantic_role == "audit":
            hints.append("audit_metadata_field")
            hints.append("not_suitable_for_relationships")
        
        if semantic_role == "measure":
            hints.append("quantitative_measure")
            hints.append("not_suitable_for_relationships")
        
        return hints
    
    def _generate_statistical_summary(self, profile: Dict[str, Any]) -> str:
        """Generate statistical summary."""
        distinct = profile.get("distinct_count", 0)
        null_ratio = profile.get("null_ratio", 0.0)
        row_count = profile.get("row_count", 0)
        
        parts = [f"{distinct} distinct"]
        
        if null_ratio > 0:
            parts.append(f"{null_ratio*100:.1f}% null")
        
        if row_count > 0 and distinct > 0:
            uniqueness = distinct / row_count
            if uniqueness > 0.95:
                parts.append("highly unique")
            elif uniqueness < 0.1:
                parts.append("low cardinality")
        
        return ", ".join(parts)
    
    def _matches_pattern(self, text: str, patterns: List[str]) -> bool:
        """Check if text matches any pattern."""
        return any(re.search(pattern, text) for pattern in patterns)
    
    def _build_identifier_patterns(self) -> List[str]:
        """Build identifier field patterns."""
        return [
            r".*id$",
            r".*_id$",
            r".*key$",
            r".*_key$",
            r".*no$",
            r".*_no$",
            r".*number$",
            r".*code$",
        ]
    
    def _build_measure_patterns(self) -> List[str]:
        """Build measure/metric field patterns."""
        return [
            r".*amount",
            r".*price",
            r".*cost",
            r".*quantity",
            r".*population",
            r".*count",
            r".*total",
            r".*sum",
            r".*score",
            r".*balance",
            r".*value",
        ]
    
    def _build_temporal_patterns(self) -> List[str]:
        """Build temporal field patterns."""
        return [
            r".*date",
            r".*time",
            r"created.*at",
            r"updated.*at",
            r"modified.*at",
            r"valid.*from",
            r"valid.*to",
            r"effective.*date",
        ]
    
    def _build_audit_patterns(self) -> List[str]:
        """Build audit field patterns."""
        return [
            r".*edited.*by",
            r".*updated.*by",
            r".*created.*by",
            r".*modified.*by",
        ]
    
    def _build_dimension_patterns(self) -> List[str]:
        """Build dimension field patterns."""
        return [
            r".*name$",
            r".*type$",
            r".*status$",
            r".*category$",
            r".*class$",
        ]


# Singleton instance
_descriptor = SemanticColumnDescriptor()


def generate_column_description(
    column_name: str,
    table_name: str,
    column_profile: Dict[str, Any],
    is_pk_candidate: bool = False,
) -> ColumnDescription:
    """
    Convenience function to generate column description.
    
    Args:
        column_name: Column name
        table_name: Table name
        column_profile: Column statistics
        is_pk_candidate: Whether column is PK candidate
    
    Returns:
        ColumnDescription
    """
    return _descriptor.generate_description(
        column_name, table_name, column_profile, is_pk_candidate
    )
