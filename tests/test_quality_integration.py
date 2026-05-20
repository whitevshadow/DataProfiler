"""
Comprehensive Quality Engine Integration Test

Tests the enhanced quality engine integrated with the full profiling pipeline.
Shows quality scores, quality flags, and quality issues for real datasets.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from profiler.profiling.profiling_engine import profile_canonical_table


def test_quality_integration():
    """Test quality engine with real profiled data."""
    
    print("\n" + "=" * 100)
    print("QUALITY ENGINE INTEGRATION TEST")
    print("=" * 100)
    print("\nTesting quality detection on real profiled datasets:")
    
    test_files = [
        "warehouse_colors.canonical.json",
        "Application_Cities.canonical.json",
    ]
    
    for filename in test_files:
        canonical_path = Path(f"output/canonical/{filename}")
        if not canonical_path.exists():
            print(f"\n[SKIP] {filename} - file not found")
            continue
        
        print(f"\n{'-' * 100}")
        print(f"Dataset: {filename}")
        print(f"{'-' * 100}")
        
        try:
            profile = profile_canonical_table(canonical_path, Path("output/profiles"))
            
            # Table-level quality
            print(f"\n[TABLE QUALITY]")
            print(f"  Overall Score:    {profile.table_profile.quality_score:.2f}/1.00")
            print(f"  Completeness:     {profile.table_profile.completeness_score:.2f}/1.00")
            print(f"  Total Flags:      {profile.table_profile.total_quality_flags}")
            print(f"  Columns w/Issues: {profile.table_profile.columns_with_issues}/{profile.table_profile.column_count}")
            
            # Column-level quality
            print(f"\n[COLUMN QUALITY]")
            print(f"  {'Column':30s} | Quality | Flags | Issues")
            print(f"  {'-' * 30}-+---------+-------+{'-' * 40}")
            
            for col in profile.columns:
                flag_names = [f.value for f in col.quality_flags]
                flag_summary = ", ".join(flag_names) if flag_names else "None"
                if len(flag_summary) > 37:
                    flag_summary = flag_summary[:34] + "..."
                
                print(f"  {col.column_name:30s} | {col.quality_score:7.2f} | {len(col.quality_flags):5d} | {flag_summary}")
            
            # Show problematic columns
            problematic = [c for c in profile.columns if c.quality_score < 0.90]
            if problematic:
                print(f"\n[QUALITY ISSUES DETECTED]")
                for col in problematic:
                    print(f"\n  Column: {col.column_name}")
                    print(f"  Score: {col.quality_score:.2f}/1.00")
                    for flag in col.quality_flags:
                        print(f"    - {flag.value.upper()}")
            else:
                print(f"\n[OK] No significant quality issues detected!")
            
            # Show relational classification
            print(f"\n[RELATIONAL CLASSIFICATION]")
            print(f"  PK: {profile.table_profile.pk_candidates}")
            print(f"  FK: {profile.table_profile.fk_candidates}")
            
        except Exception as e:
            print(f"  [ERROR] {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 100)
    print("INTEGRATION TEST COMPLETE")
    print("=" * 100)


if __name__ == "__main__":
    test_quality_integration()
