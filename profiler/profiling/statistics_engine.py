"""
Layer 6 — Statistics Engine

Computes comprehensive statistics from CanonicalTable sample values.
"""

import math
import statistics
from typing import List, Any, Dict, Optional, Tuple
from collections import Counter

from .profiling_models import ColumnStatistics, PhysicalType


def compute_statistics(
    sample_values: List[Any],
    physical_type: PhysicalType,
    existing_stats: Optional[Dict[str, Any]] = None
) -> ColumnStatistics:
    """
    Compute comprehensive statistics from sample values.
    
    Args:
        sample_values: Sample values from CanonicalTable
        physical_type: Physical type of the column
        existing_stats: Existing statistics from CanonicalTable (optional)
        
    Returns:
        ColumnStatistics with all computed metrics
    """
    
    if not sample_values:
        return _empty_statistics()
    
    total = len(sample_values)
    
    # 1. Null analysis
    null_count = sum(1 for v in sample_values if v is None or v == '' or str(v).lower() in ('null', 'none'))
    null_ratio = null_count / total if total > 0 else 0.0
    
    # 2. Non-null values
    non_null = [v for v in sample_values if v is not None and v != '' and str(v).lower() not in ('null', 'none')]
    
    if not non_null:
        return _empty_statistics()
    
    # 3. Cardinality
    distinct_vals = set(str(v) for v in non_null)
    distinct_count = len(distinct_vals)
    uniqueness_ratio = distinct_count / total if total > 0 else 0.0
    cardinality_ratio = distinct_count / len(non_null) if non_null else 0.0
    duplicate_count = len(non_null) - distinct_count
    
    # 4. Entropy
    entropy = _compute_shannon_entropy(non_null)
    max_entropy = math.log2(len(non_null)) if len(non_null) > 1 else 0.0
    entropy_normalized = entropy / max_entropy if max_entropy > 0 else 0.0
    # Clamp to [0, 1] to handle floating point precision issues
    entropy_normalized = max(0.0, min(1.0, entropy_normalized))
    
    # 5. String metrics
    min_length, max_length, avg_length = None, None, None
    if physical_type in (PhysicalType.STRING, PhysicalType.UNKNOWN):
        str_values = [str(v) for v in non_null]
        if str_values:
            lengths = [len(s) for s in str_values]
            min_length = min(lengths)
            max_length = max(lengths)
            avg_length = sum(lengths) / len(lengths)
    
    # 6. Numeric metrics
    min_value, max_value, mean, median, std_dev, variance = None, None, None, None, None, None
    quantiles, skewness, kurtosis = None, None, None
    
    if physical_type in (PhysicalType.INTEGER, PhysicalType.FLOAT, PhysicalType.DECIMAL):
        numeric_vals = _parse_numeric_values(non_null)
        if numeric_vals and len(numeric_vals) > 0:
            min_value = float(min(numeric_vals))
            max_value = float(max(numeric_vals))
            mean = float(statistics.mean(numeric_vals))
            median = float(statistics.median(numeric_vals))
            
            if len(numeric_vals) > 1:
                try:
                    std_dev = float(statistics.stdev(numeric_vals))
                    variance = float(statistics.variance(numeric_vals))
                except statistics.StatisticsError:
                    pass
            
            # Quantiles
            quantiles = _compute_quantiles(numeric_vals)
            
            # Skewness and kurtosis
            if len(numeric_vals) >= 3:
                skewness = _compute_skewness(numeric_vals, mean, std_dev)
                kurtosis = _compute_kurtosis(numeric_vals, mean, std_dev)
    
    # 7. Top values
    counter = Counter(str(v) for v in non_null)
    top_values = [(val, count) for val, count in counter.most_common(10)]
    
    return ColumnStatistics(
        null_count=null_count,
        null_ratio=null_ratio,
        distinct_count=distinct_count,
        uniqueness_ratio=uniqueness_ratio,
        cardinality_ratio=cardinality_ratio,
        duplicate_count=duplicate_count,
        entropy=entropy,
        entropy_normalized=entropy_normalized,
        min_length=min_length,
        max_length=max_length,
        avg_length=avg_length,
        min_value=min_value,
        max_value=max_value,
        mean=mean,
        median=median,
        std_dev=std_dev,
        variance=variance,
        quantiles=quantiles,
        skewness=skewness,
        kurtosis=kurtosis,
        top_values=top_values
    )


def _empty_statistics() -> ColumnStatistics:
    """Return empty statistics for null columns."""
    return ColumnStatistics(
        null_count=0,
        null_ratio=0.0,
        distinct_count=0,
        uniqueness_ratio=0.0,
        cardinality_ratio=0.0,
        duplicate_count=0,
        entropy=0.0,
        entropy_normalized=0.0
    )


def _compute_shannon_entropy(values: List[Any]) -> float:
    """
    Compute Shannon entropy.
    
    H = -Σ(p(x) * log2(p(x)))
    """
    if not values:
        return 0.0
    
    try:
        counter = Counter(str(v) for v in values)
        total = len(values)
        
        entropy = 0.0
        for count in counter.values():
            prob = count / total
            if prob > 0:
                entropy -= prob * math.log2(prob)
        
        return entropy
    except:
        return 0.0


def _parse_numeric_values(values: List[Any]) -> List[float]:
    """Parse values to numeric, returning only valid numbers."""
    numeric = []
    for v in values:
        try:
            numeric.append(float(v))
        except (ValueError, TypeError):
            pass
    return numeric


def _compute_quantiles(values: List[float]) -> Dict[str, float]:
    """Compute quantiles (p25, p50, p75, p90, p99)."""
    if not values or len(values) < 2:
        return {}
    
    try:
        sorted_vals = sorted(values)
        return {
            "p25": float(statistics.quantiles(sorted_vals, n=4)[0]),
            "p50": float(statistics.median(sorted_vals)),
            "p75": float(statistics.quantiles(sorted_vals, n=4)[2]),
            "p90": float(_percentile(sorted_vals, 0.90)),
            "p99": float(_percentile(sorted_vals, 0.99))
        }
    except:
        return {}


def _percentile(values: List[float], p: float) -> float:
    """Compute percentile."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return d0 + d1


def _compute_skewness(values: List[float], mean: float, std_dev: Optional[float]) -> Optional[float]:
    """
    Compute skewness (Fisher-Pearson coefficient).
    
    Skewness = E[(X - μ)³] / σ³
    """
    if not values or len(values) < 3 or std_dev is None or std_dev == 0:
        return None
    
    try:
        n = len(values)
        m3 = sum((x - mean) ** 3 for x in values) / n
        skewness = m3 / (std_dev ** 3)
        return skewness
    except:
        return None


def _compute_kurtosis(values: List[float], mean: float, std_dev: Optional[float]) -> Optional[float]:
    """
    Compute kurtosis (excess kurtosis).
    
    Kurtosis = E[(X - μ)⁴] / σ⁴ - 3
    """
    if not values or len(values) < 4 or std_dev is None or std_dev == 0:
        return None
    
    try:
        n = len(values)
        m4 = sum((x - mean) ** 4 for x in values) / n
        kurtosis = (m4 / (std_dev ** 4)) - 3
        return kurtosis
    except:
        return None
