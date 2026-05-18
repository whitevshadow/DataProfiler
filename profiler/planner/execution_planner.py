"""
Layer 4 — Adaptive Execution Planner

The brain of the system. Makes intelligent decisions about:
- Which engine to use (Python, DuckDB, Streaming)
- Which sampling strategy (Reservoir, HLL, Metadata, Sketches)
- Memory mode (in-memory, streaming, disk-backed)
- Scan depth (full, partial, metadata-only)
- Execution type (exact, approximate, probabilistic)

Takes ClassificationResult from Layer 3 and produces ExecutionPlan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums for execution decisions
# ---------------------------------------------------------------------------

class Engine(Enum):
    """Execution engine choices."""
    PYTHON = "python"              # Single-threaded, simple
    DUCKDB = "duckdb"              # Vectorized, analytical
    STREAMING = "streaming"        # Constant memory, huge data
    DISTRIBUTED = "distributed"    # Multi-node, PB-scale


class SamplingStrategy(Enum):
    """Sampling strategy choices."""
    RESERVOIR = "reservoir"                          # Random sampling, O(k) memory
    RESERVOIR_HLL = "reservoir_hll"                  # Reservoir + approximate distinct
    METADATA_ROWGROUP = "metadata_rowgroup"          # Parquet metadata + row groups
    METADATA_ROWGROUP_HLL = "metadata_rowgroup_hll"  # Metadata + HLL for cardinality
    STREAMING_SKETCHES = "streaming_sketches"        # Probabilistic data structures
    DISTRIBUTED_SKETCHES = "distributed_sketches"    # Multi-node sketches


class MemoryMode(Enum):
    """Memory management mode."""
    IN_MEMORY = "in_memory"        # Full dataset in RAM
    STREAMING = "streaming"        # Constant memory, streaming
    DISK_BACKED = "disk_backed"    # Spill to disk if needed
    DISTRIBUTED = "distributed"    # Distributed memory


class ScanDepth(Enum):
    """How deeply to scan the data."""
    FULL = "full"                  # Read entire dataset
    PARTIAL = "partial"            # Sample or row groups
    METADATA_ONLY = "metadata"     # Just metadata, no data scan
    ADAPTIVE = "adaptive"          # Start shallow, go deeper if needed


class ExecutionType(Enum):
    """Precision of execution."""
    EXACT = "exact"                # Exact calculations
    APPROXIMATE = "approximate"    # Approximate with error bounds
    PROBABILISTIC = "probabilistic" # Probabilistic data structures


# ---------------------------------------------------------------------------
# Execution Plan Result
# ---------------------------------------------------------------------------

@dataclass
class ExecutionPlan:
    """
    Complete execution plan for profiling a dataset.
    
    Produced by the Adaptive Execution Planner based on
    ClassificationResult from Layer 3.
    """
    # Engine decisions (required)
    engine: Engine
    sampling_strategy: SamplingStrategy
    sample_size: int
    memory_mode: MemoryMode
    scan_depth: ScanDepth
    execution_type: ExecutionType
    
    # Optional fields with defaults
    fallback_engine: Optional[Engine] = None
    memory_limit_mb: Optional[int] = None
    max_rows_to_scan: Optional[int] = None
    error_tolerance: Optional[float] = None  # For approximate execution
    
    # DuckDB-specific settings
    use_duckdb_parquet_metadata: bool = False
    use_duckdb_pushdown: bool = False
    duckdb_threads: int = 4
    duckdb_memory_limit: str = "4GB"
    
    # Sampling-specific settings
    use_hll: bool = False
    hll_precision: int = 14  # Higher = more accurate, more memory
    use_bloom_filter: bool = False
    use_count_min_sketch: bool = False
    
    # Execution hints
    can_parallelize: bool = True
    recommended_batch_size: Optional[int] = None
    requires_compression_handling: bool = False
    
    # Cost estimates
    estimated_runtime_seconds: Optional[float] = None
    estimated_memory_mb: Optional[float] = None
    estimated_io_operations: Optional[int] = None
    
    # Rationale (for explainability)
    decision_rationale: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Decision Matrix
# ---------------------------------------------------------------------------

# Size tier → Engine mapping
ENGINE_BY_TIER = {
    "tiny": Engine.PYTHON,
    "small": Engine.PYTHON,
    "medium": Engine.DUCKDB,
    "large": Engine.DUCKDB,
    "very_large": Engine.DUCKDB,
    "huge": Engine.STREAMING,
    "massive": Engine.DISTRIBUTED,
}

# Size tier → Sampling strategy
STRATEGY_BY_TIER = {
    "tiny": SamplingStrategy.RESERVOIR,
    "small": SamplingStrategy.RESERVOIR_HLL,
    "medium": SamplingStrategy.RESERVOIR_HLL,
    "large": SamplingStrategy.METADATA_ROWGROUP,
    "very_large": SamplingStrategy.METADATA_ROWGROUP_HLL,
    "huge": SamplingStrategy.STREAMING_SKETCHES,
    "massive": SamplingStrategy.DISTRIBUTED_SKETCHES,
}

# Size tier → Memory mode
MEMORY_MODE_BY_TIER = {
    "tiny": MemoryMode.IN_MEMORY,
    "small": MemoryMode.IN_MEMORY,
    "medium": MemoryMode.IN_MEMORY,
    "large": MemoryMode.DISK_BACKED,
    "very_large": MemoryMode.STREAMING,
    "huge": MemoryMode.STREAMING,
    "massive": MemoryMode.DISTRIBUTED,
}

# Size tier → Scan depth
SCAN_DEPTH_BY_TIER = {
    "tiny": ScanDepth.FULL,
    "small": ScanDepth.FULL,
    "medium": ScanDepth.PARTIAL,
    "large": ScanDepth.PARTIAL,
    "very_large": ScanDepth.METADATA_ONLY,
    "huge": ScanDepth.ADAPTIVE,
    "massive": ScanDepth.METADATA_ONLY,
}

# Size tier → Execution type
EXECUTION_TYPE_BY_TIER = {
    "tiny": ExecutionType.EXACT,
    "small": ExecutionType.EXACT,
    "medium": ExecutionType.EXACT,
    "large": ExecutionType.APPROXIMATE,
    "very_large": ExecutionType.APPROXIMATE,
    "huge": ExecutionType.PROBABILISTIC,
    "massive": ExecutionType.PROBABILISTIC,
}


# ---------------------------------------------------------------------------
# Adaptive Execution Planner
# ---------------------------------------------------------------------------

def plan_execution(
    classification_result,  # ClassificationResult from Layer 3
    compression: Optional[str] = None,  # From Layer 2 validator
) -> ExecutionPlan:
    """
    Create an execution plan based on dataset classification.
    
    This is the main entry point for Layer 4.
    
    Args:
        classification_result: Output from Layer 3 classifier
        
    Returns:
        ExecutionPlan with all execution decisions
    """
    tier = classification_result.size_tier
    complexity = classification_result.complexity_score
    workload = classification_result.workload_type
    size_mb = classification_result.size_mb
    
    rationale = []
    
    # 1. Engine selection
    engine = _select_engine(tier, complexity, workload, rationale)
    fallback = _select_fallback_engine(engine)
    
    # 2. Sampling strategy
    strategy = _select_sampling_strategy(tier, complexity, workload, rationale)
    sample_size = _compute_sample_size(tier, complexity, classification_result.estimated_rows)
    
    # 3. Memory mode
    memory_mode = _select_memory_mode(tier, size_mb, complexity, rationale)
    memory_limit = _compute_memory_limit(memory_mode, size_mb)
    
    # 4. Scan depth
    scan_depth = _select_scan_depth(tier, complexity, rationale)
    max_rows_scan = _compute_max_rows_to_scan(scan_depth, classification_result.estimated_rows)
    
    # 5. Execution type
    exec_type = _select_execution_type(tier, complexity, rationale)
    error_tolerance = _compute_error_tolerance(exec_type)
    
    # 6. DuckDB-specific settings
    use_parquet_metadata = (strategy in (SamplingStrategy.METADATA_ROWGROUP, 
                                         SamplingStrategy.METADATA_ROWGROUP_HLL))
    use_pushdown = (engine == Engine.DUCKDB and complexity < 7)
    
    # 7. Sampling features
    use_hll = "hll" in strategy.value
    use_bloom = (complexity >= 7 and exec_type == ExecutionType.PROBABILISTIC)
    use_cms = (complexity >= 8 and exec_type == ExecutionType.PROBABILISTIC)
    
    # 8. Parallelization
    can_parallel = engine in (Engine.DUCKDB, Engine.STREAMING, Engine.DISTRIBUTED)
    batch_size = _compute_batch_size(tier, complexity)
    
    # 9. Cost estimates
    runtime_est = _estimate_runtime(tier, complexity, size_mb)
    memory_est = _estimate_memory(memory_mode, size_mb, sample_size)
    io_est = _estimate_io_operations(scan_depth, classification_result.estimated_rows)
    
    # 10. Build plan
    plan = ExecutionPlan(
        engine=engine,
        fallback_engine=fallback,
        sampling_strategy=strategy,
        sample_size=sample_size,
        memory_mode=memory_mode,
        memory_limit_mb=memory_limit,
        scan_depth=scan_depth,
        max_rows_to_scan=max_rows_scan,
        execution_type=exec_type,
        error_tolerance=error_tolerance,
        use_duckdb_parquet_metadata=use_parquet_metadata,
        use_duckdb_pushdown=use_pushdown,
        duckdb_threads=4 if engine == Engine.DUCKDB else 1,
        duckdb_memory_limit=f"{memory_limit}MB" if memory_limit else "4GB",
        use_hll=use_hll,
        hll_precision=14 if use_hll else 0,
        use_bloom_filter=use_bloom,
        use_count_min_sketch=use_cms,
        can_parallelize=can_parallel,
        recommended_batch_size=batch_size,
        requires_compression_handling=compression is not None,
        estimated_runtime_seconds=runtime_est,
        estimated_memory_mb=memory_est,
        estimated_io_operations=io_est,
        decision_rationale=rationale,
    )
    
    log.info("Execution plan created:")
    log.info("  Engine: %s | Strategy: %s", engine.value, strategy.value)
    log.info("  Memory: %s | Scan: %s | Type: %s", 
             memory_mode.value, scan_depth.value, exec_type.value)
    log.info("  Est. Runtime: %.1fs | Est. Memory: %.0f MB", 
             runtime_est if runtime_est else 0, 
             memory_est if memory_est else 0)
    
    return plan


# ---------------------------------------------------------------------------
# Decision functions
# ---------------------------------------------------------------------------

def _select_engine(tier: str, complexity: float, workload: str, rationale: List[str]) -> Engine:
    """Select execution engine."""
    engine = ENGINE_BY_TIER.get(tier, Engine.PYTHON)
    
    # Override based on complexity
    if complexity >= 8 and engine == Engine.DUCKDB:
        engine = Engine.STREAMING
        rationale.append(f"High complexity ({complexity}/10) → streaming engine")
    
    # Override based on workload
    if workload == "analytical_olap" and tier in ("medium", "large"):
        engine = Engine.DUCKDB
        rationale.append(f"Analytical workload → DuckDB for vectorized execution")
    
    rationale.append(f"Tier '{tier}' → {engine.value} engine")
    return engine


def _select_fallback_engine(primary: Engine) -> Optional[Engine]:
    """Select fallback engine if primary fails."""
    fallbacks = {
        Engine.DUCKDB: Engine.PYTHON,
        Engine.STREAMING: Engine.DUCKDB,
        Engine.DISTRIBUTED: Engine.STREAMING,
    }
    return fallbacks.get(primary)


def _select_sampling_strategy(tier: str, complexity: float, workload: str, rationale: List[str]) -> SamplingStrategy:
    """Select sampling strategy."""
    strategy = STRATEGY_BY_TIER.get(tier, SamplingStrategy.RESERVOIR)
    
    # Enhance for analytical workloads
    if workload == "analytical_olap" and strategy == SamplingStrategy.RESERVOIR:
        strategy = SamplingStrategy.RESERVOIR_HLL
        rationale.append("Analytical workload → add HLL for cardinality")
    
    rationale.append(f"Tier '{tier}' → {strategy.value} sampling")
    return strategy


def _compute_sample_size(tier: str, complexity: float, estimated_rows: Optional[int]) -> int:
    """Compute optimal sample size."""
    base_sizes = {
        "tiny": 100,
        "small": 500,
        "medium": 1000,
        "large": 5000,
        "very_large": 10000,
        "huge": 50000,
        "massive": 100000,
    }
    
    base = base_sizes.get(tier, 1000)
    
    # Adjust for complexity
    if complexity < 3:
        return base
    elif complexity < 6:
        return int(base * 1.5)
    else:
        return int(base * 2.0)


def _select_memory_mode(tier: str, size_mb: float, complexity: float, rationale: List[str]) -> MemoryMode:
    """Select memory management mode."""
    mode = MEMORY_MODE_BY_TIER.get(tier, MemoryMode.IN_MEMORY)
    
    # Override if dataset can't fit in typical RAM
    if size_mb > 8192:  # > 8GB
        mode = MemoryMode.STREAMING
        rationale.append(f"Large dataset ({size_mb:.0f} MB) → streaming mode")
    
    rationale.append(f"Memory mode: {mode.value}")
    return mode


def _compute_memory_limit(mode: MemoryMode, size_mb: float) -> Optional[int]:
    """Compute memory limit in MB."""
    if mode == MemoryMode.IN_MEMORY:
        # Allow 2x dataset size for processing
        return int(min(size_mb * 2, 8192))
    elif mode == MemoryMode.DISK_BACKED:
        return 4096  # 4GB limit, spill to disk
    else:
        return 1024  # Streaming uses constant memory


def _select_scan_depth(tier: str, complexity: float, rationale: List[str]) -> ScanDepth:
    """Select scan depth."""
    depth = SCAN_DEPTH_BY_TIER.get(tier, ScanDepth.FULL)
    rationale.append(f"Scan depth: {depth.value}")
    return depth


def _compute_max_rows_to_scan(depth: ScanDepth, estimated_rows: Optional[int]) -> Optional[int]:
    """Compute maximum rows to scan."""
    if depth == ScanDepth.FULL:
        return None  # Scan everything
    elif depth == ScanDepth.PARTIAL and estimated_rows:
        return min(estimated_rows, 1_000_000)  # Cap at 1M rows
    elif depth == ScanDepth.METADATA_ONLY:
        return 0  # No data scan
    else:
        return None


def _select_execution_type(tier: str, complexity: float, rationale: List[str]) -> ExecutionType:
    """Select execution precision type."""
    exec_type = EXECUTION_TYPE_BY_TIER.get(tier, ExecutionType.EXACT)
    
    if complexity >= 7:
        exec_type = ExecutionType.PROBABILISTIC
        rationale.append(f"High complexity ({complexity}/10) → probabilistic execution")
    
    rationale.append(f"Execution type: {exec_type.value}")
    return exec_type


def _compute_error_tolerance(exec_type: ExecutionType) -> Optional[float]:
    """Compute acceptable error tolerance."""
    if exec_type == ExecutionType.EXACT:
        return None
    elif exec_type == ExecutionType.APPROXIMATE:
        return 0.01  # 1% error tolerance
    else:  # PROBABILISTIC
        return 0.05  # 5% error tolerance


def _compute_batch_size(tier: str, complexity: float) -> Optional[int]:
    """Compute recommended batch size for streaming."""
    if tier in ("tiny", "small"):
        return None  # No batching needed
    elif tier == "medium":
        return 10000
    elif tier == "large":
        return 50000
    else:
        return 100000


def _estimate_runtime(tier: str, complexity: float, size_mb: float) -> float:
    """Estimate execution time in seconds."""
    # Base time by tier (assuming reasonable hardware)
    base_times = {
        "tiny": 0.1,
        "small": 0.5,
        "medium": 2.0,
        "large": 10.0,
        "very_large": 60.0,
        "huge": 300.0,
        "massive": 1800.0,
    }
    
    base = base_times.get(tier, 1.0)
    
    # Complexity multiplier
    complexity_multiplier = 1.0 + (complexity / 10.0)
    
    return base * complexity_multiplier


def _estimate_memory(mode: MemoryMode, size_mb: float, sample_size: int) -> float:
    """Estimate memory usage in MB."""
    if mode == MemoryMode.IN_MEMORY:
        # Assume 2x dataset size for processing overhead
        return min(size_mb * 2, 8192)
    elif mode == MemoryMode.STREAMING:
        # Constant memory based on sample size
        # Assume ~1KB per row
        return (sample_size * 1024) / (1024 * 1024)  # Convert to MB
    else:
        return 4096  # Default 4GB


def _estimate_io_operations(depth: ScanDepth, estimated_rows: Optional[int]) -> int:
    """Estimate number of I/O operations."""
    if depth == ScanDepth.METADATA_ONLY:
        return 1  # Single metadata read
    elif depth == ScanDepth.PARTIAL and estimated_rows:
        return estimated_rows // 10000  # One I/O per 10K rows
    else:
        return estimated_rows // 10000 if estimated_rows else 100
