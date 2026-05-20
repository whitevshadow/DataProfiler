"""
Test FK Detection

Verify that FK detection correctly distinguishes:
- PRIMARY_KEY (entity anchors like cityid)
- FOREIGN_KEY (relational references like stateprovinceid)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from profiler.profiling.profiling_engine import profile_canonical_table


def test_fk_detection():
    """Test FK detection on real datasets."""
    
    test_files = [
        ("Application_Cities", {
            "expected_pk": ["cityid"],
            "expected_fk": ["stateprovinceid"],
        }),
        ("Sales_Customers", {
            "expected_pk": ["customerid"],
            "expected_fk": ["primarycontactpersonid", "alternatecontactpersonid", "deliverycityid", "postalcityid"],
        }),
    ]
    
    print("\n" + "=" * 100)
    print("FK DETECTION TEST — Distinguish PK vs FK")
    print("=" * 100)
    
    for table_name, expectations in test_files:
        print(f"\n[TEST] {table_name}")
        print("-" * 100)
        
        canonical_path = Path(f"output/canonical/{table_name}.canonical.json")
        if not canonical_path.exists():
            print(f"  SKIP - file not found")
            continue
        
        try:
            profile = profile_canonical_table(canonical_path, Path("output/profiles"))
            
            print(f"\nResults:")
            print(f"  PK Candidates: {profile.table_profile.pk_candidates}")
            print(f"  FK Candidates: {profile.table_profile.fk_candidates}")
            
            print(f"\nColumn Analysis (High Uniqueness Only):")
            print(f"  {'Column':30s} | {'Role':20s} | PK Conf | FK Conf | Referenced Entity")
            print(f"  {'-' * 30}-+-{'-' * 20}-+---------+---------+{'-' * 25}")
            
            for col in sorted(profile.columns, key=lambda c: c.uniqueness, reverse=True):
                if col.uniqueness < 0.9:
                    continue
                
                role = col.relational_role.value if col.relational_role else "unknown"
                ref_entity = ""
                if col.fk_evidence and col.fk_evidence.referenced_entity:
                    ref_entity = col.fk_evidence.referenced_entity
                
                print(f"  {col.column_name:30s} | {role:20s} | {col.pk_confidence:7.2f} | {col.fk_confidence:7.2f} | {ref_entity}")
            
            # Validation
            print(f"\nValidation:")
            expected_pks = expectations["expected_pk"]
            expected_fks = expectations["expected_fk"]
            actual_pks = profile.table_profile.pk_candidates
            actual_fks = profile.table_profile.fk_candidates
            
            # Check PKs
            for pk in expected_pks:
                if pk in actual_pks:
                    print(f"  [OK] {pk} correctly identified as PK")
                else:
                    print(f"  [FAIL] {pk} NOT identified as PK (expected)")
            
            # Check FKs
            for fk in expected_fks:
                if fk in actual_fks:
                    print(f"  [OK] {fk} correctly identified as FK")
                else:
                    print(f"  [FAIL] {fk} NOT identified as FK (expected)")
            
            # Check for false positives (columns that shouldn't be PK but are)
            for pk in actual_pks:
                if pk not in expected_pks:
                    print(f"  [WARN] {pk} identified as PK but may be FK")
            
        except Exception as e:
            print(f"  [ERROR] {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 100)


if __name__ == "__main__":
    test_fk_detection()
