"""
Semantic Classifier Demo — Shows the full intelligence layer

Demonstrates:
- Complexity scoring
- Workload type classification
- Structural classification
- Analytical suitability detection
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


def demo_semantic_classifier():
    """Demo the semantic classifier on different file types."""
    
    print("\n" + "=" * 70)
    print("SEMANTIC CLASSIFIER DEMONSTRATION")
    print("=" * 70)
    
    # Test files with different characteristics
    test_files = [
        ("data/sales_orders.csv", "Transactional/Event Data"),
        ("data/Sales_Customers.csv", "Entity/Dimension Table"),
        ("data/sales_invoicelines.csv", "Fact Table"),
        ("data/warehouse_stockitems.csv", "Analytical/Product Catalog"),
    ]
    
    results = []
    
    for file_path, description in test_files:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            print(f"\n⚠ Skipping {file_path} (not found)")
            continue
        
        print(f"\n{'=' * 70}")
        print(f"FILE: {file_path_obj.name}")
        print(f"Description: {description}")
        print('=' * 70)
        
        result = process_file(file_path, sample_size=100, save_sample=False)
        
        if result.success:
            classifier = result.layer25_classifier
            
            print(f"\n📊 SEMANTIC ANALYSIS:")
            print(f"  Size Tier: {classifier['size_tier']}")
            print(f"  Complexity: {classifier['complexity_score']}/10.0")
            
            print(f"\n  Complexity Breakdown:")
            for factor, value in classifier['complexity_factors'].items():
                print(f"    - {factor}: {value}")
            
            print(f"\n🏷️  WORKLOAD CLASSIFICATION:")
            print(f"  Type: {classifier['workload_type']}")
            print(f"  Relational: {'✓' if classifier['is_relational'] else '✗'}")
            print(f"  Time-Series: {'✓' if classifier['contains_time_series'] else '✗'}")
            print(f"  Contains PII: {'⚠' if classifier['contains_pii'] else '✓'}")
            print(f"  NLP-Heavy: {'✓' if classifier['nlp_heavy'] else '✗'}")
            print(f"  ML-Ready: {'✓' if classifier['ml_ready'] else '✗'}")
            
            if classifier['structural_type']:
                print(f"\n🏗️  STRUCTURAL TYPE: {classifier['structural_type']}")
            
            print(f"\n⚙️  EXECUTION PLAN:")
            print(f"  Engine: {classifier['engine_recommendation']}")
            print(f"  Strategy: {classifier['strategy_recommendation']}")
            print(f"  Recommended Sample: {classifier['recommended_sample_size']} rows")
            print(f"  Fits in Memory: {'✓' if classifier['can_fit_in_memory'] else '✗'}")
            print(f"  Requires Streaming: {'Yes' if classifier['requires_streaming'] else 'No'}")
            
            if classifier['estimated_rows']:
                print(f"\n📈 ESTIMATES:")
                print(f"  Rows: ~{classifier['estimated_rows']:,}")
                print(f"  Columns: {classifier['estimated_columns']}")
            
            results.append((file_path_obj.name, classifier))
        else:
            print(f"✗ Failed: {result.error}")
    
    # Summary comparison
    print(f"\n{'=' * 70}")
    print("WORKLOAD COMPARISON MATRIX")
    print('=' * 70)
    
    if results:
        print(f"\n{'File':<30} {'Workload Type':<20} {'Complexity':<12} {'Structure':<15}")
        print('-' * 77)
        
        for filename, classifier in results:
            workload = classifier['workload_type']
            complexity = f"{classifier['complexity_score']}/10"
            structure = classifier['structural_type'] or 'N/A'
            
            print(f"{filename:<30} {workload:<20} {complexity:<12} {structure:<15}")
    
    print(f"\n{'=' * 70}")
    print("DEMO COMPLETE")
    print('=' * 70)
    
    print("\n💡 KEY INSIGHTS:")
    print("  • Complexity scoring considers size, columns, format, and compression")
    print("  • Workload classification detects patterns in column names")
    print("  • Structural type identifies fact tables, dimensions, and event streams")
    print("  • Execution plan adapts based on complexity and workload type")
    print(f"\n{'=' * 70}")


if __name__ == "__main__":
    try:
        demo_semantic_classifier()
    except Exception as e:
        log.error("Demo failed: %s", e, exc_info=True)
        sys.exit(1)
