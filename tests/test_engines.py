"""
Test Format Engines — Verify parsing capabilities

Tests all format engines with sample data.
"""

import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from profiler.engines.format_engines import registry


def test_csv_engine():
    """Test CSV engine."""
    print("\n" + "=" * 60)
    print("TEST: CSV Engine")
    print("=" * 60)
    
    file_path = Path("data/Sales_Customers.csv")
    if not file_path.exists():
        print("⚠ Skipping - file not found")
        return None
    
    try:
        table = registry.parse(
            file_path=file_path,
            file_format="csv",
            encoding="utf-8",
            sample_size=5
        )
        
        print(f"✓ Parsed: {table.source_path}")
        print(f"  Source Type: {table.source_type}")
        print(f"  Columns: {table.column_count}")
        print(f"  Rows: {table.row_count}")
        print(f"  Encoding: {table.encoding}")
        print(f"  Delimiter: {repr(table.delimiter)}")
        print(f"  Column names: {table.get_column_names()[:5]}...")
        if table.rows:
            print(f"  First row: {table.rows[0][:3]}...")
        
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_json_engine():
    """Test JSON engine."""
    print("\n" + "=" * 60)
    print("TEST: JSON Engine")
    print("=" * 60)
    
    # Create a test JSON file
    test_data = [
        {"id": 1, "name": "Alice", "age": 30, "city": "NYC"},
        {"id": 2, "name": "Bob", "age": 25, "city": "LA"},
        {"id": 3, "name": "Charlie", "age": 35, "city": "Chicago"},
        {"id": 4, "name": "Diana", "age": 28, "city": "Boston"},
    ]
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_data, f)
        temp_path = Path(f.name)
    
    try:
        table = registry.parse(
            file_path=temp_path,
            file_format="json",
            sample_size=2
        )
        
        print(f"✓ Parsed: {table.source_type}")
        print(f"  Columns: {table.column_count}")
        print(f"  Rows: {table.row_count}")
        print(f"  Sample: {table.is_sample}")
        print(f"  Column names: {table.get_column_names()}")
        if table.rows:
            print(f"  First row: {table.rows[0]}")
            print(f"  Second row: {table.rows[1]}")
        
        temp_path.unlink()  # Clean up
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        temp_path.unlink()  # Clean up
        return False


def test_ndjson_engine():
    """Test NDJSON (newline-delimited JSON) engine."""
    print("\n" + "=" * 60)
    print("TEST: NDJSON Engine")
    print("=" * 60)
    
    # Create a test NDJSON file
    test_lines = [
        {"id": 1, "product": "Laptop", "price": 999.99},
        {"id": 2, "product": "Mouse", "price": 29.99},
        {"id": 3, "product": "Keyboard", "price": 79.99},
    ]
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        for line in test_lines:
            f.write(json.dumps(line) + '\n')
        temp_path = Path(f.name)
    
    try:
        table = registry.parse(
            file_path=temp_path,
            file_format="jsonl",
            sample_size=2
        )
        
        print(f"✓ Parsed: {table.source_type}")
        print(f"  Columns: {table.column_count}")
        print(f"  Rows: {table.row_count}")
        print(f"  Column names: {table.get_column_names()}")
        if table.rows:
            print(f"  First row: {table.rows[0]}")
        
        temp_path.unlink()  # Clean up
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        temp_path.unlink()  # Clean up
        return False


def test_parquet_engine():
    """Test Parquet engine."""
    print("\n" + "=" * 60)
    print("TEST: Parquet Engine")
    print("=" * 60)
    
    # Try to find a parquet file
    parquet_files = list(Path("output").glob("*.parquet"))
    if not parquet_files:
        print("⚠ No parquet files found in output/")
        return None
    
    file_path = parquet_files[0]
    
    try:
        table = registry.parse(
            file_path=file_path,
            file_format="parquet",
            sample_size=3
        )
        
        print(f"✓ Parsed: {file_path.name}")
        print(f"  Source Type: {table.source_type}")
        print(f"  Columns: {table.column_count}")
        print(f"  Rows: {table.row_count}")
        print(f"  Column names: {table.get_column_names()[:5]}...")
        if table.rows:
            print(f"  First row sample: {table.rows[0][:3]}...")
        
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_canonical_table_methods():
    """Test CanonicalTable utility methods."""
    print("\n" + "=" * 60)
    print("TEST: CanonicalTable Methods")
    print("=" * 60)
    
    file_path = Path("data/application_deliverymethods.csv")
    if not file_path.exists():
        print("⚠ Skipping - file not found")
        return None
    
    try:
        table = registry.parse(
            file_path=file_path,
            file_format="csv",
            sample_size=10
        )
        
        print(f"✓ Testing utility methods...")
        
        # Test get_column_names
        names = table.get_column_names()
        print(f"  Column names: {names}")
        
        # Test get_column
        first_col = table.get_column(names[0])
        print(f"  First column: {first_col.name} at index {first_col.index}")
        
        # Test iter_rows
        row_count = 0
        for row in table.iter_rows():
            row_count += 1
        print(f"  Iterated {row_count} rows")
        
        # Verify counts match
        assert row_count == table.row_count, "Row count mismatch"
        print(f"  ✓ Row iteration works correctly")
        
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("FORMAT ENGINES TEST SUITE")
    print("=" * 60)
    print("\nTesting Layer 5 — Format Engines")
    print("Design Rule: Engines ONLY parse, NEVER profile\n")
    
    results = [
        ("CSV Engine", test_csv_engine()),
        ("JSON Engine", test_json_engine()),
        ("NDJSON Engine", test_ndjson_engine()),
        ("Parquet Engine", test_parquet_engine()),
        ("CanonicalTable Methods", test_canonical_table_methods()),
    ]
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    for name, result in results:
        if result is True:
            print(f"✓ {name}")
        elif result is False:
            print(f"✗ {name}")
        else:
            print(f"⚠ {name} (skipped)")
    
    passed = sum(1 for _, r in results if r is True)
    total = sum(1 for _, r in results if r is not None)
    skipped = sum(1 for _, r in results if r is None)
    
    print(f"\nTotal: {passed}/{total} passed, {skipped} skipped")
    
    if passed == total and total > 0:
        print("\n✓ All tests passed!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
