"""
Layer 6 — Profiling Models

Pydantic data models for the profiling layer.
These define the schema for FileProfile output.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LogicalType(str, Enum):
    """Logical type classification."""
    IDENTIFIER = "identifier"
    AUDIT_REFERENCE = "audit_reference"
    MEASURE = "measure"
    DIMENSION = "dimension"
    TIMESTAMP = "timestamp"
    AUDIT = "audit"
    CATEGORY = "category"
    DESCRIPTION = "description"
    GEOSPATIAL = "geospatial"
    CONTACT = "contact"
    UNKNOWN = "unknown"

class PhysicalType(str, Enum):
    """Physical data types detected from values."""
    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"
    DECIMAL = "decimal"
    STRING = "string"
    DATE = "date"
    DATETIME = "datetime"
    TIME = "time"
    UUID = "uuid"
    JSON = "json"
    BINARY = "binary"
    UNKNOWN = "unknown"


class SemanticType(str, Enum):
    """Semantic types inferred from patterns and context."""
    # Identifiers
    IDENTIFIER = "identifier"
    NATURAL_KEY = "natural_key"
    SURROGATE_KEY = "surrogate_key"
    # Personal Information
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    NAME = "name"
    ADDRESS = "address"
    
    # Geographic
    COUNTRY = "country"
    STATE_PROVINCE = "state_province"
    CITY = "city"
    ZIP_CODE = "zip_code"
    LATITUDE = "latitude"
    LONGITUDE = "longitude"
    GEO_POINT = "GEO_POINT"
    GEOSPATIAL_POINT = "geospatial_point"
    GEOGRAPHIC_ENTITY = "geographic_entity"
    GEOSPATIAL_COORDINATE = "geospatial_coordinate"
    
    # Financial
    CURRENCY = "currency"
    PRICE = "price"
    AMOUNT = "amount"
    
    # Temporal
    TIMESTAMP_START = "timestamp_start"
    TIMESTAMP_END = "timestamp_end"
    TIMESTAMP = "timestamp"
    TEMPORAL = "temporal"
    TEMPORAL_START = "temporal_start"
    TEMPORAL_END = "temporal_end"
    
    # Categorical
    CATEGORY = "category"
    ENUM = "enum"
    BOOLEAN_FLAG = "boolean_flag"
    
    # Measurements
    MEASURE = "measure"
    COUNT = "count"
    PERCENTAGE = "percentage"
    NUMERIC = "numeric"
    
    # Text
    FREE_TEXT = "free_text"
    DESCRIPTION = "description"
    COMMENT = "comment"
    URL = "url"
    
    # Other
    DIMENSION = "dimension"
    UNKNOWN = "unknown"


class QualityFlag(str, Enum):
    """Data quality flags - comprehensive quality dimensions."""
    
    # 1. STRUCTURAL QUALITY
    CORRUPT_ROW = "corrupt_row"
    SHIFTED_COLUMNS = "shifted_columns"
    ENCODING_MISMATCH = "encoding_mismatch"
    MALFORMED_JSON = "malformed_json"
    TRUNCATION_DETECTED = "truncation_detected"
    INVALID_NESTING = "invalid_nesting"
    
    # 2. COMPLETENESS QUALITY
    FULLY_NULL = "fully_null"
    HIGH_NULL_RATIO = "high_null_ratio"
    HIGH_MISSINGNESS = "high_missingness"
    SPARSITY_DETECTED = "sparsity_detected"
    REQUIRED_FIELD_ABSENT = "required_field_absent"
    
    # 3. UNIQUENESS QUALITY
    DUPLICATE_ROWS = "duplicate_rows"
    HIGH_DUPLICATION = "high_duplication"
    PK_DUPLICATION = "pk_duplication"
    DUPLICATE_EXPLOSION = "duplicate_explosion"
    WEAK_IDENTIFIER = "weak_identifier"
    
    # 4. TYPE QUALITY
    TYPE_CONFLICT = "type_conflict"
    MIXED_NUMERIC_STRING = "mixed_numeric_string"
    INVALID_BOOLEAN = "invalid_boolean"
    MALFORMED_UUID = "malformed_uuid"
    MIXED_DATE_FORMATS = "mixed_date_formats"
    MIXED_TIMEZONES = "mixed_timezones"
    INVALID_NUMERIC_FORMAT = "invalid_numeric_format"
    
    # 5. SEMANTIC QUALITY
    NEGATIVE_PRICE = "negative_price"
    INVALID_EMAIL = "invalid_email"
    IMPOSSIBLE_AGE = "impossible_age"
    INVALID_COUNTRY_CODE = "invalid_country_code"
    MALFORMED_PHONE = "malformed_phone"
    INCONSISTENT_CURRENCY = "inconsistent_currency"
    INVALID_SEMANTIC_VALUE = "invalid_semantic_value"
    
    # 6. RELATIONAL QUALITY
    ORPHAN_FOREIGN_KEY = "orphan_foreign_key"
    BROKEN_JOIN = "broken_join"
    WEAK_RELATIONSHIP = "weak_relationship"
    REFERENTIAL_DRIFT = "referential_drift"
    CARDINALITY_VIOLATION = "cardinality_violation"
    
    # 7. TEMPORAL QUALITY
    FUTURE_TIMESTAMP = "future_timestamp"
    INVALID_ORDERING = "invalid_ordering"
    NEGATIVE_DURATION = "negative_duration"
    INCONSISTENT_TIMEZONE_SEQUENCE = "inconsistent_timezone_sequence"
    IMPOSSIBLE_EVENT_TIMELINE = "impossible_event_timeline"
    
    # 8. STATISTICAL QUALITY
    DISTRIBUTION_DRIFT = "distribution_drift"
    ANOMALY_SPIKE = "anomaly_spike"
    ENTROPY_COLLAPSE = "entropy_collapse"
    EXTREME_SKEWNESS = "extreme_skewness"
    UNEXPECTED_CARDINALITY_CHANGE = "unexpected_cardinality_change"
    ABNORMAL_VARIANCE = "abnormal_variance"
    ZERO_ENTROPY = "zero_entropy"
    CONSTANT_COLUMN = "constant_column"
    SKEWED_DISTRIBUTION = "skewed_distribution"
    OUTLIER_DETECTED = "outlier_detected"
    
    # 9. CONSISTENCY QUALITY
    CONFLICTING_VALUES = "conflicting_values"
    SEMANTIC_CONTRADICTION = "semantic_contradiction"
    INCONSISTENT_UNITS = "inconsistent_units"
    INCONSISTENT_CATEGORY_MAPPING = "inconsistent_category_mapping"
    
    # 10. BUSINESS RULE QUALITY
    BUSINESS_RULE_VIOLATION = "business_rule_violation"
    REQUIRED_FIELD_MISSING = "required_field_missing"
    INVALID_RANGE = "invalid_range"
    TEMPORAL_ANOMALY = "temporal_anomaly"
    GEO_ERROR = "geo_error"
    INVALID_IDENTIFIER = "invalid_identifier"
    HEAVY_TAIL = "heavy_tail"
    CROSS_FIELD_CONSTRAINT_VIOLATION = "cross_field_constraint_violation"
    LOW_CARDINALITY_IDENTIFIER = "low_cardinality_identifier"
    DUPLICATE_EXPECTED = "duplicate_expected"
    
    # LEGACY / GENERAL
    HIGH_CARDINALITY = "high_cardinality"
    LOW_CARDINALITY = "low_cardinality"
    PII_EXPOSURE_RISK = "pii_exposure_risk"
    SUSPICIOUS_IDENTIFIER = "suspicious_identifier"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class ColumnStatistics(BaseModel):
    """Comprehensive column statistics."""
    total_count: int = 0
    non_null_count: int = 0
    distinct_non_null_count: int = 0
    coverage_ratio: float = Field(default=0.0, ge=0, le=1)
    duplicate_ratio: float = Field(default=0.0, ge=0, le=1)
    
    # Nullability
    null_count: int
    null_ratio: float = Field(..., ge=0, le=1)
    
    # Cardinality
    distinct_count: int
    uniqueness_ratio: float = Field(..., ge=0, le=1)
    cardinality_ratio: float = Field(..., ge=0, le=1)
    duplicate_count: int
    
    # Information theory
    entropy: float
    entropy_normalized: float = Field(..., ge=0, le=1)
    
    # String metrics
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    avg_length: Optional[float] = None
    
    # Numeric metrics
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean: Optional[float] = None
    median: Optional[float] = None
    std_dev: Optional[float] = None
    variance: Optional[float] = None
    
    # Distribution
    quantiles: Optional[Dict[str, float]] = None
    skewness: Optional[float] = None
    kurtosis: Optional[float] = None
    
    # Top values
    top_values: Optional[List[Tuple[str, int]]] = None
    frequency_distribution: Optional[List[Dict[str, Any]]] = None
    duplicate_density: float = Field(default=0.0, ge=0, le=1)


class PKEvidence(BaseModel):
    """Evidence for PK candidate scoring."""
    pk_score: float = Field(default=0.0, ge=0, le=1)
    pk_candidate: bool = False
    pk_confidence: float = Field(default=0.0, ge=0, le=1)
    suppressed: bool = False
    suppression_reasons: List[str] = Field(default_factory=list)
    positive_evidence: List[str] = Field(default_factory=list)
    negative_evidence: List[str] = Field(default_factory=list)
    
    uniqueness_score: float = Field(..., ge=0, le=1)
    non_null_score: float = Field(..., ge=0, le=1)
    entropy_score: float = Field(..., ge=0, le=1)
    type_stability_score: float = Field(..., ge=0, le=1)
    name_pattern_score: float = Field(..., ge=0, le=1)
    
    # Explanation
    reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class CardinalityClass(str, Enum):
    """Cardinality classification for columns."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProfileHints(BaseModel):
    """Lightweight profiler-only hints for downstream interpretation."""
    is_identifier: bool = False
    is_temporal: bool = False
    is_audit: bool = False
    is_measure: bool = False
    is_dimension: bool = False
    is_text: bool = False


