"""
Relationship Detection Data Models

Pydantic models for the foreign key relationship detection layer.
Ensures type safety, validation, and serialization consistency.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class RelationshipType(str, Enum):
    """Types of relationships detected between tables."""
    FOREIGN_KEY = "foreign_key"
    COMPOSITE_FOREIGN_KEY = "composite_foreign_key"
    SELF_REFERENTIAL = "self_referential"
    MANY_TO_MANY = "many_to_many"
    HIERARCHICAL = "hierarchical"
    WEAK_REFERENCE = "weak_reference"
    UNKNOWN = "unknown"


class ExecutionEngine(str, Enum):
    """Execution engine used for relationship detection."""
    PYTHON = "python"
    DUCKDB = "duckdb"
    STREAMING = "streaming"
    HYBRID = "hybrid"


class SamplingStrategy(str, Enum):
    """Sampling strategy used for validation."""
    FULL_SCAN = "full_scan"
    RESERVOIR = "reservoir"
    RESERVOIR_HLL = "reservoir_hll"
    METADATA_ONLY = "metadata_only"
    ROW_GROUP = "row_group"
    STREAMING_SKETCH = "streaming_sketch"


class PhysicalType(str, Enum):
    """Physical data types for type compatibility matching."""
    INTEGER = "INTEGER"
    BIGINT = "BIGINT"
    FLOAT = "FLOAT"
    DOUBLE = "DOUBLE"
    STRING = "STRING"
    VARCHAR = "VARCHAR"
    UUID = "UUID"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    TIMESTAMP = "TIMESTAMP"
    DECIMAL = "DECIMAL"
    BINARY = "BINARY"
    JSON = "JSON"
    ARRAY = "ARRAY"
    UNKNOWN = "UNKNOWN"


@dataclass
class ColumnReference:
    """Reference to a table column."""
    table: str
    column: str
    physical_type: Optional[str] = None
    logical_type: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "table": self.table,
            "column": self.column,
            "physical_type": self.physical_type,
            "logical_type": self.logical_type,
        }


@dataclass
class RelationshipEvidence:
    """Evidence supporting a relationship hypothesis."""
    containment_ratio: float  # |FK ∩ PK| / |FK| - AUTHORITATIVE
    overlap_ratio: float  # |FK ∩ PK| / |PK|
    type_match: bool
    type_compatibility_score: float
    pk_confidence: float
    naming_similarity: float
    cardinality_ratio: float  # |FK distinct| / |PK distinct|
    null_ratio_fk: float
    
    # Sampling metadata
    is_approximate: bool = False
    sample_size_fk: Optional[int] = None
    sample_size_pk: Optional[int] = None
    
    # Advanced evidence
    bloom_filter_passed: bool = True
    orphan_count: Optional[int] = None
    semantic_similarity: Optional[float] = None  # If ANN used for retrieval
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "containment_ratio": round(self.containment_ratio, 4),
            "overlap_ratio": round(self.overlap_ratio, 4),
            "type_match": self.type_match,
            "type_compatibility_score": round(self.type_compatibility_score, 2),
            "pk_confidence": round(self.pk_confidence, 4),
            "naming_similarity": round(self.naming_similarity, 4),
            "cardinality_ratio": round(self.cardinality_ratio, 4),
            "null_ratio_fk": round(self.null_ratio_fk, 4),
            "is_approximate": self.is_approximate,
            "sample_size_fk": self.sample_size_fk,
            "sample_size_pk": self.sample_size_pk,
            "bloom_filter_passed": self.bloom_filter_passed,
            "orphan_count": self.orphan_count,
            "semantic_similarity": round(self.semantic_similarity, 4) if self.semantic_similarity else None,
        }


@dataclass
class RelationshipValidation:
    """Validation results for a relationship."""
    containment_validated: bool
    orphan_count: int
    orphan_ratio: float
    referential_integrity_score: float  # 1.0 - orphan_ratio
    validation_method: str  # "full_scan", "sampled", "bloom_filter"
    
    # Quality flags
    has_orphans: bool = False
    is_weak_reference: bool = False
    is_ambiguous: bool = False
    
    # Warnings
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "containment_validated": self.containment_validated,
            "orphan_count": self.orphan_count,
            "orphan_ratio": round(self.orphan_ratio, 4),
            "referential_integrity_score": round(self.referential_integrity_score, 4),
            "validation_method": self.validation_method,
            "has_orphans": self.has_orphans,
            "is_weak_reference": self.is_weak_reference,
            "is_ambiguous": self.is_ambiguous,
            "warnings": self.warnings,
        }


@dataclass
class RelationshipExecutionMetadata:
    """Metadata about how the relationship was detected."""
    engine: str
    sampling_strategy: str
    is_approximate: bool
    deterministic_seed: Optional[int] = None
    profiler_version: str = "1.0.0"
    relationship_rule_version: str = "1.0.0"
    detection_timestamp: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine": self.engine,
            "sampling_strategy": self.sampling_strategy,
            "is_approximate": self.is_approximate,
            "deterministic_seed": self.deterministic_seed,
            "profiler_version": self.profiler_version,
            "relationship_rule_version": self.relationship_rule_version,
            "detection_timestamp": self.detection_timestamp,
        }


@dataclass
class Relationship:
    """A detected relationship between two columns."""
    relationship_id: str
    relationship_type: RelationshipType
    from_column: ColumnReference
    to_column: ColumnReference
    confidence: float
    accepted: bool
    evidence: RelationshipEvidence
    validation: RelationshipValidation
    execution_metadata: RelationshipExecutionMetadata
    
    # Optional fields
    composite_key: bool = False
    composite_members: Optional[List[Tuple[str, str]]] = None  # [(table, col), ...]
    reasoning: Optional[str] = None
    suppression_reasons: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "relationship_id": self.relationship_id,
            "relationship_type": self.relationship_type.value,
            "from": self.from_column.to_dict(),
            "to": self.to_column.to_dict(),
            "confidence": round(self.confidence, 4),
            "accepted": self.accepted,
            "evidence": self.evidence.to_dict(),
            "validation": self.validation.to_dict(),
            "execution_metadata": self.execution_metadata.to_dict(),
            "composite_key": self.composite_key,
        }
        
        if self.composite_members:
            result["composite_members"] = self.composite_members
        if self.reasoning:
            result["reasoning"] = self.reasoning
        if self.suppression_reasons:
            result["suppression_reasons"] = self.suppression_reasons
        
        return result


@dataclass
class RelationshipReport:
    """Complete relationship detection report."""
    relationship_report_id: str
    schema_version: str = "v1.0.0"
    artifact_type: str = "RelationshipReport"
    generation_timestamp: Optional[str] = None
    
    # Core data
    relationships: List[Relationship] = field(default_factory=list)
    
    # Summary statistics
    total_relationships_detected: int = 0
    total_relationships_accepted: int = 0
    total_relationships_rejected: int = 0
    total_tables_analyzed: int = 0
    total_candidate_pairs_evaluated: int = 0
    
    # Execution metadata
    execution_engine: Optional[str] = None
    execution_time_seconds: Optional[float] = None
    
    # Graph metadata (for future graph exports)
    graph_node_count: int = 0
    graph_edge_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "relationship_report_id": self.relationship_report_id,
            "schema_version": self.schema_version,
            "artifact_type": self.artifact_type,
            "generation_timestamp": self.generation_timestamp,
            "summary": {
                "total_relationships_detected": self.total_relationships_detected,
                "total_relationships_accepted": self.total_relationships_accepted,
                "total_relationships_rejected": self.total_relationships_rejected,
                "total_tables_analyzed": self.total_tables_analyzed,
                "total_candidate_pairs_evaluated": self.total_candidate_pairs_evaluated,
                "graph_node_count": self.graph_node_count,
                "graph_edge_count": self.graph_edge_count,
            },
            "execution_metadata": {
                "execution_engine": self.execution_engine,
                "execution_time_seconds": round(self.execution_time_seconds, 3) if self.execution_time_seconds else None,
            },
            "relationships": [rel.to_dict() for rel in self.relationships],
        }


# ============================================================================
# INTERNAL WORKING MODELS (not serialized to JSON)
# ============================================================================

@dataclass
class CandidatePair:
    """A candidate FK->PK relationship for evaluation."""
    fk_table: str
    fk_column: str
    pk_table: str
    pk_column: str
    
    # Type metadata
    fk_type: str
    pk_type: str
    
    # PK candidate metadata
    pk_confidence: float
    pk_accepted: bool
    
    # Generation metadata
    generation_reason: str  # "naming_heuristic", "type_match", "semantic_retrieval"
    naming_similarity: float = 0.0
    type_compatible: bool = False
    
    def __hash__(self):
        return hash((self.fk_table, self.fk_column, self.pk_table, self.pk_column))
    
    def __eq__(self, other):
        if not isinstance(other, CandidatePair):
            return False
        return (
            self.fk_table == other.fk_table and
            self.fk_column == other.fk_column and
            self.pk_table == other.pk_table and
            self.pk_column == other.pk_column
        )


@dataclass
class TypeCompatibilityResult:
    """Result of type compatibility check."""
    compatible: bool
    compatibility_score: float  # 0.0 to 1.0
    coercion_required: bool = False
    coercion_strategy: Optional[str] = None
    reasoning: str = ""


@dataclass
class OverlapEstimate:
    """Overlap estimation result."""
    overlap_count: int
    overlap_ratio: float  # |FK ∩ PK| / |PK|
    is_approximate: bool = False
    bloom_filter_used: bool = False
    sample_size: Optional[int] = None


@dataclass
class ContainmentResult:
    """Containment validation result."""
    contained: bool
    containment_ratio: float  # |FK ∩ PK| / |FK|
    orphan_count: int
    orphan_ratio: float
    total_fk_values: int
    distinct_fk_values: int
    distinct_pk_values: int
    validation_method: str
    is_approximate: bool = False
