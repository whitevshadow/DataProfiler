"""Test PK Suppression Rules on Real Data"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from profiler.profiling.profiling_engine import profile_canonical_table

def test_warehouse_colors():
    """Test suppression rules on warehouse_colors (has temporal columns)."""
    print("=" * 80)
    print("TEST: warehouse_colors PK Detection with Suppression Rules")
    print("=" * 80)
    
    canonical_path = Path("output/canonical/warehouse_colors.canonical.json")
    
    if not canonical_path.exists():
        print(f"ERROR: File not found: {canonical_path}")
        return False
    
    print(f"\nProfiling: {canonical_path.name}")
    
    try:
        profile = profile_canonical_table(
            canonical_path,
            output_dir=Path("output/profiles_test")
        )
        
        print(f"\nProfile generated successfully")
        print(f"\nTable: {profile.table_name}")
        print(f"Total columns: {profile.table_profile.column_count}")
        
        # Check PK candidates
        print(f"\nPK Candidates: {len(profile.table_profile.pk_candidates)}")
        for col_name in profile.table_profile.pk_candidates:
            col = next((c for c in profile.columns if c.column_name == col_name), None)
            if col:
                print(f"  [PK] {col_name}: confidence={col.pk_confidence:.2f}")
        
        # Check suppressed columns
        print(f"\nSuppressed Columns:")
        for col in profile.columns:
            if not col.pk_candidate and col.uniqueness > 0.9:
                print(f"  [SUPPRESSED] {col.column_name}: uniqueness={col.uniqueness:.2f}")
                if col.pk_evidence and col.pk_evidence.warnings:
                    for warning in col.pk_evidence.warnings[:3]:
                        print(f"      - {warning}")
        
        # Expected results check (updated for semantic stability)
        expected_valid_pks = ["colorid"]  # Only true identifier
        expected_suppressed = ["colorname", "validfrom", "validto", "lasteditedby"]  # Includes semantic instability
        
        actual_pks = [c.column_name for c in profile.columns if c.pk_candidate]
        
        print(f"\n" + "=" * 80)
        print("VALIDATION:")
        print("=" * 80)
        
        success = True
        for pk in expected_valid_pks:
            if pk in actual_pks:
                print(f"[OK] {pk}: Correctly identified as PK candidate")
            else:
                print(f"[FAIL] {pk}: Should be PK candidate")
                success = False
        
        for col in expected_suppressed:
            if col not in actual_pks:
                print(f"[OK] {col}: Correctly suppressed")
            else:
                print(f"[FAIL] {col}: Should be suppressed")
                success = False
        
        return success
    
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_application_cities():
    """Test suppression rules on Application_Cities (also has temporal columns)."""
    print("\n\n" + "=" * 80)
    print("TEST: Application_Cities PK Detection with Suppression Rules")
    print("=" * 80)
    
    canonical_path = Path("output/canonical/Application_Cities.canonical.json")
    
    if not canonical_path.exists():
        print(f"ERROR: File not found: {canonical_path}")
        return False
    
    try:
        profile = profile_canonical_table(canonical_path)
        
        print(f"\nTable: {profile.table_name}")
        print(f"PK Candidates: {profile.table_profile.pk_candidates}")
        
        # cityid should be the primary PK candidate
        cityid_col = next((c for c in profile.columns if c.column_name == "cityid"), None)
        if cityid_col and cityid_col.pk_candidate:
            print(f"[OK] cityid correctly identified (confidence: {cityid_col.pk_confidence:.2f})")
        else:
            print(f"[FAIL] cityid NOT identified as PK")
            return False
        
        # validfrom, validto, lasteditedby should be suppressed
        temporal_cols = ["validfrom", "validto", "lasteditedby"]
        for col_name in temporal_cols:
            col = next((c for c in profile.columns if c.column_name == col_name), None)
            if col and not col.pk_candidate:
                print(f"[OK] {col_name} correctly suppressed")
            elif col and col.pk_candidate:
                print(f"[FAIL] {col_name} should be suppressed")
                return False
        
        return True
    
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\nTESTING PK SUPPRESSION RULES\n")
    
    test1 = test_warehouse_colors()
    test2 = test_application_cities()
    
    print("\n\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"warehouse_colors: {'[PASSED]' if test1 else '[FAILED]'}")
    print(f"Application_Cities: {'[PASSED]' if test2 else '[FAILED]'}")
    print(f"\nOverall: {'[ALL TESTS PASSED]' if (test1 and test2) else '[SOME TESTS FAILED]'}")
    
    sys.exit(0 if (test1 and test2) else 1)
