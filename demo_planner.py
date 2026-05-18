"""
Execution Planner Demo — Shows Layer 4: The Brain

Demonstrates intelligent execution planning:
- Engine selection (Python, DuckDB, Streaming)
- Sampling strategy (Reservoir, HLL, Metadata, Sketches)
- Memory mode decisions
- Scan depth optimization
- Exact vs probabilistic execution
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pipeline import process_file

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)

log = logging.getLogger(__name__)


def demo_execution_planner():
    """Demo the execution planner on different dataset sizes."""
    
    print("\n" + "=" * 80)
    print("EXECUTION PLANNER DEMONSTRATION")
    print("Layer 4 — The Brain of the System")
    print("=" * 80)
    
    # Test files with different sizes/complexities
    test_files = [
        ("data/warehouse_stockitems.csv", "Tiny (0.06 MB)", "Exact, in-memory"),
        ("data/Sales_Customers.csv", "Small (1.11 MB)", "Exact, in-memory"),
        ("data/sales_orders.csv", "Medium (115 MB)", "Exact, DuckDB"),
        ("data/sales_invoicelines.csv", "Large (143 MB)", "Approximate, partial scan"),
    ]
    
    results = []
    
    for file_path, size_desc, expected_strategy in test_files:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            print(f"\n⚠ Skipping {file_path} (not found)")
            continue
        
        print(f"\n{'=' * 80}")
        print(f"FILE: {file_path_obj.name} ({size_desc})")
        print(f"Expected: {expected_strategy}")
        print('=' * 80)
        
        result = process_file(file_path, sample_size=100, save_sample=False)
        
        if result.success:
            planner = result.layer3_planner
            
            print(f"\n⚙️  EXECUTION PLAN:")
            print(f"  Engine: {planner['engine'].upper()}")
            if planner['fallback_engine']:
                print(f"  Fallback: {planner['fallback_engine']}")
            print(f"  Strategy: {planner['sampling_strategy']}")
            print(f"  Sample Size: {planner['sample_size']:,} rows")
            
            print(f"\n💾 MEMORY MANAGEMENT:")
            print(f"  Mode: {planner['memory_mode']}")
            if planner['memory_limit_mb']:
                print(f"  Limit: {planner['memory_limit_mb']} MB")
            
            print(f"\n📖 SCAN CONFIGURATION:")
            print(f"  Depth: {planner['scan_depth']}")
            if planner['max_rows_to_scan']:
                print(f"  Max Rows: {planner['max_rows_to_scan']:,}")
            print(f"  Execution Type: {planner['execution_type']}")
            if planner['error_tolerance']:
                print(f"  Error Tolerance: {planner['error_tolerance']*100:.1f}%")
            
            print(f"\n🎲 PROBABILISTIC DATA STRUCTURES:")
            print(f"  HyperLogLog: {'✓' if planner['use_hll'] else '✗'}")
            print(f"  Bloom Filter: {'✓' if planner['use_bloom_filter'] else '✗'}")
            print(f"  Count-Min Sketch: {'✓' if planner['use_count_min_sketch'] else '✗'}")
            
            print(f"\n⚡ PERFORMANCE:")
            print(f"  Can Parallelize: {'✓' if planner['can_parallelize'] else '✗'}")
            print(f"  Est. Runtime: {planner['estimated_runtime_seconds']:.2f}s")
            print(f"  Est. Memory: {planner['estimated_memory_mb']:.0f} MB")
            print(f"  Est. I/O Ops: {planner['estimated_io_operations']:,}")
            
            if planner['decision_rationale']:
                print(f"\n🧠 DECISION RATIONALE:")
                for i, decision in enumerate(planner['decision_rationale'], 1):
                    print(f"  {i}. {decision}")
            
            results.append((file_path_obj.name, planner))
        else:
            print(f"✗ Failed: {result.error}")
    
    # Comparison matrix
    print(f"\n{'=' * 80}")
    print("EXECUTION PLAN COMPARISON")
    print('=' * 80)
    
    if results:
        print(f"\n{'File':<30} {'Engine':<10} {'Strategy':<25} {'Memory':<12} {'Exec Type':<15}")
        print('-' * 92)
        
        for filename, planner in results:
            engine = planner['engine']
            strategy = planner['sampling_strategy']
            memory = planner['memory_mode']
            exec_type = planner['execution_type']
            
            print(f"{filename:<30} {engine:<10} {strategy:<25} {memory:<12} {exec_type:<15}")
    
    print(f"\n{'=' * 80}")
    print("KEY EXECUTION STRATEGIES")
    print('=' * 80)
    print("""
📊 DECISION MATRIX:

Size Tier      Engine        Strategy                Memory         Scan      Execution
────────────────────────────────────────────────────────────────────────────────────────
Tiny           Python        Reservoir               In-Memory      Full      Exact
Small          Python        Reservoir + HLL         In-Memory      Full      Exact
Medium         DuckDB        Reservoir + HLL         In-Memory      Partial   Exact
Large          DuckDB        Metadata + RowGroup     Disk-Backed    Partial   Approximate
Very Large     DuckDB        Metadata + RowGroup+HLL Streaming      Metadata  Approximate
Huge           Streaming     Streaming + Sketches    Streaming      Adaptive  Probabilistic
Massive        Distributed   Distributed Sketches    Distributed    Metadata  Probabilistic

💡 KEY INSIGHTS:
  • Engine selection adapts to dataset size and complexity
  • Sampling strategy evolves from exact to probabilistic
  • Memory mode prevents OOM on large datasets
  • Scan depth minimizes I/O operations
  • Execution type trades accuracy for performance when needed
    """)
    
    print(f"{'=' * 80}")
    print("DEMO COMPLETE")
    print('=' * 80)


if __name__ == "__main__":
    try:
        demo_execution_planner()
    except Exception as e:
        log.error("Demo failed: %s", e, exc_info=True)
        sys.exit(1)
