# ERVE Quick Reference

## One-Line Usage

```python
# User says: "Generate DB diagram"
# Agent calls:
generate_er_visualizations()  # Done! ✨
```

## Auto-Scaling Rules

| Tables | Relationships | Auto top_k |
|--------|---------------|------------|
| < 50 | Any | 50 |
| 50-200 | Any | 100 |
| > 200 | < 10k | 200 |
| Any | > 10k | 500 |

## Generation Modes

| Mode | Output |
|------|--------|
| `"full"` | Everything (default) |
| `"dbml"` | dbdiagram.io schema |
| `"drawio"` | Diagrams.net XML |
| `"mermaid"` | Mermaid ERD |
| `"html"` | Interactive HTML |
| `"charts"` | PNG relationship charts |
| `"graph"` | Graph JSON + HTML |

## Common Patterns

### Default (Everything)
```python
generate_er_visualizations()
```

### High Confidence Only
```python
generate_er_visualizations(min_confidence=0.8)
```

### Top 50 Relationships
```python
generate_er_visualizations(top_k=50)
```

### DBML Only
```python
generate_er_visualizations(mode="dbml")
```

### Custom Everything
```python
generate_er_visualizations(
    relationships_path="path/to/relationships.json",
    output_base="custom/output",
    mode="full",
    min_confidence=0.7,
    top_k=100
)
```

## Output Files

```
output/
  erd/
    schema.dbml        ← Import to dbdiagram.io
    schema.mmd         ← Paste into Mermaid Live
    erd.html           ← Open in browser
  drawio/
    semantic_erd.drawio   ← Open in diagrams.net
    ontology.drawio       ← Full ontology
  charts/
    relationship_summary.png
    confidence_histogram.png
    relationship_heatmap.png
  graph/
    graph.json         ← Graph structure
    graph.html         ← Interactive viz
```

## CLI

```bash
# Menu
python -m profiler.erve --menu

# Full export
python -m profiler.erve --full

# DBML only, top 50
python -m profiler.erve --dbml --top-k 50

# High confidence
python -m profiler.erve --full --min-confidence 0.8
```

## Troubleshooting

### No output generated
- Check that `output/relationships/relationships.json` exists
- Verify relationships have `confidence_score >= min_confidence`
- Lower `min_confidence` to 0.0 to see all relationships

### Too many relationships
- Increase `min_confidence` (e.g., 0.7, 0.8)
- Set explicit `top_k` (e.g., 50, 100)
- Use mode-specific generation instead of "full"

### Validation error on top_k
- **Should not happen anymore!** System auto-computes.
- If you see this, file a bug - the fix handles null/None automatically.

## What Changed

### Before ❌
```python
# Required explicit top_k, failed on null
generate_er_visualizations(
    relationships_path="...",
    top_k=null,  # ERROR!
    output_base="output",
    min_confidence=0.5,
    mode="full"
)
```

### After ✅
```python
# All optional, auto-computed
generate_er_visualizations()  # Works!
```

## Key Features

✅ **Auto top_k** - Computed from dataset size  
✅ **Null-safe** - Never fails on missing parameters  
✅ **Multi-format** - 6+ output types  
✅ **Confidence filtering** - Intelligent pruning  
✅ **Smart sorting** - Class priority + confidence  
✅ **Module splitting** - Large schema support  
✅ **Deduplication** - Best relationship per edge  
✅ **Profile integration** - Uses PK/FK candidates  
✅ **LCIL integration** - Semantic domain enrichment  

## Constants

```python
DEFAULT_TOP_K = 100
AUTO_TOP_K_SMALL = 50    # < 50 tables
AUTO_TOP_K_MEDIUM = 100  # 50-200 tables
AUTO_TOP_K_LARGE = 200   # > 200 tables
AUTO_TOP_K_HUGE = 500    # > 10k relationships
```
