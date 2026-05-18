"""
Quick test script to verify the connector and pipeline work.

Runs basic tests without requiring full demo.
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test if all imports work."""
    print("Testing imports...")
    try:
        from connector.file.connect_file import connect, FileConnector
        print("✓ Connector imports successful")
        
        from pipeline import process_file, process_directory
        print("✓ Pipeline imports successful")
        
        from profiler.validator.validator import validate
        print("✓ Validator imports successful")
        
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False


def test_connector_basic():
    """Test basic file connector functionality."""
    print("\nTesting connector...")
    
    try:
        from connector.file.connect_file import connect
        
        # Test with data directory
        data_dir = Path("data")
        if not data_dir.exists():
            print("⚠ data/ directory not found, skipping connector test")
            return True
        
        # Get first CSV file
        csv_files = list(data_dir.glob("*.csv"))
        if not csv_files:
            print("⚠ No CSV files in data/, skipping connector test")
            return True
        
        test_file = csv_files[0]
        print(f"  Testing with: {test_file.name}")
        
        result = connect(test_file)
        
        assert result["source_type"] == "file", "Wrong source_type"
        assert result["exists"] == True, "File should exist"
        assert result["accessible"] == True, "File should be accessible"
        assert result["is_remote"] == False, "Local file should not be remote"
        assert "file_name" in result, "Missing file_name"
        assert "file_format" in result, "Missing file_format"
        assert "size_mb" in result, "Missing size_mb"
        
        print(f"✓ Connector test passed")
        print(f"  Format: {result['file_format']}")
        print(f"  Size: {result['size_mb']} MB")
        
        return True
        
    except Exception as e:
        print(f"✗ Connector test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_validator_basic():
    """Test validator functionality."""
    print("\nTesting validator...")
    
    try:
        from profiler.validator.validator import validate
        
        # Test with data directory
        data_dir = Path("data")
        if not data_dir.exists():
            print("⚠ data/ directory not found, skipping validator test")
            return True
        
        # Get first CSV file
        csv_files = list(data_dir.glob("*.csv"))
        if not csv_files:
            print("⚠ No CSV files in data/, skipping validator test")
            return True
        
        test_file = csv_files[0]
        print(f"  Testing with: {test_file.name}")
        
        result = validate(test_file)
        
        assert result.path.exists(), "Validated path should exist"
        assert result.size_bytes > 0, "File should have size"
        assert result.encoding is not None, "Encoding should be detected"
        
        print(f"✓ Validator test passed")
        print(f"  Encoding: {result.encoding}")
        print(f"  Compression: {result.compression or 'None'}")
        print(f"  Delimiter: {result.delimiter_hint or 'Unknown'}")
        
        return True
        
    except Exception as e:
        print(f"✗ Validator test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pipeline_basic():
    """Test full pipeline."""
    print("\nTesting pipeline...")
    
    try:
        from pipeline import process_file
        
        # Test with data directory
        data_dir = Path("data")
        if not data_dir.exists():
            print("⚠ data/ directory not found, skipping pipeline test")
            return True
        
        # Get first CSV file
        csv_files = list(data_dir.glob("*.csv"))
        if not csv_files:
            print("⚠ No CSV files in data/, skipping pipeline test")
            return True
        
        test_file = csv_files[0]
        print(f"  Testing with: {test_file.name}")
        
        result = process_file(test_file, sample_size=10, save_sample=False)
        
        if result.success:
            print(f"✓ Pipeline test passed")
            print(f"  Total rows: {result.layer4_sampler.get('total_rows', 'N/A')}")
            print(f"  Sample rows: {result.layer4_sampler.get('sample_rows', 'N/A')}")
            print(f"  Tier: {result.layer4_sampler.get('tier', 'N/A')}")
            return True
        else:
            print(f"✗ Pipeline failed: {result.error}")
            return False
        
    except Exception as e:
        print(f"✗ Pipeline test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("AGENTIC PROFILER — QUICK TEST")
    print("=" * 60)
    
    results = []
    
    # Test imports
    results.append(("Imports", test_imports()))
    
    # Test connector
    results.append(("Connector", test_connector_basic()))
    
    # Test validator
    results.append(("Validator", test_validator_basic()))
    
    # Test pipeline
    results.append(("Pipeline", test_pipeline_basic()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{name:20s} {status}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print("-" * 60)
    print(f"Total: {passed}/{total} passed")
    print("=" * 60)
    
    if passed == total:
        print("\n✓ All tests passed!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
