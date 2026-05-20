"""
Quick PK Detection Test with Enhanced Suppression Rules
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from profiler.profiling.profiling_engine import profile_canonical_table


def test_enhanced_suppressions():
    """Test all tables with enhanced suppression rules."""
    
    canonical_dir = Path("output/canonical")
    test_files = [
        "warehouse_colors.canonical.json",
        "Application_Cities.canonical.json",
        "Sales_Customers.canonical.json",
    ]
    
    results = {}
    
    print("\n" + "=" * 80)
    print("PK DETECTION TEST - ENHANCED SUPPRESSION RULES")
    print("=" * 80)
    
    for filename in test_files:
        filepath = canonical_dir / filename
        if not filepath.exists():
            print(f"\n[SKIP] {filename} - file not found")
            continue
        
        print(f"\n[TEST] {filename}")
        print("-" * 80)
        
        try:
            profile = profile_canonical_table(filepath, Path("output/profiles"))
            
            table_name = profile.table_name
            pk_candidates = profile.table_profile.pk_candidates
            
            print(f"Table: {table_name}")
            print(f"PK Candidates: {pk_candidates}")
            print(f"Quality Score: {profile.table_profile.quality_score:.2f}")
            
            # Show high-uniqueness columns and their status
            print("\nHigh-Uniqueness Columns:")
            for col in profile.columns:
                if col.uniqueness >= 0.9:
                    status = "PK CANDIDATE" if col.pk_candidate else "SUPPRESSED"
                    print(f"  - {col.column_name:30s} | {status:15s} | Conf: {col.pk_confidence:.2f} | Type: {col.physical_type}")
            
            results[table_name] = {
                "pk_candidates": pk_candidates,
                "quality_score": profile.table_profile.quality_score,
                "status": "PASS"
            }
            
        except Exception as e:
            print(f"ERROR: {e}")
            results[table_name] = {"status": "FAIL", "error": str(e)}
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    for table_name, result in results.items():
        status = result.get("status", "UNKNOWN")
        pk_count = len(result.get("pk_candidates", []))
        print(f"{table_name:30s} | Status: {status:6s} | PK Count: {pk_count}")
    
    print("\n" + "=" * 80)
    
    # Save results
    output_file = Path("output/pk_detection_results.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    test_enhanced_suppressions()
