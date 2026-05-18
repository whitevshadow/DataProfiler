"""
Data Profiling Pipeline — Orchestrates all layers

Layer 1: Connector  — Connect to file, validate access
Layer 2: Validator  — Verify format, encoding, compression
Layer 3: Sampler    — Adaptive sampling based on file size
Layer 4: Profiler   — Statistical profiling (future)

Usage:
    from pipeline import process_file
    
    result = process_file("data/sales_orders.csv")
    print(result)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path if needed
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Layer 1 — Connector
try:
    from connector.file.connect_file import connect as file_connect
except ImportError:
    from file_profiler.connectors.file.connect_file import connect as file_connect

# Layer 2 — Validator
try:
    from profiler.validator.validator import validate
    from profiler.validator.errors import (
        FileIntakeError,
        EmptyFileError,
        CorruptFileError,
        UnsupportedEncodingError,
    )
except ImportError:
    from file_profiler.profiler.validator.validator import validate
    from file_profiler.profiler.validator.errors import (
        FileIntakeError,
        EmptyFileError,
        CorruptFileError,
        UnsupportedEncodingError,
    )

# Layer 2.5 — Classifier (NEW: Semantic Intelligence)
try:
    from profiler.classifier.classifier import classify as semantic_classify
except ImportError:
    from file_profiler.profiler.classifier.classifier import classify as semantic_classify

# Layer 3 — Execution Planner (NEW: The Brain)
try:
    from profiler.planner.execution_planner import plan_execution
except ImportError:
    from file_profiler.profiler.planner.execution_planner import plan_execution

# Layer 4 — Sampler (using existing sampling.py)
try:
    from profiler.sampling.sampling import (
        classify_workload,
        python_reservoir_sampling,
        get_duckdb_connection,
        get_reader,
        duckdb_reservoir_sampling,
        duckdb_rowgroup_sampling,
        save_arrow_table,
    )
except ImportError:
    from file_profiler.profiler.sampling.sampling import (
        classify_workload,
        python_reservoir_sampling,
        get_duckdb_connection,
        get_reader,
        duckdb_reservoir_sampling,
        duckdb_rowgroup_sampling,
        save_arrow_table,
    )

log = logging.getLogger(__name__)

# Output directory for samples
OUTPUT_DIR = Path("./output")
OUTPUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Pipeline Result
# ---------------------------------------------------------------------------

class PipelineResult:
    """Result of the full pipeline execution."""
    
    def __init__(self):
        self.layer1_connector = {}
        self.layer2_validator = {}
        self.layer25_classifier = {}  # Semantic classifier
        self.layer3_planner = {}      # NEW: Execution planner
        self.layer4_sampler = {}      # Renamed from layer3
        self.success = False
        self.error = None
    
    def to_dict(self) -> dict:
        """Return result as dictionary."""
        return {
            "success": self.success,
            "error": self.error,
            "layer1_connector": self.layer1_connector,
            "layer2_validator": self.layer2_validator,
            "layer25_classifier": self.layer25_classifier,
            "layer3_planner": self.layer3_planner,
            "layer4_sampler": self.layer4_sampler,
        }
    
    def __repr__(self) -> str:
        if self.success:
            return f"<PipelineResult: SUCCESS | {self.layer1_connector.get('file_name')}>"
        else:
            return f"<PipelineResult: FAILED | {self.error}>"


# ---------------------------------------------------------------------------
# Main Pipeline Function
# ---------------------------------------------------------------------------

def process_file(
    file_path: str | Path,
    sample_size: int = 1000,
    save_sample: bool = True,
) -> PipelineResult:
    """
    Process a file through the full profiling pipeline.
    
    Args:
        file_path: Path to file
        sample_size: Number of rows to sample
        save_sample: Whether to save the sample to output/
        
    Returns:
        PipelineResult with metadata from all layers
    """
    result = PipelineResult()
    
    try:
        # =================================================================
        # LAYER 1 — CONNECTOR
        # =================================================================
        log.info("=" * 60)
        log.info("LAYER 1 — CONNECTOR")
        log.info("=" * 60)
        
        connector_result = file_connect(file_path)
        result.layer1_connector = connector_result
        
        log.info("✓ Connector: %s", connector_result["file_format"])
        log.info("  URI: %s", connector_result["uri"])
        log.info("  Size: %.2f MB", connector_result["size_mb"])
        
        # =================================================================
        # LAYER 2 — VALIDATOR
        # =================================================================
        log.info("=" * 60)
        log.info("LAYER 2 — VALIDATOR")
        log.info("=" * 60)
        
        validation_result = validate(file_path)
        
        result.layer2_validator = {
            "path": str(validation_result.path),
            "size_bytes": validation_result.size_bytes,
            "encoding": validation_result.encoding,
            "is_bom_present": validation_result.is_bom_present,
            "bom_encoding": validation_result.bom_encoding,
            "compression": validation_result.compression,
            "delimiter_hint": validation_result.delimiter_hint,
        }
        
        log.info("✓ Validator:")
        log.info("  Encoding: %s", validation_result.encoding)
        log.info("  Compression: %s", validation_result.compression or "None")
        log.info("  Delimiter: %s", validation_result.delimiter_hint or "Unknown")
        log.info("  BOM: %s", "Yes" if validation_result.is_bom_present else "No")
        
        # Update Layer 1 result with Layer 2 findings
        result.layer1_connector["encoding"] = validation_result.encoding
        result.layer1_connector["compression"] = validation_result.compression
        
        # =================================================================
        # LAYER 2.5 — SEMANTIC CLASSIFIER (NEW!)
        # =================================================================
        log.info("=" * 60)
        log.info("LAYER 2.5 — SEMANTIC CLASSIFIER")
        log.info("=" * 60)
        
        # Quick peek at columns for classification
        column_names = None
        estimated_rows = None
        
        try:
            if connector_result["file_format"] == "csv":
                import csv
                
                # Try multiple encodings if needed
                encodings_to_try = [
                    validation_result.encoding,
                    'utf-8',
                    'utf-8-sig',
                    'latin-1',
                ]
                
                # Remove duplicates while preserving order
                seen = set()
                encodings_to_try = [x for x in encodings_to_try if not (x in seen or seen.add(x))]
                
                last_error = None
                for encoding in encodings_to_try:
                    try:
                        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                            reader = csv.reader(f)
                            header = next(reader)
                            column_names = header
                            
                            # Count rows (quick estimate from first few)
                            row_count = 0
                            for i, _ in enumerate(reader):
                                row_count += 1
                                if i > 10000:  # Stop after 10k for estimate
                                    break
                            
                            if row_count > 10000:
                                # Extrapolate based on file size
                                bytes_per_row = validation_result.size_bytes / row_count
                                estimated_rows = int(validation_result.size_bytes / bytes_per_row)
                            else:
                                estimated_rows = row_count
                        
                        log.debug("Successfully read metadata with encoding: %s", encoding)
                        break  # Success - exit loop
                        
                    except (UnicodeDecodeError, UnicodeError) as e:
                        last_error = e
                        log.debug("Failed with encoding %s: %s", encoding, e)
                        continue
                
                if column_names is None and last_error:
                    log.warning("Could not extract column metadata after trying multiple encodings: %s", last_error)
                    
        except Exception as e:
            log.warning("Could not extract column metadata: %s", e)
        
        # Perform semantic classification
        classification = semantic_classify(
            source_type=connector_result["source_type"],
            size_bytes=connector_result["size_bytes"],
            file_format=connector_result["file_format"],
            encoding=validation_result.encoding,
            compression=validation_result.compression,
            column_names=column_names,
            estimated_rows=estimated_rows,
        )
        
        result.layer25_classifier = {
            "size_tier": classification.size_tier,
            "engine_recommendation": classification.engine_recommendation,
            "strategy_recommendation": classification.strategy_recommendation,
            "complexity_score": classification.complexity_score,
            "complexity_factors": classification.complexity_factors,
            "workload_type": classification.workload_type,
            "is_relational": classification.is_relational,
            "contains_time_series": classification.contains_time_series,
            "contains_pii": classification.contains_pii,
            "nlp_heavy": classification.nlp_heavy,
            "ml_ready": classification.ml_ready,
            "structural_type": classification.structural_type,
            "estimated_rows": classification.estimated_rows,
            "estimated_columns": classification.estimated_columns,
            "recommended_sample_size": classification.recommended_sample_size,
            "requires_streaming": classification.requires_streaming,
            "can_fit_in_memory": classification.can_fit_in_memory,
        }
        
        log.info("✓ Classifier:")
        log.info("  Complexity: %.1f/10.0", classification.complexity_score)
        log.info("  Workload Type: %s", classification.workload_type)
        if classification.structural_type:
            log.info("  Structure: %s", classification.structural_type)
        log.info("  Relational: %s", "Yes" if classification.is_relational else "No")
        log.info("  Time-Series: %s", "Yes" if classification.contains_time_series else "No")
        if classification.contains_pii:
            log.info("  ⚠ Contains PII: Yes")
        if classification.nlp_heavy:
            log.info("  NLP-Heavy: Yes")
        if classification.ml_ready:
            log.info("  ML-Ready: Yes")
        
        # =================================================================
        # LAYER 3 — EXECUTION PLANNER (NEW!)
        # =================================================================
        log.info("=" * 60)
        log.info("LAYER 3 — EXECUTION PLANNER")
        log.info("=" * 60)
        
        # Create execution plan based on classification
        execution_plan = plan_execution(classification, validation_result.compression)
        
        result.layer3_planner = {
            "engine": execution_plan.engine.value,
            "fallback_engine": execution_plan.fallback_engine.value if execution_plan.fallback_engine else None,
            "sampling_strategy": execution_plan.sampling_strategy.value,
            "sample_size": execution_plan.sample_size,
            "memory_mode": execution_plan.memory_mode.value,
            "memory_limit_mb": execution_plan.memory_limit_mb,
            "scan_depth": execution_plan.scan_depth.value,
            "max_rows_to_scan": execution_plan.max_rows_to_scan,
            "execution_type": execution_plan.execution_type.value,
            "error_tolerance": execution_plan.error_tolerance,
            "use_hll": execution_plan.use_hll,
            "use_bloom_filter": execution_plan.use_bloom_filter,
            "use_count_min_sketch": execution_plan.use_count_min_sketch,
            "can_parallelize": execution_plan.can_parallelize,
            "estimated_runtime_seconds": execution_plan.estimated_runtime_seconds,
            "estimated_memory_mb": execution_plan.estimated_memory_mb,
            "estimated_io_operations": execution_plan.estimated_io_operations,
            "decision_rationale": execution_plan.decision_rationale,
        }
        
        log.info("✓ Execution Plan:")
        log.info("  Engine: %s (fallback: %s)", 
                 execution_plan.engine.value, 
                 execution_plan.fallback_engine.value if execution_plan.fallback_engine else "none")
        log.info("  Strategy: %s", execution_plan.sampling_strategy.value)
        log.info("  Memory: %s (limit: %s MB)", 
                 execution_plan.memory_mode.value,
                 execution_plan.memory_limit_mb or "N/A")
        log.info("  Scan: %s | Execution: %s", 
                 execution_plan.scan_depth.value,
                 execution_plan.execution_type.value)
        log.info("  Probabilistic DS: HLL=%s, Bloom=%s, CMS=%s",
                 "✓" if execution_plan.use_hll else "✗",
                 "✓" if execution_plan.use_bloom_filter else "✗",
                 "✓" if execution_plan.use_count_min_sketch else "✗")
        log.info("  Cost Est: %.1fs runtime, %.0f MB memory, %d I/O ops",
                 execution_plan.estimated_runtime_seconds or 0,
                 execution_plan.estimated_memory_mb or 0,
                 execution_plan.estimated_io_operations or 0)
        
        # Log decision rationale
        if execution_plan.decision_rationale:
            log.info("  Decisions:")
            for decision in execution_plan.decision_rationale:
                log.info("    • %s", decision)
        
        # =================================================================
        # LAYER 4 — SAMPLER (Executes the plan)
        # =================================================================
        log.info("=" * 60)
        log.info("LAYER 4 — SAMPLER")
        log.info("=" * 60)
        
        # Use execution plan decisions
        size_mb = connector_result["size_mb"]
        tier = classification.size_tier
        engine = execution_plan.engine.value
        strategy = execution_plan.sampling_strategy.value
        sample_size = execution_plan.sample_size
        
        log.info("  Executing plan...")
        log.info("  Tier: %s", tier.upper())
        log.info("  Engine: %s", engine.upper())
        log.info("  Strategy: %s", strategy)
        log.info("  Sample size: %d", sample_size)
        
        sample_path = None
        total_rows = 0
        sample_rows = 0
        
        # Python engine for small files
        if engine == "python":
            header, rows, total_rows = python_reservoir_sampling(
                file_path,
                sample_size=sample_size
            )
            sample_rows = len(rows)
            
            if save_sample:
                import csv
                sample_path = OUTPUT_DIR / f"{Path(file_path).stem}_sample.csv"
                with open(sample_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(header)
                    writer.writerows(rows)
        
        # DuckDB engine for larger files
        elif engine == "duckdb":
            con = get_duckdb_connection()
            reader = get_reader(str(file_path))
            
            # Count total rows
            count_query = f"SELECT COUNT(*) AS cnt FROM {reader}"
            total_rows = con.execute(count_query).fetchone()[0]
            
            # Sample based on strategy
            if strategy in ("reservoir_hll", "reservoir"):
                table = duckdb_reservoir_sampling(con, reader, sample_size)
            elif strategy in ("metadata_rowgroup", "metadata_rowgroup_hll"):
                table = duckdb_rowgroup_sampling(con, reader, sample_size)
            else:
                # Fallback to reservoir
                table = duckdb_reservoir_sampling(con, reader, sample_size)
            
            sample_rows = len(table)
            
            if save_sample:
                import pyarrow.parquet as pq
                sample_path = OUTPUT_DIR / f"{Path(file_path).stem}_sample.parquet"
                pq.write_table(table, sample_path)
                
                # Also save as CSV for easier viewing
                csv_path = OUTPUT_DIR / f"{Path(file_path).stem}_sample.csv"
                df = table.to_pandas()
                df.to_csv(csv_path, index=False)
                sample_path = csv_path  # Point to CSV for readability
            
            con.close()
        
        result.layer3_sampler = {
            "tier": tier,
            "engine": engine,
            "strategy": strategy,
            "total_rows": total_rows,
            "sample_rows": sample_rows,
            "sample_path": str(sample_path) if sample_path else None,
            "sample_saved": save_sample,
        }
        
        log.info("✓ Sampler:")
        log.info("  Total rows: %d", total_rows)
        log.info("  Sample rows: %d", sample_rows)
        if sample_path:
            log.info("  Sample saved: %s", sample_path)
        
        # =================================================================
        # SUCCESS
        # =================================================================
        result.success = True
        
        log.info("=" * 60)
        log.info("✓ PIPELINE COMPLETED SUCCESSFULLY")
        log.info("=" * 60)
        
    except FileNotFoundError as e:
        result.error = f"File not found: {e}"
        log.error("✗ Layer 1 failed: %s", result.error)
    
    except EmptyFileError as e:
        result.error = f"File is empty: {e}"
        log.error("✗ Layer 2 failed: %s", result.error)
    
    except UnsupportedEncodingError as e:
        result.error = f"Unsupported encoding: {e}"
        log.error("✗ Layer 2 failed: %s", result.error)
    
    except FileIntakeError as e:
        result.error = f"Validation error: {e}"
        log.error("✗ Layer 2 failed: %s", result.error)
    
    except Exception as e:
        result.error = f"Unexpected error: {e}"
        log.error("✗ Pipeline failed: %s", result.error)
        import traceback
        log.error(traceback.format_exc())
    
    return result


# ---------------------------------------------------------------------------
# Batch Processing
# ---------------------------------------------------------------------------

def process_directory(
    directory_path: str | Path,
    sample_size: int = 1000,
    save_sample: bool = True,
) -> list[PipelineResult]:
    """
    Process all files in a directory.
    
    Args:
        directory_path: Path to directory
        sample_size: Number of rows to sample per file
        save_sample: Whether to save samples
        
    Returns:
        List of PipelineResult for each file
    """
    directory = Path(directory_path)
    
    if not directory.is_dir():
        raise ValueError(f"Not a directory: {directory}")
    
    # Supported extensions
    SUPPORTED_EXTS = {
        '.csv', '.tsv', '.txt',
        '.parquet', '.pq', '.parq',
    }
    
    results = []
    
    for file_path in sorted(directory.iterdir()):
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTS:
            log.info("\n\nProcessing: %s", file_path.name)
            result = process_file(file_path, sample_size, save_sample)
            results.append(result)
    
    # Summary
    success_count = sum(1 for r in results if r.success)
    fail_count = len(results) - success_count
    
    log.info("\n" + "=" * 60)
    log.info("BATCH PROCESSING SUMMARY")
    log.info("=" * 60)
    log.info("Total files: %d", len(results))
    log.info("Success: %d", success_count)
    log.info("Failed: %d", fail_count)
    
    return results


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )
    
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <file_or_directory>")
        sys.exit(1)
    
    target = sys.argv[1]
    target_path = Path(target)
    
    if target_path.is_file():
        result = process_file(target_path)
        print("\n" + "=" * 60)
        print("RESULT:")
        print("=" * 60)
        import json
        print(json.dumps(result.to_dict(), indent=2))
    
    elif target_path.is_dir():
        results = process_directory(target_path)
        print("\n" + "=" * 60)
        print("RESULTS:")
        print("=" * 60)
        for r in results:
            if r.success:
                print(f"✓ {r.layer1_connector['file_name']}")
            else:
                print(f"✗ {r.error}")
    
    else:
        print(f"Error: Not a file or directory: {target}")
        sys.exit(1)
