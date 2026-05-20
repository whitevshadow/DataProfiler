"""
Demo: Profiling Agent Usage

Shows how to use the Profiling Agent in various modes.
"""

from pathlib import Path
from profiling_agent import ProfilingAgent, profile_single_file, profile_directory
import json

print("=" * 70)
print("PROFILING AGENT DEMO")
print("=" * 70)

# Example 1: Profile a single file
print("\n📝 Example 1: Single File Profiling")
print("-" * 70)

result = profile_single_file(Path("data/warehouse_colors.csv"))

if result["success"]:
    print("\n✓ Success!")
    print(f"  Canonical JSON: {result['canonical_json_path']}")
    
    # Load and inspect the artifact
    with open(result['canonical_json_path'], 'r', encoding='utf-8') as f:
        canonical = json.load(f)
    
    print(f"  Rows: {canonical['metadata']['row_count_estimate']}")
    print(f"  Columns: {canonical['metadata']['column_count']}")
    print(f"  Column names: {', '.join(c['normalized_name'] for c in canonical['columns'])}")
else:
    print(f"\n✗ Failed: {result['error']}")


# Example 2: Profile using agent instance
print("\n\n📝 Example 2: Using Agent Instance")
print("-" * 70)

agent = ProfilingAgent(output_dir=Path("output/canonical"))
result = agent.profile(Path("data/sales_buyinggroups.csv"))

if result["success"]:
    print("\n✓ Success!")
    
    # Inspect layer results
    print("\nLayer Results:")
    print(f"  Connector: {result['layers']['layer1_connector']['file_format']}, "
          f"{result['layers']['layer1_connector']['size_mb']} MB")
    print(f"  Validator: {result['layers']['layer2_validator']['encoding']}")
    print(f"  Classifier: {result['layers']['layer25_classifier']['size_tier']}, "
          f"complexity {result['layers']['layer25_classifier']['complexity_score']}/10")
    print(f"  Planner: {result['layers']['layer3_planner']['engine']}, "
          f"strategy {result['layers']['layer3_planner']['sampling_strategy']}")


# Example 3: Batch processing (commented out to avoid re-processing)
print("\n\n📝 Example 3: Batch Processing")
print("-" * 70)
print("# Uncomment to run:")
print("# result = profile_directory(Path('data/'))")
print("# print(f\"Processed {result['successful']}/{result['total']} files\")")


# Example 4: Inspect generated artifacts
print("\n\n📝 Example 4: Inspect Generated Artifacts")
print("-" * 70)

import os
artifacts = list(Path("output/canonical").glob("*.canonical.json"))
print(f"\nFound {len(artifacts)} Canonical JSON artifacts:")

# Show top 5 by size
artifacts_with_size = [(f, f.stat().st_size) for f in artifacts]
artifacts_with_size.sort(key=lambda x: x[1], reverse=True)

for i, (artifact, size) in enumerate(artifacts_with_size[:5], 1):
    size_kb = size / 1024
    print(f"  {i}. {artifact.name}: {size_kb:.2f} KB")

print("\n" + "=" * 70)
print("Demo complete! Run:")
print("  python profiling_agent.py --help")
print("=" * 70)
