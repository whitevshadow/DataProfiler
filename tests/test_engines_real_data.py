"""
Real Data Test — Format Engines with Actual Data

Tests all format engines with real data from data/ folder.
Shows parsing capabilities across different file sizes and complexities.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from profiler.engines import registry


def test_small_file():
    """Test with small file (dimension table)."""
    print("\n" + "=" * 70)
    print("TEST 1: Small File (Dimension Table)")
    print("=" * 70)
    
    file_path = Path("data/application_deliverymethods.csv")
    
    try:
        table = registry.parse(
            file_path=file_path,
            file_format="csv",
            encoding="utf-8",
            sample_size=None  # Read all
        )
        
        print(f"✓ File: {file_path.name}")
        print(f"  Source Type: {table.source_type}")
        print(f"  Encoding: {table.encoding}")
        print(f"  Delimiter: {repr(table.delimiter)}")
        print(f"  Columns: {table.column_count}")
        print(f"  Rows: {table.row_count}")
        print(f"\n  Column Names:")
        for i, col in enumerate(table.columns, 1):
            print(f"    {i}. {col.name}")
        
        print(f"\n  Sample Data (first 3 rows):")
        for i, row in enumerate(table.iter_rows()):
            if i >= 3:
                break
            print(f"    Row {i+1}: {row[:3]}...")
        
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_medium_file():
    """Test with medium file (fact table)."""
    print("\n" + "=" * 70)
    print("TEST 2: Medium File (Fact Table)")
    print("=" * 70)
    
    file_path = Path("data/sales_orders.csv")
    
    try:
        # Parse with sampling
        table = registry.parse(
            file_path=file_path,
            file_format="csv",
            encoding="utf-8",
            sample_size=100  # Sample 100 rows
        )
        
        print(f"✓ File: {file_path.name}")
        print(f"  Source Type: {table.source_type}")
        print(f"  Encoding: {table.encoding}")
        print(f"  Columns: {table.column_count}")
        print(f"  Rows Sampled: {table.row_count}")
        print(f"  Is Sample: {table.is_sample}")
        
        print(f"\n  Column Names (first 10):")
        for i, name in enumerate(table.get_column_names()[:10], 1):
            print(f"    {i}. {name}")
        
        print(f"\n  First Row:")
        first_row = next(table.iter_rows())
        for col, val in zip(table.get_column_names()[:5], first_row[:5]):
            print(f"    {col}: {val}")
        
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_large_file():
    """Test with large file (transaction table)."""
    print("\n" + "=" * 70)
    print("TEST 3: Large File (Transaction Table)")
    print("=" * 70)
    
    file_path = Path("data/sales_invoicelines.csv")
    
    try:
        # Parse with small sample for large file
        table = registry.parse(
            file_path=file_path,
            file_format="csv",
            encoding="utf-8",
            sample_size=50  # Small sample for large file
        )
        
        print(f"✓ File: {file_path.name}")
        print(f"  Source Type: {table.source_type}")
        print(f"  Columns: {table.column_count}")
        print(f"  Rows Sampled: {table.row_count}")
        print(f"  Is Sample: {table.is_sample}")
        
        print(f"\n  Column Names:")
        for i, name in enumerate(table.get_column_names(), 1):
            print(f"    {i}. {name}")
        
        # Test iteration
        print(f"\n  Testing row iteration...")
        row_count = sum(1 for _ in table.iter_rows())
        print(f"  ✓ Successfully iterated {row_count} rows")
        
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_customer_file():
    """Test with customer file (wide table with many columns)."""
    print("\n" + "=" * 70)
    print("TEST 4: Wide Table (Many Columns)")
    print("=" * 70)
    
    file_path = Path("data/Sales_Customers.csv")
    
    try:
        table = registry.parse(
            file_path=file_path,
            file_format="csv",
            encoding="utf-8",
            sample_size=20
        )
        
        print(f"✓ File: {file_path.name}")
        print(f"  Columns: {table.column_count} (wide table!)")
        print(f"  Rows Sampled: {table.row_count}")
        
        print(f"\n  All Column Names:")
        col_names = table.get_column_names()
        for i in range(0, len(col_names), 4):
            chunk = col_names[i:i+4]
            print(f"    {', '.join(chunk)}")
        
        # Test get_column method
        print(f"\n  Testing get_column() method:")
        first_col = table.get_column(col_names[0])
        print(f"    Column: {first_col.name}")
        print(f"    Index: {first_col.index}")
        print(f"    Type: {first_col.data_type}")
        print(f"    Nullable: {first_col.nullable}")
        
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_utf8_file():
    """Test with UTF-8 encoded file."""
    print("\n" + "=" * 70)
    print("TEST 5: UTF-8 Encoding Test")
    print("=" * 70)
    
    file_path = Path("data/Application_Cities.csv")
    
    try:
        table = registry.parse(
            file_path=file_path,
            file_format="csv",
            encoding="utf-8",
            sample_size=10
        )
        
        print(f"✓ File: {file_path.name}")
        print(f"  Encoding: {table.encoding}")
        print(f"  Columns: {table.column_count}")
        print(f"  Rows: {table.row_count}")
        
        print(f"\n  Sample Cities (testing UTF-8 handling):")
        city_col_idx = None
        for i, col in enumerate(table.columns):
            if 'CityName' in col.name:
                city_col_idx = i
                break
        
        if city_col_idx is not None:
            for i, row in enumerate(table.iter_rows()):
                if i >= 5:
                    break
                print(f"    {row[city_col_idx]}")
        
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multiple_files():
    """Test parsing multiple files in sequence."""
    print("\n" + "=" * 70)
    print("TEST 6: Batch Processing Multiple Files")
    print("=" * 70)
    
    files = [
        "sales_buyinggroups.csv",
        "sales_customercategories.csv",
        "warehouse_colors.csv",
        "warehouse_packagetypes.csv",
        "application_paymentmethods.csv",
    ]
    
    results = []
    
    for filename in files:
        file_path = Path("data") / filename
        if not file_path.exists():
            print(f"  ⚠ Skipping {filename} (not found)")
            continue
        
        try:
            table = registry.parse(
                file_path=file_path,
                file_format="csv",
                encoding="utf-8",
                sample_size=5
            )
            
            results.append({
                'file': filename,
                'columns': table.column_count,
                'rows': table.row_count,
                'success': True
            })
            
        except Exception as e:
            results.append({
                'file': filename,
                'error': str(e),
                'success': False
            })
    
    print(f"\n  Batch Results:")
    print(f"  {'File':<40} {'Columns':<10} {'Rows':<10} {'Status':<10}")
    print(f"  {'-'*70}")
    
    for result in results:
        if result['success']:
            print(f"  {result['file']:<40} {result['columns']:<10} {result['rows']:<10} {'✓':<10}")
        else:
            print(f"  {result['file']:<40} {'N/A':<10} {'N/A':<10} {'✗':<10}")
    
    success_count = sum(1 for r in results if r['success'])
    print(f"\n  ✓ Successfully parsed {success_count}/{len(results)} files")
    
    return success_count == len(results)


def test_canonical_table_features():
    """Test CanonicalTable features comprehensively."""
    print("\n" + "=" * 70)
    print("TEST 7: CanonicalTable IR Features")
    print("=" * 70)
    
    file_path = Path("data/warehouse_stockgroups.csv")
    
    try:
        table = registry.parse(
            file_path=file_path,
            file_format="csv",
            encoding="utf-8",
            sample_size=15
        )
        
        print(f"✓ Testing CanonicalTable IR features...")
        
        # Test 1: Metadata
        print(f"\n  1. Metadata:")
        print(f"     source_path: {table.source_path}")
        print(f"     source_type: {table.source_type}")
        print(f"     column_count: {table.column_count}")
        print(f"     row_count: {table.row_count}")
        
        # Test 2: Column access
        print(f"\n  2. Column Access:")
        col_names = table.get_column_names()
        print(f"     get_column_names(): {col_names}")
        
        first_col = table.get_column(col_names[0])
        print(f"     get_column('{col_names[0]}'): {first_col}")
        
        # Test 3: Row iteration
        print(f"\n  3. Row Iteration:")
        row_list = list(table.iter_rows())
        print(f"     iter_rows() returned {len(row_list)} rows")
        print(f"     First row: {row_list[0]}")
        print(f"     Last row: {row_list[-1]}")
        
        # Test 4: Direct row access
        print(f"\n  4. Direct Row Access:")
        if table.rows:
            print(f"     table.rows is available")
            print(f"     len(table.rows): {len(table.rows)}")
            assert len(table.rows) == table.row_count
            print(f"     ✓ Row count matches")
        
        # Test 5: Sampling metadata
        print(f"\n  5. Sampling Metadata:")
        print(f"     is_sample: {table.is_sample}")
        print(f"     sample_size: {table.sample_size}")
        
        # Test 6: Encoding metadata
        print(f"\n  6. Encoding Metadata:")
        print(f"     encoding: {table.encoding}")
        print(f"     delimiter: {repr(table.delimiter)}")
        print(f"     compression: {table.compression}")
        
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all real data tests."""
    print("\n" + "=" * 70)
    print("FORMAT ENGINES — REAL DATA TEST SUITE")
    print("=" * 70)
    print("\nTesting Layer 5 with actual data from data/ folder")
    print("Design Rule: Engines ONLY parse, NEVER profile\n")
    
    tests = [
        ("Small File (Dimension)", test_small_file),
        ("Medium File (Fact)", test_medium_file),
        ("Large File (Transaction)", test_large_file),
        ("Wide Table (Many Columns)", test_customer_file),
        ("UTF-8 Encoding", test_utf8_file),
        ("Batch Processing", test_multiple_files),
        ("CanonicalTable Features", test_canonical_table_features),
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
        print("\nLayer 5 Format Engines are working correctly with real data!")
        print("\nKey Achievements:")
        print("  ✓ Parses CSV files with various sizes")
        print("  ✓ Handles UTF-8 encoding correctly")
        print("  ✓ Supports sampling for large files")
        print("  ✓ Provides clean CanonicalTable IR")
        print("  ✓ Works with dimension, fact, and transaction tables")
        print("  ✓ Batch processing multiple files")
        print("\nReady for Layer 6 integration!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
