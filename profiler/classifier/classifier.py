"""
Layer 3 — Semantic Classifier

Goes beyond simple size-based routing to provide intelligent workload classification.

Determines:
- Source type (CSV, Parquet, JSON, etc.)
- Size tier (tiny → massive)
- Execution complexity (shallow → extreme)
- Analytical suitability (OLAP, time-series, NLP, ML, etc.)
- Structural classification (fact table, dimension, event stream, entity)

This provides the intelligence layer for adaptive execution planning.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List
import re

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Classification Result
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    """
    Complete classification of a dataset.
    
    Combines size-based routing with semantic intelligence.
    """
    # Basic properties (required)
    source_type: str                    # "csv", "parquet", "json", etc.
    size_bytes: int
    size_mb: float
    
    # Size tier classification (required)
    size_tier: str                      # "tiny", "small", "medium", "large", etc.
    engine_recommendation: str          # "python", "duckdb", "streaming"
    strategy_recommendation: str        # "reservoir", "rowgroup", "streaming_sketches"
    
    # Execution complexity (required)
    complexity_score: float
    workload_type: str                  # "analytical_olap", "transactional", "time_series", etc.
    
    # Optional fields with defaults
    complexity_factors: dict = field(default_factory=dict)
    is_relational: bool = False
    contains_time_series: bool = False
    contains_pii: bool = False
    nlp_heavy: bool = False
    ml_ready: bool = False
    structural_type: Optional[str] = None  # "fact_table", "dimension", "event_stream", "entity"
    estimated_rows: Optional[int] = None
    estimated_columns: Optional[int] = None
    high_cardinality_columns: List[str] = field(default_factory=list)
    low_cardinality_columns: List[str] = field(default_factory=list)
    recommended_sample_size: int = 1000
    requires_streaming: bool = False
    can_fit_in_memory: bool = True


# ---------------------------------------------------------------------------
# Complexity Scoring
# ---------------------------------------------------------------------------

def compute_complexity_score(
    size_mb: float,
    estimated_columns: Optional[int] = None,
    estimated_rows: Optional[int] = None,
    compression: Optional[str] = None,
    file_format: Optional[str] = None,
    encoding: Optional[str] = None,
) -> tuple[float, dict]:
    """
    Compute execution complexity score (0-10 scale).
    
    Factors:
    - File size
    - Column count (if known)
    - Row count (if known)
    - Compression (adds overhead)
    - Format complexity (Parquet < CSV < JSON)
    - Encoding issues (non-UTF8 adds complexity)
    
    Returns:
        (score, factors_dict)
    """
    factors = {}
    score = 0.0
    
    # 1. Size weight (0-3 points)
    if size_mb < 1:
        size_weight = 0.0
    elif size_mb < 10:
        size_weight = 0.5
    elif size_mb < 100:
        size_weight = 1.0
    elif size_mb < 1024:
        size_weight = 1.5
    elif size_mb < 10240:
        size_weight = 2.0
    else:
        size_weight = 3.0
    
    score += size_weight
    factors["size_weight"] = size_weight
    
    # 2. Column count weight (0-2 points)
    if estimated_columns:
        if estimated_columns < 10:
            col_weight = 0.0
        elif estimated_columns < 50:
            col_weight = 0.5
        elif estimated_columns < 200:
            col_weight = 1.0
        elif estimated_columns < 1000:
            col_weight = 1.5
        else:
            col_weight = 2.0
        
        score += col_weight
        factors["column_count_weight"] = col_weight
    
    # 3. Row count weight (0-2 points)
    if estimated_rows:
        if estimated_rows < 1000:
            row_weight = 0.0
        elif estimated_rows < 100_000:
            row_weight = 0.5
        elif estimated_rows < 1_000_000:
            row_weight = 1.0
        elif estimated_rows < 10_000_000:
            row_weight = 1.5
        else:
            row_weight = 2.0
        
        score += row_weight
        factors["row_count_weight"] = row_weight
    
    # 4. Compression weight (0-1 points)
    if compression in ('gz', 'zip', 'bz2', 'xz'):
        comp_weight = 1.0
        score += comp_weight
        factors["compression_weight"] = comp_weight
    
    # 5. Format complexity (0-1.5 points)
    format_complexity = {
        'parquet': 0.0,    # Self-describing, columnar
        'csv': 0.5,        # Simple but requires parsing
        'tsv': 0.5,
        'json': 1.0,       # Nested structures
        'jsonl': 0.8,
        'xml': 1.5,        # Most complex
        'excel': 0.7,      # Binary format
    }
    
    format_weight = format_complexity.get(file_format, 0.5)
    score += format_weight
    factors["format_weight"] = format_weight
    
    # 6. Encoding complexity (0-0.5 points)
    if encoding and encoding not in ('utf-8', 'ascii', 'utf-8-sig'):
        encoding_weight = 0.5
        score += encoding_weight
        factors["encoding_weight"] = encoding_weight
    
    # Normalize to 0-10 scale
    max_score = 3.0 + 2.0 + 2.0 + 1.0 + 1.5 + 0.5  # = 10.0
    normalized_score = min(score, max_score)
    
    return normalized_score, factors


# ---------------------------------------------------------------------------
# Workload Type Classification
# ---------------------------------------------------------------------------

def classify_workload_type(
    column_names: Optional[List[str]] = None,
    sample_data: Optional[dict] = None,
) -> tuple[str, dict]:
    """
    Classify the workload type based on column names and sample data.
    
    Workload types:
    - analytical_olap: Measures + dimensions, aggregation-friendly
    - transactional: ID-heavy, many foreign keys
    - time_series: Timestamps, temporal patterns
    - event_stream: Append-only, timestamps
    - nlp_corpus: Large text columns
    - ml_features: Numerical features, target columns
    - mixed: Multiple patterns
    
    Returns:
        (workload_type, characteristics_dict)
    """
    if not column_names:
        return "unknown", {}
    
    col_lower = [c.lower() for c in column_names]
    characteristics = {
        "is_relational": False,
        "contains_time_series": False,
        "contains_pii": False,
        "nlp_heavy": False,
        "ml_ready": False,
    }
    
    # Pattern detection
    id_patterns = r'(^id$|_id$|^.*id$)'
    fk_patterns = r'(customer|order|product|user|person|account).*id'
    time_patterns = r'(date|time|timestamp|created|updated|when)'
    measure_patterns = r'(amount|price|quantity|total|count|sum|revenue|cost)'
    pii_patterns = r'(email|phone|ssn|address|name|dob|birth)'
    text_patterns = r'(description|comment|note|text|body|content|message)'
    feature_patterns = r'(feature|score|rating|prediction|label|target)'
    
    # Count pattern matches
    id_count = sum(1 for c in col_lower if re.search(id_patterns, c))
    fk_count = sum(1 for c in col_lower if re.search(fk_patterns, c))
    time_count = sum(1 for c in col_lower if re.search(time_patterns, c))
    measure_count = sum(1 for c in col_lower if re.search(measure_patterns, c))
    pii_count = sum(1 for c in col_lower if re.search(pii_patterns, c))
    text_count = sum(1 for c in col_lower if re.search(text_patterns, c))
    feature_count = sum(1 for c in col_lower if re.search(feature_patterns, c))
    
    total_cols = len(col_lower)
    
    # Classification logic
    characteristics["is_relational"] = (id_count + fk_count) >= 2
    characteristics["contains_time_series"] = time_count >= 1
    characteristics["contains_pii"] = pii_count >= 1
    characteristics["nlp_heavy"] = text_count >= 3 or (text_count / total_cols > 0.3)
    characteristics["ml_ready"] = feature_count >= 5 or (feature_count / total_cols > 0.5)
    
    # Determine workload type
    if characteristics["ml_ready"]:
        workload_type = "ml_features"
    elif characteristics["nlp_heavy"]:
        workload_type = "nlp_corpus"
    elif time_count >= 2 and measure_count >= 2:
        workload_type = "time_series"
    elif time_count >= 1 and id_count >= 1 and not measure_count:
        workload_type = "event_stream"
    elif measure_count >= 3 and (id_count + fk_count) >= 2:
        workload_type = "analytical_olap"
    elif (id_count + fk_count) >= 3:
        workload_type = "transactional"
    else:
        workload_type = "mixed"
    
    return workload_type, characteristics


# ---------------------------------------------------------------------------
# Structural Classification
# ---------------------------------------------------------------------------

def classify_structure(
    column_names: Optional[List[str]] = None,
    estimated_rows: Optional[int] = None,
) -> Optional[str]:
    """
    Classify dataset structural type.
    
    Types:
    - fact_table: Many measures, few dimensions, large row count
    - dimension: Mostly categorical, smaller row count
    - event_stream: Timestamps, append-only pattern
    - entity: Primary key + attributes
    
    Returns:
        structural_type or None
    """
    if not column_names:
        return None
    
    col_lower = [c.lower() for c in column_names]
    
    # Pattern detection
    id_count = sum(1 for c in col_lower if 'id' in c)
    time_count = sum(1 for c in col_lower if any(t in c for t in ['date', 'time', 'when']))
    measure_count = sum(1 for c in col_lower if any(m in c for m in ['amount', 'price', 'quantity', 'total', 'count']))
    name_count = sum(1 for c in col_lower if 'name' in c)
    
    # Classification heuristics
    if time_count >= 2 and estimated_rows and estimated_rows > 100_000:
        return "event_stream"
    
    if measure_count >= 4 and id_count >= 2:
        return "fact_table"
    
    if name_count >= 2 and id_count == 1 and estimated_rows and estimated_rows < 10_000:
        return "dimension"
    
    if id_count == 1 and len(col_lower) >= 5:
        return "entity"
    
    return None


# ---------------------------------------------------------------------------
# Main Classifier
# ---------------------------------------------------------------------------

def classify(
    source_type: str,
    size_bytes: int,
    file_format: str,
    encoding: Optional[str] = None,
    compression: Optional[str] = None,
    column_names: Optional[List[str]] = None,
    estimated_rows: Optional[int] = None,
    sample_data: Optional[dict] = None,
) -> ClassificationResult:
    """
    Full semantic classification of a dataset.
    
    This is the main entry point for Layer 3 classification.
    
    Args:
        source_type: "file", "database", "stream", etc.
        size_bytes: File size in bytes
        file_format: "csv", "parquet", "json", etc.
        encoding: File encoding (if applicable)
        compression: Compression format (if applicable)
        column_names: List of column names (if available)
        estimated_rows: Estimated row count (if available)
        sample_data: Sample data for analysis (if available)
    
    Returns:
        ClassificationResult with full semantic analysis
    """
    size_mb = size_bytes / (1024 * 1024)
    
    # 1. Size tier classification (existing logic)
    if size_mb < 10:
        size_tier = "tiny"
        engine = "python"
        strategy = "reservoir"
    elif size_mb < 100:
        size_tier = "small"
        engine = "python"
        strategy = "reservoir_hll"
    elif size_mb < 1024:
        size_tier = "medium"
        engine = "duckdb"
        strategy = "reservoir_hll"
    elif size_mb < 10240:
        size_tier = "large"
        engine = "duckdb"
        strategy = "metadata_rowgroup"
    elif size_mb < 102400:
        size_tier = "very_large"
        engine = "duckdb"
        strategy = "metadata_rowgroup_hll"
    else:
        size_tier = "huge"
        engine = "streaming"
        strategy = "streaming_sketches"
    
    # 2. Complexity scoring (NEW)
    estimated_columns = len(column_names) if column_names else None
    complexity_score, complexity_factors = compute_complexity_score(
        size_mb=size_mb,
        estimated_columns=estimated_columns,
        estimated_rows=estimated_rows,
        compression=compression,
        file_format=file_format,
        encoding=encoding,
    )
    
    # 3. Workload classification (NEW)
    workload_type, characteristics = classify_workload_type(
        column_names=column_names,
        sample_data=sample_data,
    )
    
    # 4. Structural classification (NEW)
    structural_type = classify_structure(
        column_names=column_names,
        estimated_rows=estimated_rows,
    )
    
    # 5. Determine recommendations
    recommended_sample_size = _compute_sample_size(size_tier, complexity_score)
    requires_streaming = size_tier in ("huge", "massive")
    can_fit_in_memory = size_mb < 4096  # 4GB threshold
    
    # 6. Build result
    result = ClassificationResult(
        source_type=source_type,
        size_bytes=size_bytes,
        size_mb=round(size_mb, 2),
        size_tier=size_tier,
        engine_recommendation=engine,
        strategy_recommendation=strategy,
        complexity_score=round(complexity_score, 2),
        complexity_factors=complexity_factors,
        workload_type=workload_type,
        is_relational=characteristics.get("is_relational", False),
        contains_time_series=characteristics.get("contains_time_series", False),
        contains_pii=characteristics.get("contains_pii", False),
        nlp_heavy=characteristics.get("nlp_heavy", False),
        ml_ready=characteristics.get("ml_ready", False),
        structural_type=structural_type,
        estimated_rows=estimated_rows,
        estimated_columns=estimated_columns,
        recommended_sample_size=recommended_sample_size,
        requires_streaming=requires_streaming,
        can_fit_in_memory=can_fit_in_memory,
    )
    
    log.info("Classification complete:")
    log.info("  Tier: %s | Engine: %s | Strategy: %s", size_tier, engine, strategy)
    log.info("  Complexity: %.1f/10 | Workload: %s", complexity_score, workload_type)
    if structural_type:
        log.info("  Structure: %s", structural_type)
    
    return result


def _compute_sample_size(size_tier: str, complexity_score: float) -> int:
    """Compute recommended sample size based on tier and complexity."""
    base_sizes = {
        "tiny": 100,
        "small": 500,
        "medium": 1000,
        "large": 5000,
        "very_large": 10000,
        "huge": 50000,
        "massive": 100000,
    }
    
    base_size = base_sizes.get(size_tier, 1000)
    
    # Adjust for complexity
    if complexity_score < 3:
        return base_size
    elif complexity_score < 6:
        return int(base_size * 1.5)
    else:
        return int(base_size * 2.0)
