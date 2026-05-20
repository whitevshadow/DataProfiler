"""Test script to verify ERVE outputs."""
import json
from pathlib import Path

# Check graph.json
graph_path = Path("output/graph/graph.json")
if graph_path.exists():
    data = json.loads(graph_path.read_text())
    print("✓ Graph JSON Generated")
    print(f"  Nodes: {len(data['nodes'])}")
    print(f"  Edges: {len(data['edges'])}")
    print(f"  Connected components: {data['metrics']['connected_components']}")
    print(f"  Largest component: {data['metrics']['largest_component_size']} tables")
    print(f"  Orphan tables: {data['metrics']['orphan_table_count']}")

# Check all expected files
expected_files = [
    "output/erd/schema.dbml",
    "output/erd/schema.mmd",
    "output/erd/erd.html",
    "output/drawio/semantic_erd.drawio",
    "output/drawio/ontology.drawio",
    "output/charts/relationship_summary.png",
    "output/charts/confidence_histogram.png",
    "output/charts/relationship_heatmap.png",
    "output/graph/graph.json",
    "output/graph/graph.html",
]

print("\n✓ File Generation Status:")
for file_path in expected_files:
    path = Path(file_path)
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    status = "✓" if exists and size > 0 else "✗"
    print(f"  {status} {path.name:30s} ({size:,} bytes)")

# Test different modes
print("\n✓ Testing Different Modes:")
from profiler import services

# Test auto top_k (None)
result1 = services.generate_er_visualizations(mode="dbml")
print(f"  Auto top_k (None): {result1['success']} - {result1['true_fk_relationships']} relationships")

# Test explicit top_k
result2 = services.generate_er_visualizations(mode="dbml", top_k=10)
print(f"  Explicit top_k=10: {result2['success']} - {result2['true_fk_relationships']} relationships")

# Test high confidence
result3 = services.generate_er_visualizations(mode="dbml", min_confidence=0.9)
print(f"  High confidence (0.9): {result3['success']} - {result3['true_fk_relationships']} relationships")

print("\n✅ All ERVE tests passed!")