class ColumnProfile(BaseModel):
    """Complete column profile."""
    # Identity
    column_name: str
    original_name: Optional[str] = None
    position: int
    
    # Types
    physical_type: PhysicalType
    semantic_type: Optional[SemanticType] = None
    logical_type: Optional[LogicalType] = None
    type_confidence: float = Field(..., ge=0, le=1)
    
    # Metrics
    completeness: float = Field(..., ge=0, le=1)
    uniqueness: float = Field(..., ge=0, le=1)
    entropy_normalized: float = Field(..., ge=0, le=1)
    cardinality_class: Optional[CardinalityClass] = None
    
    # PK Detection
    pk_candidate: bool
    pk_score: float = Field(..., ge=0, le=1)
    pk_confidence: float = Field(..., ge=0, le=1)
    pk_evidence: Optional[PKEvidence] = None
    suppressed: bool = False
    suppression_reasons: List[str] = Field(default_factory=list)

    # Specialized profiles
    temporal_pattern: Optional[Dict[str, Any]] = None
    geo_profile: Optional[Dict[str, Any]] = None
    audit_profile: Optional[Dict[str, Any]] = None
    
    # Quality
    quality_flags: List[QualityFlag] = Field(default_factory=list)
    quality_score: float = Field(..., ge=0, le=1)
    quality_breakdown: Dict[str, float] = Field(default_factory=dict)
    
    # Statistics
    statistics: ColumnStatistics

    # Lightweight profiler hints
    profile_hints: ProfileHints = Field(default_factory=ProfileHints)
    
    # Sample values (for debugging)
    sample_values: Optional[List[Any]] = None


class TableProfile(BaseModel):
    """Table-level profile."""
    row_count_estimate: Optional[int]
    column_count: int
    
    # Quality metrics
    completeness_score: float = Field(..., ge=0, le=1)
    quality_score: float = Field(..., ge=0, le=1)
    
    # PK candidates
    pk_candidates: List[str] = Field(default_factory=list)
    composite_pk_candidates: List[List[str]] = Field(default_factory=list)
    
    # Quality summary
    total_quality_flags: int
    columns_with_issues: int


class ProfilingMetadata(BaseModel):
    """Profiling execution metadata."""
    profiled_at: datetime
    profiler_version: str
    execution_time_ms: float
    sample_based: bool
    sample_size: Optional[int] = None
    canonical_table_id: str


class FileProfile(BaseModel):
    """Complete file profile output."""
    profile_id: str
    table_name: str
    
    # Metadata
    profiling_metadata: ProfilingMetadata
    
    # Profiles
    table_profile: TableProfile
    columns: List[ColumnProfile]
    
    # Source reference
    source_canonical_path: Optional[str] = None
