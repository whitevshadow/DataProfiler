"""
Demo: Canonical JSON Persistence Flow

Shows the complete flow from raw data → CanonicalTable → Canonical JSON.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from profiler.engines import registry


def demo_flow():
    """Demonstrate the complete Canonical JSON flow."""
    
    print("\n" + "=" * 70)
    print("CANONICAL JSON PERSISTENCE — COMPLETE FLOW DEMO")
    print("=" * 70)
    
    print("\n🚀 Design Philosophy:")
    print("   Format engines ONLY parse, NEVER profile")
    print("   Canonical JSON is the reusable intermediate artifact")
    print("   Lightweight: schema + metadata + samples (NOT full dataset)")
    
    # Step 1: Parse raw data
    print("\n" + "-" * 70)
    print("STEP 1: Parse Raw Data → CanonicalTable")
    print("-" * 70)
    
    file_path = Path("data/warehouse_stockgroups.csv")
    print(f"\nInput: {file_path}")
    
    table = registry.parse(
        file_path=file_path,
        file_format="csv",
        encoding="utf-8",
        sample_size=15  # Sample for efficiency
    )
    
    print(f"✓ Parsed with {table.source_type.upper()} engine")
    print(f"  Columns: {table.column_count}")
    print(f"  Rows: {table.row_count}")
    print(f"  Encoding: {table.encoding}")
    
    # Step 2: Compute lightweight statistics
    print("\n" + "-" * 70)
    print("STEP 2: Compute Lightweight Statistics")
    print("-" * 70)
    
    table.compute_lightweight_statistics()
    
    print(f"\n✓ Computed statistics:")
    for col in table.columns[:3]:  # Show first 3
        print(f"\n  {col.original_name} → {col.normalized_name}")
        print(f"    Nullable: {col.nullable}")
        print(f"    Null Count: {col.null_count}")
        print(f"    Distinct: {col.distinct_count}")
        if col.avg_length:
            print(f"    Avg Length: {col.avg_length:.2f}")
        print(f"    Samples: {col.sample_values[:3]}...")
    
    # Step 3: Generate Canonical JSON
    print("\n" + "-" * 70)
    print("STEP 3: Generate Canonical JSON")
    print("-" * 70)
    
    canonical = table.to_canonical_json()
    
    print(f"\n✓ Generated Canonical JSON:")
    print(f"  table_id: {canonical['table_id']}")
    print(f"  table_name: {canonical['table_name']}")
    print(f"  format: {canonical['source']['format']}")
    print(f"  columns: {len(canonical['columns'])}")
    
    # Step 4: Persist to disk
    print("\n" + "-" * 70)
    print("STEP 4: Persist to Disk")
    print("-" * 70)
    
    output_path = Path("output/canonical/demo_stockgroups.canonical.json")
    table.save_canonical_json(output_path)
    
    print(f"\n✓ Saved to: {output_path}")
    print(f"  File size: {output_path.stat().st_size:,} bytes")
    
    # Step 5: Verify reusability
    print("\n" + "-" * 70)
    print("STEP 5: Verify Reusability")
    print("-" * 70)
    
    # Load back from disk
    with open(output_path, 'r') as f:
        loaded = json.load(f)
    
    print(f"\n✓ Loaded from disk")
    print(f"  Columns: {len(loaded['columns'])}")
    print(f"  Row estimate: {loaded['metadata']['row_count_estimate']}")
    
    # Show what downstream layers can use
    print("\n✓ Downstream layers can now:")
    print("  → Skip reparsing (use cached schema)")
    print("  → Access normalized column names")
    print("  → Use sample values for type inference")
    print("  → Build lineage graphs")
    print("  → Run semantic analysis")
    print("  → Debug with original names")
    
    # Architecture summary
    print("\n" + "=" * 70)
    print("ARCHITECTURE SUMMARY")
    print("=" * 70)
    
    print("""
┌─────────────────┐
│   Raw Data      │  CSV, JSON, Parquet, Excel, etc.
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Format Engine   │  Parse → CanonicalTable
│  (Layer 5)      │  Design: ONLY parse, NEVER profile
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ CanonicalTable  │  In-memory IR
│   (Python)      │  Schema + rows + metadata
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Canonical JSON  │  Persistent artifact ⭐
│   (Cached)      │  Lightweight, reusable
└────────┬────────┘
         │
         ├──────→ Layer 6: Profiler
         ├──────→ Layer 7: PK/FK Detection
         ├──────→ Layer 8: Semantic Layer
         └──────→ Layer 9: Knowledge Graph
    """)
    
    print("\n" + "=" * 70)
    print("KEY BENEFITS 🚀")
    print("=" * 70)
    
    benefits = [
        ("Caching", "Avoid reparsing files repeatedly"),
        ("Lineage", "Track original_name → normalized_name"),
        ("Debugging", "Sample values show actual data"),
        ("Semantic", "Type inference uses samples"),
        ("Scalability", "Lightweight, not full dataset"),
        ("Integration", "Input for all downstream layers"),
    ]
    
    for benefit, desc in benefits:
        print(f"  ✓ {benefit:<15} {desc}")
    
    print("\n" + "=" * 70)
    print("WHAT'S STORED VS NOT STORED")
    print("=" * 70)
    
    stored = [
        ("✅ Schema", "Column names, positions, types"),
        ("✅ Normalized names", "customer_id, not 'Customer ID'"),
        ("✅ Sample values", "10 representative samples per column"),
        ("✅ Lightweight stats", "null_count, distinct_estimate, avg_length"),
        ("✅ Metadata", "source, format, row estimate, sampling strategy"),
        ("❌ Full dataset", "NOT stored (too heavy)"),
        ("❌ All rows", "NOT stored (samples only)"),
        ("❌ Heavy profiling", "Belongs in separate artifacts"),
    ]
    
    for item, desc in stored:
        print(f"  {item:<20} {desc}")
    
    print("\n" + "=" * 70)
    print("✓ Demo Complete!")
    print("=" * 70)
    print("\nCanonical JSON is the foundation for:")
    print("  → FileProfile.json (Layer 6)")
    print("  → RelationshipReport.json (PK/FK detection)")
    print("  → SemanticCatalog.json (embeddings/ontology)")
    print("  → QualityReport.json (anomaly detection)")


if __name__ == "__main__":
    demo_flow()
