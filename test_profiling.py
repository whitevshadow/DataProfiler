"""
Test Profiling Engine

Verify the profiling layer works on real Canonical JSON artifacts.
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from profiler.profiling.profiling_engine import profile_canonical_table, batch_profile

def test_single_file():
    """Test profiling a single file."""
    print("=" * 80)
    print("TEST 1: Single File Profiling")
    print("=" * 80)
    
    canonical_path = Path("output/canonical/warehouse_colors.canonical.json")
    
    if not canonical_path.exists():
        print(f"❌ File not found: {canonical_path}")
        return False
    
    print(f"\nProfiling: {canonical_path.name}")
    
    try:
        profile = profile_canonical_table(
            canonical_path,
            output_dir=Path("output/profiles")
        )
        
        print(f"✅ Profile generated successfully!")
        print(f"\nTable: {profile.table_name}")
        print(f"Columns: {profile.table_profile.column_count}")
        print(f"Quality Score: {profile.table_profile.quality_score:.2f}")
        print(f"Completeness: {profile.table_profile.completeness_score:.2f}")
        
        # PK candidates
        if profile.table_profile.pk_candidates:
            print(f"\nPK Candidates:")
            for col_name in profile.table_profile.pk_candidates:
                col = next((c for c in profile.columns if c.column_name == col_name), None)
                if col:
                    print(f"  • {col_name}: {col.pk_confidence:.2f}")
                    if col.pk_evidence:
                        for reason in col.pk_evidence.reasons:
                            print(f"      - {reason}")
        
        # Quality flags
        flagged_columns = [c for c in profile.columns if c.quality_flags]
        if flagged_columns:
            print(f"\nQuality Issues:")
            for col in flagged_columns:
                print(f"  • {col.column_name}: {[f.value for f in col.quality_flags]}")
        
        return True
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_batch_profiling():
    """Test batch profiling."""
    print("\n" + "=" * 80)
    print("TEST 2: Batch Profiling (5 files)")
    print("=" * 80)
    
    canonical_dir = Path("output/canonical")
    
    # Get first 5 files for quick test
    files = list(canonical_dir.glob("*.canonical.json"))[:5]
    
    if not files:
        print(f"❌ No canonical files found in {canonical_dir}")
        return False
    
    print(f"\nProfiling {len(files)} files...")
    for f in files:
        print(f"  • {f.name}")
    
    try:
        profiles = batch_profile(
            canonical_dir,
            output_dir=Path("output/profiles"),
            parallel=True,
            max_workers=2
        )
        
        print(f"\n✅ Profiled {len(profiles)} files")
        
        # Summary
        for filename, profile in profiles.items():
            pk_count = len(profile.table_profile.pk_candidates)
            quality = profile.table_profile.quality_score
            print(f"  • {filename}: PKs={pk_count}, Quality={quality:.2f}")
        
        return True
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pk_detection():
    """Test PK detection accuracy."""
    print("\n" + "=" * 80)
    print("TEST 3: PK Detection Accuracy")
    print("=" * 80)
    
    test_files = [
        ("Application_Cities.canonical.json", "cityid"),
        ("warehouse_colors.canonical.json", "colorid"),
        ("Sales_Customers.canonical.json", "customerid"),
    ]
    
    results = []
    
    for filename, expected_pk in test_files:
        canonical_path = Path(f"output/canonical/{filename}")
        
        if not canonical_path.exists():
            print(f"⚠️  Skipping {filename} (not found)")
            continue
        
        try:
            profile = profile_canonical_table(canonical_path)
            
            # Check if expected PK was detected
            detected = expected_pk in profile.table_profile.pk_candidates
            
            if detected:
                col = next((c for c in profile.columns if c.column_name == expected_pk), None)
                confidence = col.pk_confidence if col else 0.0
                print(f"✅ {filename}: Detected {expected_pk} (confidence: {confidence:.2f})")
                results.append(True)
            else:
                print(f"❌ {filename}: Failed to detect {expected_pk}")
                print(f"   Detected: {profile.table_profile.pk_candidates}")
                results.append(False)
        
        except Exception as e:
            print(f"❌ {filename}: Error - {e}")
            results.append(False)
    
    accuracy = sum(results) / len(results) if results else 0.0
    print(f"\nPK Detection Accuracy: {accuracy:.1%} ({sum(results)}/{len(results)})")
    
    return accuracy >= 0.8  # 80% threshold


if __name__ == "__main__":
    print("\nPROFILING ENGINE TEST SUITE\n")
    
    test1 = test_single_file()
    test2 = test_batch_profiling()
    test3 = test_pk_detection()
    
    print("\n" + "=" * 80)
    print("TEST RESULTS")
    print("=" * 80)
    print(f"Single File:     {'✅ PASS' if test1 else '❌ FAIL'}")
    print(f"Batch Profiling: {'✅ PASS' if test2 else '❌ FAIL'}")
    print(f"PK Detection:    {'✅ PASS' if test3 else '❌ FAIL'}")
    
    all_passed = test1 and test2 and test3
    print(f"\nOverall: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    sys.exit(0 if all_passed else 1)
