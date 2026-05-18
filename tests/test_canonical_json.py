"""
Test Canonical JSON Persistence

Verifies that CanonicalTable can be saved as lightweight JSON artifacts.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from profiler.engines import registry


def test_canonical_json_generation():
    """Test generating Canonical JSON from parsed data."""
    print("\n" + "=" * 70)
    print("TEST 1: Canonical JSON Generation")
    print("=" * 70)
    
    file_path = Path("data/sales_customercategories.csv")
    
    try:
        # Parse file
        table = registry.parse(
            file_path=file_path,
            file_format="csv",
            encoding="utf-8",
            sample_size=10
        )
        
        # Compute lightweight statistics
        table.compute_lightweight_statistics()
        
        # Generate canonical JSON
        canonical = table.to_canonical_json()
        
        print(f"✓ Generated Canonical JSON")
        print(f"\n  Table Metadata:")
        print(f"    table_id: {canonical['table_id']}")
        print(f"    table_name: {canonical['table_name']}")
        
        print(f"\n  Source:")
        print(f"    source_type: {canonical['source']['source_type']}")
        print(f"    format: {canonical['source']['format']}")
        print(f"    path: {canonical['source']['path']}")
        
        print(f"\n  Metadata:")
        print(f"    row_count_estimate: {canonical['metadata']['row_count_estimate']}")
        print(f"    column_count: {canonical['metadata']['column_count']}")
        print(f"    size_mb: {canonical['metadata']['size_mb']}")
        print(f"    engine: {canonical['metadata']['engine']}")
        
        print(f"\n  Columns ({len(canonical['columns'])}):")
        for col in canonical['columns']:
            print(f"    - {col['column_id']}: {col['original_name']} → {col['normalized_name']}")
            print(f"      Type: {col['physical_type']}, Nullable: {col['nullable']}")
            if 'sample_values' in col:
                print(f"      Samples: {col['sample_values'][:3]}...")
            if 'statistics' in col:
                print(f"      Stats: {col['statistics']}")
        
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_canonical_json_persistence():
    """Test saving Canonical JSON to disk."""
    print("\n" + "=" * 70)
    print("TEST 2: Canonical JSON Persistence")
    print("=" * 70)
    
    file_path = Path("data/application_deliverymethods.csv")
    output_path = Path("output/canonical/application_deliverymethods.canonical.json")
    
    try:
        # Parse file
        table = registry.parse(
            file_path=file_path,
            file_format="csv",
            encoding="utf-8",
            sample_size=20
        )
        
        # Save canonical JSON
        saved_path = table.save_canonical_json(output_path)
        
        print(f"✓ Saved to: {saved_path}")
        
        # Verify file exists
        assert saved_path.exists(), "File not saved"
        print(f"  ✓ File exists")
        
        # Verify file is valid JSON
        with open(saved_path, 'r') as f:
            data = json.load(f)
        print(f"  ✓ Valid JSON")
        
        # Verify structure
        assert "table_id" in data
        assert "table_name" in data
        assert "source" in data
        assert "metadata" in data
        assert "columns" in data
        print(f"  ✓ Valid structure")
        
        # Show file size
        file_size = saved_path.stat().st_size
        print(f"  File size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
        
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_column_normalization():
    """Test column name normalization."""
    print("\n" + "=" * 70)
    print("TEST 3: Column Name Normalization")
    print("=" * 70)
    
    from profiler.engines.format_engines import CanonicalTable
    
    test_cases = [
        ("Customer ID", "customer_id"),
        ("First Name", "first_name"),
        ("Email-Address", "email_address"),
        ("Product.Name", "product_name"),
        ("Total Price ($)", "total_price"),
        ("Date/Time", "date_time"),
        ("  Spaces  ", "spaces"),
        ("Multiple   Spaces", "multiple_spaces"),
    ]
    
    all_passed = True
    for original, expected in test_cases:
        normalized = CanonicalTable.normalize_column_name(original)
        status = "✓" if normalized == expected else "✗"
        if normalized != expected:
            all_passed = False
        print(f"  {status} '{original}' → '{normalized}' (expected: '{expected}')")
    
    return all_passed


def test_lightweight_statistics():
    """Test lightweight statistics computation."""
    print("\n" + "=" * 70)
    print("TEST 4: Lightweight Statistics")
    print("=" * 70)
    
    file_path = Path("data/warehouse_colors.csv")
    
    try:
        table = registry.parse(
            file_path=file_path,
            file_format="csv",
            encoding="utf-8",
            sample_size=15
        )
        
        # Compute stats
        table.compute_lightweight_statistics()
        
        print(f"✓ Computed statistics for {len(table.columns)} columns")
        
        for col in table.columns:
            print(f"\n  Column: {col.name}")
            print(f"    Original: {col.original_name}")
            print(f"    Normalized: {col.normalized_name}")
            print(f"    Nullable: {col.nullable}")
            print(f"    Null Count: {col.null_count}")
            print(f"    Distinct Count: {col.distinct_count}")
            if col.avg_length:
                print(f"    Avg Length: {col.avg_length:.2f}")
            if col.sample_values:
                print(f"    Sample Values: {col.sample_values[:5]}")
        
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_batch_persistence():
    """Test batch saving multiple files."""
    print("\n" + "=" * 70)
    print("TEST 5: Batch Canonical JSON Persistence")
    print("=" * 70)
    
    files = [
        "sales_buyinggroups.csv",
        "warehouse_colors.csv",
        "warehouse_packagetypes.csv",
        "application_paymentmethods.csv",
    ]
    
    output_dir = Path("output/canonical")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = []
    
    for filename in files:
        file_path = Path("data") / filename
        output_path = output_dir / f"{file_path.stem}.canonical.json"
        
        try:
            # Parse and save
            table = registry.parse(
                file_path=file_path,
                file_format="csv",
                encoding="utf-8",
                sample_size=10
            )
            
            table.save_canonical_json(output_path)
            
            # Verify
            with open(output_path, 'r') as f:
                data = json.load(f)
            
            results.append({
                'file': filename,
                'output': output_path.name,
                'columns': len(data['columns']),
                'size_kb': output_path.stat().st_size / 1024,
                'success': True
            })
            
        except Exception as e:
            results.append({
                'file': filename,
                'error': str(e),
                'success': False
            })
    
    print(f"\n  Batch Results:")
    print(f"  {'File':<35} {'Output':<40} {'Cols':<6} {'Size':<10} {'Status'}")
    print(f"  {'-'*100}")
    
    for result in results:
        if result['success']:
            print(f"  {result['file']:<35} {result['output']:<40} {result['columns']:<6} "
                  f"{result['size_kb']:.1f} KB    {'✓':<10}")
        else:
            print(f"  {result['file']:<35} {'N/A':<40} {'N/A':<6} {'N/A':<10} {'✗'}")
    
    success_count = sum(1 for r in results if r['success'])
    print(f"\n  ✓ Successfully saved {success_count}/{len(results)} Canonical JSON files")
    
    return success_count == len(results)


def test_json_structure():
    """Test complete JSON structure matches specification."""
    print("\n" + "=" * 70)
    print("TEST 6: JSON Structure Compliance")
    print("=" * 70)
    
    file_path = Path("data/Sales_Customers.csv")
    output_path = Path("output/canonical/test_structure.canonical.json")
    
    try:
        # Parse with sampling
        table = registry.parse(
            file_path=file_path,
            file_format="csv",
            encoding="utf-8",
            sample_size=20
        )
        
        # Save
        table.save_canonical_json(output_path, table_id="tbl_test_001", table_name="customers")
        
        # Load and verify
        with open(output_path, 'r') as f:
            data = json.load(f)
        
        print(f"✓ Loaded JSON structure")
        
        # Verify top-level keys
        required_keys = ["table_id", "table_name", "source", "metadata", "columns"]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"
            print(f"  ✓ Has key: {key}")
        
        # Verify source structure
        assert "source_type" in data["source"]
        assert "format" in data["source"]
        assert "path" in data["source"]
        print(f"  ✓ Source structure valid")
        
        # Verify metadata structure
        assert "row_count_estimate" in data["metadata"]
        assert "column_count" in data["metadata"]
        assert "sampling_strategy" in data["metadata"]
        print(f"  ✓ Metadata structure valid")
        
        # Verify columns structure
        assert len(data["columns"]) > 0
        first_col = data["columns"][0]
        required_col_keys = ["column_id", "original_name", "normalized_name", 
                             "position", "physical_type", "nullable"]
        for key in required_col_keys:
            assert key in first_col, f"Missing column key: {key}"
        print(f"  ✓ Column structure valid")
        
        # Show sample
        print(f"\n  Sample JSON (first column):")
        print(f"  {json.dumps(first_col, indent=4)}")
        
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all canonical JSON tests."""
    print("\n" + "=" * 70)
    print("CANONICAL JSON PERSISTENCE TEST SUITE")
    print("=" * 70)
    print("\nTesting reusable intermediate artifact generation")
    print("Design: Lightweight, cached, lineage-aware\n")
    
    tests = [
        ("JSON Generation", test_canonical_json_generation),
        ("JSON Persistence", test_canonical_json_persistence),
        ("Column Normalization", test_column_normalization),
        ("Lightweight Statistics", test_lightweight_statistics),
        ("Batch Persistence", test_batch_persistence),
        ("JSON Structure", test_json_structure),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ Unexpected error in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Final summary
    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    
    for name, result in results:
        status = "✓" if result else "✗"
        print(f"{status} {name}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n" + "=" * 70)
        print("✓✓✓ ALL TESTS PASSED! ✓✓✓")
        print("=" * 70)
        print("\nCanonical JSON Persistence is working!")
        print("\nKey Achievements:")
        print("  ✓ Generates lightweight JSON artifacts")
        print("  ✓ Column normalization (Customer ID → customer_id)")
        print("  ✓ Lightweight statistics (null count, distinct estimate)")
        print("  ✓ Sample values for semantic analysis")
        print("  ✓ Proper JSON structure (table_id, source, metadata, columns)")
        print("  ✓ File persistence with caching")
        print("\nBenefits:")
        print("  → Avoids reparsing files")
        print("  → Enables lineage tracking")
        print("  → Input for downstream layers")
        print("  → Debugging artifact")
        print("\nReady for Layer 6 integration!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
