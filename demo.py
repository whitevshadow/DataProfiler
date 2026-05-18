"""
Demo script for the file connector and pipeline.

Shows:
1. Layer 1 — Connector (connect to file, validate access)
2. Layer 2 — Validator (detect encoding, compression, format)
3. Layer 3 — Sampler (adaptive sampling, save sample)
"""

import json
import logging
import sys
from pathlib import Path

# Add parent directory to path if needed
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Layer 1 — Connector
try:
    from connector.file.connect_file import connect
except ImportError:
    from file_profiler.connectors.file.connect_file import connect

# Full pipeline
try:
    from pipeline import process_file, process_directory
except ImportError:
    from file_profiler.pipeline import process_file, process_directory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)

log = logging.getLogger(__name__)


def demo_connector_only():
    """Demo: Layer 1 Connector only"""
    print("\n" + "=" * 70)
    print("DEMO 1: Layer 1 — Connector Only")
    print("=" * 70)
    
    file_path = "data/sales_orders.csv"
    
    try:
        result = connect(file_path)
        
        print("\n✓ Connection successful!")
        print("\nSource Descriptor:")
        print(json.dumps(result, indent=2))
        
        # Expected output:
        # {
        #   "source_type": "file",
        #   "uri": "file:///path/to/sales_orders.csv",
        #   "is_remote": false,
        #   "file_name": "sales_orders.csv",
        #   "file_format": "csv",
        #   "size_bytes": 12345,
        #   "size_mb": 0.01,
        #   "encoding": null,
        #   "compression": null,
        #   "accessible": true,
        #   "exists": true
        # }
        
    except Exception as e:
        print(f"\n✗ Connection failed: {e}")


def demo_full_pipeline_single_file():
    """Demo: Full pipeline on a single file"""
    print("\n" + "=" * 70)
    print("DEMO 2: Full Pipeline — Single File")
    print("=" * 70)
    
    file_path = "data/sales_orders.csv"
    
    result = process_file(file_path, sample_size=1000, save_sample=True)
    
    print("\n" + "=" * 70)
    print("PIPELINE RESULT")
    print("=" * 70)
    print(json.dumps(result.to_dict(), indent=2, default=str))


def demo_full_pipeline_directory():
    """Demo: Full pipeline on entire directory"""
    print("\n" + "=" * 70)
    print("DEMO 3: Full Pipeline — Batch Processing")
    print("=" * 70)
    
    directory_path = "data"
    
    results = process_directory(directory_path, sample_size=500, save_sample=True)
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    for i, result in enumerate(results, 1):
        if result.success:
            file_name = result.layer1_connector.get("file_name", "Unknown")
            size_mb = result.layer1_connector.get("size_mb", 0)
            encoding = result.layer2_validator.get("encoding", "Unknown")
            total_rows = result.layer3_sampler.get("total_rows", 0)
            sample_rows = result.layer3_sampler.get("sample_rows", 0)
            
            print(f"\n{i}. ✓ {file_name}")
            print(f"   Size: {size_mb:.2f} MB")
            print(f"   Encoding: {encoding}")
            print(f"   Rows: {total_rows:,} (sampled: {sample_rows:,})")
        else:
            print(f"\n{i}. ✗ FAILED: {result.error}")


def demo_layer_details():
    """Demo: Show detailed layer outputs"""
    print("\n" + "=" * 70)
    print("DEMO 4: Layer-by-Layer Details")
    print("=" * 70)
    
    file_path = "data/sales_customers.csv"
    
    result = process_file(file_path, sample_size=100, save_sample=True)
    
    if result.success:
        print("\n" + "-" * 70)
        print("LAYER 1 — CONNECTOR OUTPUT")
        print("-" * 70)
        print(json.dumps(result.layer1_connector, indent=2))
        
        print("\n" + "-" * 70)
        print("LAYER 2 — VALIDATOR OUTPUT")
        print("-" * 70)
        print(json.dumps(result.layer2_validator, indent=2))
        
        print("\n" + "-" * 70)
        print("LAYER 3 — SAMPLER OUTPUT")
        print("-" * 70)
        print(json.dumps(result.layer3_sampler, indent=2, default=str))
    else:
        print(f"\n✗ Pipeline failed: {result.error}")


def demo_error_handling():
    """Demo: Error handling for missing/corrupt files"""
    print("\n" + "=" * 70)
    print("DEMO 5: Error Handling")
    print("=" * 70)
    
    test_cases = [
        ("nonexistent.csv", "File doesn't exist"),
        ("data/", "Directory instead of file"),
        # Add more edge cases as needed
    ]
    
    for file_path, description in test_cases:
        print(f"\nTest: {description}")
        print(f"Path: {file_path}")
        
        result = process_file(file_path, sample_size=100, save_sample=False)
        
        if result.success:
            print("✓ Unexpected success")
        else:
            print(f"✗ Expected error: {result.error}")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("FILE PROFILER DEMO")
    print("=" * 70)
    print("\nThis demo shows the 3-layer architecture:")
    print("  Layer 1: Connector  — Connect to file, validate access")
    print("  Layer 2: Validator  — Verify format, encoding, compression")
    print("  Layer 3: Sampler    — Adaptive sampling based on file size")
    print("=" * 70)
    
    # Run demos
    try:
        demo_connector_only()
        demo_full_pipeline_single_file()
        # demo_full_pipeline_directory()  # Uncomment to process all files
        # demo_layer_details()  # Uncomment for detailed output
        # demo_error_handling()  # Uncomment for error handling demo
    
    except Exception as e:
        log.error("Demo failed: %s", e, exc_info=True)
    
    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print("\nCheck the 'output/' directory for sample files.")
    print("=" * 70)
