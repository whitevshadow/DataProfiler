"""
Real-World Example: FK Detection on WideWorldImporters Dataset

This script demonstrates the FK detection layer on real profiled data.
"""

import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from relationships import detect_relationships
from relationships.relationship_serializer import save_relationship_report


def load_canonical_table(filepath):
    """Load a canonical table JSON file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def load_profile(filepath):
    """Load a profile JSON file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def extract_pk_candidates_from_profile(profile):
    """Extract PK candidates from a profile."""
    pk_candidates = []
    
    for col in profile.get("columns", []):
        if col.get("pk_candidate", False):
            pk_candidates.append({
                "column": col["column_name"],
                "confidence": col.get("pk_confidence", 0.0),
                "accepted": col.get("pk_candidate", False),
                "physical_type": col.get("physical_type", "UNKNOWN"),
                "distinct_count": col.get("distinct_count", 0),
            })
    
    return pk_candidates


def main():
    print("=" * 80)
    print("FK RELATIONSHIP DETECTION - REAL-WORLD EXAMPLE")
    print("=" * 80)
    print("\nDataset: WideWorldImporters (Sales, Purchasing, Warehouse, Application)\n")
    
    # Define tables to analyze
    tables_to_analyze = [
        "warehouse_colors",
        "Application_Cities",
        "Sales_Customers",
        "sales_orders",
    ]
    
    # Load table profiles and canonical tables
    table_profiles = {}
    pk_candidates = {}
    canonical_tables = {}
    
    for table in tables_to_analyze:
        # Load profile
        profile_path = f"output/profiles/{table}.profile.json"
        profile = load_profile(profile_path)
        
        if profile:
            table_profiles[table] = profile
            pk_candidates[table] = extract_pk_candidates_from_profile(profile)
            print(f"[OK] Loaded profile: {table}")
            print(f"     PK candidates: {[c['column'] for c in pk_candidates[table]]}")
        
        # Load canonical table
        canonical_path = f"output/canonical/{table}.canonical.json"
        canonical = load_canonical_table(canonical_path)
        
        if canonical:
            canonical_tables[table] = canonical
            print(f"[OK] Loaded canonical: {table}")
    
    if not table_profiles:
        print("\n[WARNING] No profiles found. Please run profiling first:")
        print("  python profiling_agent.py")
        return
    
    print(f"\n[INFO] Analyzing {len(table_profiles)} tables...")
    
    # Run FK detection
    print("\n" + "=" * 80)
    print("RUNNING FK DETECTION")
    print("=" * 80 + "\n")
    
    report = detect_relationships(
        table_profiles=table_profiles,
        pk_candidates=pk_candidates,
        canonical_tables=canonical_tables,
        acceptance_threshold=0.75,
    )
    
    # Display results
    print("\n" + "=" * 80)
    print("RELATIONSHIP DETECTION REPORT")
    print("=" * 80)
    
    print(f"\nSummary:")
    print(f"  Tables Analyzed:         {report.total_tables_analyzed}")
    print(f"  Candidate Pairs:         {report.total_candidate_pairs_evaluated}")
    print(f"  Relationships Detected:  {report.total_relationships_detected}")
    print(f"  Accepted:                {report.total_relationships_accepted}")
    print(f"  Rejected:                {report.total_relationships_rejected}")
    print(f"  Execution Time:          {report.execution_time_seconds:.3f}s")
    
    print(f"\n[ACCEPTED RELATIONSHIPS]")
    print("-" * 80)
    
    if report.total_relationships_accepted == 0:
        print("No relationships accepted.")
    else:
        for rel in report.relationships:
            if rel.accepted:
                print(f"\n{rel.from_column.table}.{rel.from_column.column}")
                print(f"  → {rel.to_column.table}.{rel.to_column.column}")
                print(f"  Confidence:    {rel.confidence:.4f}")
                print(f"  Containment:   {rel.evidence.containment_ratio:.4f}")
                print(f"  Type Match:    {rel.evidence.type_match}")
                print(f"  Orphans:       {rel.validation.orphan_count}")
                print(f"  Integrity:     {rel.validation.referential_integrity_score:.4f}")
    
    print(f"\n[REJECTED RELATIONSHIPS]")
    print("-" * 80)
    
    if report.total_relationships_rejected == 0:
        print("No relationships rejected.")
    else:
        for rel in report.relationships:
            if not rel.accepted:
                print(f"\n{rel.from_column.table}.{rel.from_column.column}")
                print(f"  → {rel.to_column.table}.{rel.to_column.column}")
                print(f"  Confidence:    {rel.confidence:.4f}")
                print(f"  Reasons:       {', '.join(rel.suppression_reasons)}")
    
    # Save report
    output_path = "output/relationship_report.json"
    save_relationship_report(report, output_path)
    print(f"\n[OK] Report saved to: {output_path}")
    
    # Export graph
    from relationships.graph_builder import build_relationship_graph, export_to_dot
    
    graph = build_relationship_graph(report.relationships)
    
    graph_json_path = "output/relationship_graph.json"
    with open(graph_json_path, 'w', encoding='utf-8') as f:
        json.dump(graph, f, indent=2)
    print(f"[OK] Graph exported to: {graph_json_path}")
    
    dot = export_to_dot(report.relationships)
    dot_path = "output/relationship_graph.dot"
    with open(dot_path, 'w', encoding='utf-8') as f:
        f.write(dot)
    print(f"[OK] DOT graph exported to: {dot_path}")
    
    print("\n" + "=" * 80)
    print("[COMPLETE] FK Relationship Detection")
    print("=" * 80)


if __name__ == "__main__":
    main()
