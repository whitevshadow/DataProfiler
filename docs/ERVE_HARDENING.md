# ER Visualization Engine (ERVE) - Hardening & Auto-Scaling

## Overview

The ER Visualization Engine has been redesigned to be **fully automatic** and **fault-tolerant**. Users no longer need to manually specify `top_k` or worry about validation errors.

## Problem Fixed

### Before
```python
# User says: "Generate DB diagram"
# Agent calls:
generate_er_visualizations(
    relationships_path="output/relationships/relationships.json",
    top_k=null,  # ❌ VALIDATION ERROR: expected int, received null
    output_base="output",
    min_confidence=0.5,
    mode="full"
)
```

### After
```python
# User says: "Generate DB diagram"
# Agent calls:
generate_er_visualizations()  # ✅ All parameters optional with smart defaults

# System automatically:
# - Sets top_k based on dataset size
# - Applies confidence filtering
# - Generates all formats
# - Never throws validation errors
```

## Auto-Scaling Top-K Algorithm

The system automatically computes `top_k` based on dataset characteristics:

| Dataset Size | Auto top_k | Reasoning |
|--------------|------------|-----------|
| < 50 tables | 50 | Small schema - show everything |
| 50-200 tables | 100 | Medium schema - balance detail vs clarity |
| > 200 tables | 200 | Large schema - focus on key relationships |
| > 10,000 relationships | 500 | Huge dataset - render cap for performance |

### Implementation

```python
def _auto_compute_top_k(self, relationship_count: int) -> int:
    """Auto-compute top_k based on dataset characteristics."""
    table_count = len(self.tables)
    
    # Priority 1: Huge relationship count
    if relationship_count > 10000:
        return 500
    
    # Priority 2: Scale based on table count
    if table_count < 50:
        return 50
    elif table_count <= 200:
        return 100
    else:
        return 200
```

## Features

### 1. Null-Safe Parameter Handling

All parameters have sensible defaults:
- `relationships_path`: `"output/relationships/relationships.json"`
- `output_base`: `"output"`
- `mode`: `"full"` (generates everything)
- `min_confidence`: `0.5` (50% confidence threshold)
- `top_k`: `None` (auto-computed)

### 2. Multi-Format Generation

Single command generates all ER intelligence representations:

#### DBML (dbdiagram.io)
- TRUE_FK relationships only
- Clean table definitions
- Ref syntax for foreign keys
- Module splitting for large schemas

**Output:** `output/erd/schema.dbml`

#### Draw.io XML
- Semantic ERD (TRUE_FK + SEMANTICALLY_RELATED + SHARED_ENTITY_DOMAIN)
- Ontology diagram (all relationship types)
- Professional styling
- Relationship labels with confidence

**Output:** 
- `output/drawio/semantic_erd.drawio`
- `output/drawio/ontology.drawio`

#### Mermaid ERD
- TRUE_FK relationships only
- Readable cardinality notation
- Capped for rendering performance

**Output:** `output/erd/schema.mmd`

#### HTML Preview
- Standalone interactive ERD
- Mermaid.js rendering
- Zoom and pan controls
- No external dependencies

**Output:** `output/erd/erd.html`

#### PNG Charts
- Relationship summary bar chart
- Confidence score histogram
- Relationship heatmap (top 25 tables)

**Output:**
- `output/charts/relationship_summary.png`
- `output/charts/confidence_histogram.png`
- `output/charts/relationship_heatmap.png`

#### Graph Intelligence
- Full graph JSON with nodes/edges
- Interactive graph HTML with D3.js
- Metrics (degree distribution, clustering, etc.)

**Output:**
- `output/graph/graph.json`
- `output/graph/graph.html`

### 3. Generation Modes

Control what gets generated:

```python
# Generate everything (default)
generate_er_visualizations(mode="full")

# Generate only DBML
generate_er_visualizations(mode="dbml")

# Generate only draw.io
generate_er_visualizations(mode="drawio")

# Generate only Mermaid
generate_er_visualizations(mode="mermaid")

# Generate only HTML preview
generate_er_visualizations(mode="html")

# Generate only charts
generate_er_visualizations(mode="charts")

# Generate only graph JSON
generate_er_visualizations(mode="graph")
```

### 4. Confidence Filtering

Relationships are filtered by confidence score:

```python
# Default: 0.5 (50%)
generate_er_visualizations(min_confidence=0.5)

# High confidence only: 0.8 (80%)
generate_er_visualizations(min_confidence=0.8)

# Include everything: 0.0
generate_er_visualizations(min_confidence=0.0)
```

After confidence filtering, relationships are sorted by:
1. Relationship class priority (TRUE_FK > SEMANTICALLY_RELATED > SHARED_ENTITY_DOMAIN > POSSIBLE_REFERENCE)
2. Confidence score (descending)
3. Alphabetical order (fk_table, pk_table)

Then `top_k` is applied.

### 5. Error Handling

The system **never fails** because of:
- Missing `top_k` → Auto-computed
- Null values → Defaults applied
- Empty relationships → Generates empty diagrams with warnings
- Missing confidence → Assumed 0.0

All errors are logged but don't stop execution.

## User Experience

### Simple Case

```
User: "Generate DB diagram"
Agent: [calls generate_er_visualizations()]
System: 
  ✓ Loaded 2,341 relationships
  ✓ Filtered to 1,847 (min_confidence=0.5)
  ✓ Auto-computed top_k=100 (87 tables)
  ✓ Generated DBML schema
  ✓ Generated draw.io files
  ✓ Generated Mermaid ERD
  ✓ Generated HTML preview
  ✓ Generated charts
  ✓ Generated graph JSON
```

### Advanced Case

```python
# User wants specific control
generate_er_visualizations(
    mode="dbml",              # Only DBML
    top_k=50,                 # Limit to top 50
    min_confidence=0.7,       # High confidence only
)
```

## Agent Integration

The agent system prompt has been updated with:

```
- generate_er_visualizations()
  → FULLY AUTOMATIC ER diagram generation
  → All params optional with smart defaults
  → top_k auto-computed: < 50 tables → 50, 50-200 → 100, > 200 → 200
  → Modes: "full" (all formats), "dbml", "drawio", "mermaid", "html", "charts", "graph"
  → User can simply say "Generate DB diagram" without parameters
```

## CLI Usage

```bash
# Interactive menu (auto-computed top_k)
python -m profiler.erve --menu

# Generate everything
python -m profiler.erve --full

# Generate only DBML with custom top_k
python -m profiler.erve --dbml --top-k 50

# High confidence threshold
python -m profiler.erve --full --min-confidence 0.8
```

## Output Structure

```
output/
├── erd/
│   ├── schema.dbml           # dbdiagram.io format
│   ├── schema.mmd            # Mermaid ERD
│   └── erd.html              # Standalone HTML preview
├── drawio/
│   ├── semantic_erd.drawio   # Semantic relationships
│   └── ontology.drawio       # Full ontology
├── charts/
│   ├── relationship_summary.png
│   ├── confidence_histogram.png
│   └── relationship_heatmap.png
├── graph/
│   ├── graph.json            # Graph structure
│   └── graph.html            # Interactive visualization
└── scripts/
    ├── generate_dbml.py
    ├── generate_drawio.py
    ├── generate_mermaid.py
    ├── generate_html.py
    ├── generate_charts.py
    └── generate_graph.py
```

## Technical Details

### Constants

```python
DEFAULT_TOP_K = 100              # Fallback default
AUTO_TOP_K_SMALL = 50           # < 50 tables
AUTO_TOP_K_MEDIUM = 100         # 50-200 tables
AUTO_TOP_K_LARGE = 200          # > 200 tables
AUTO_TOP_K_HUGE = 500           # > 10000 relationships
```

### Relationship Classes

```python
TRUE_FK                 # Actual foreign keys
POSSIBLE_REFERENCE      # Likely references (lower confidence)
SEMANTICALLY_RELATED    # Columns with semantic similarity
SHARED_ENTITY_DOMAIN    # Shared lookup tables
```

### Rendering Limits

```python
max_render_edges = 500          # General render cap
max_mermaid_edges = 450         # Mermaid specific cap
max_drawio_edges = 700          # Draw.io specific cap
max_drawio_nodes = 350          # Draw.io node cap
max_tables_per_module = 120     # Module split threshold
split_modules_over_tables = 240 # Module split trigger
heatmap_top_n = 25             # Heatmap size
```

## Backward Compatibility

All existing code continues to work:

```python
# Old explicit style still works
generate_er_visualizations(
    relationships_path="output/relationships/relationships.json",
    output_base="output",
    mode="full",
    min_confidence=0.5,
    top_k=100
)

# New automatic style
generate_er_visualizations()  # Same result with auto top_k
```

## Testing

No test changes required - all tests pass with auto-computed `top_k`.

## Summary

The ER Visualization Engine is now:

✅ **Fully automatic** - No manual parameter tuning required
✅ **Fault-tolerant** - Never fails on null/missing values
✅ **Smart** - Adapts to dataset size automatically
✅ **Comprehensive** - Generates 6+ output formats
✅ **User-friendly** - "Generate DB diagram" just works
✅ **Backward compatible** - Existing code unchanged

Users can now generate professional ER diagrams with zero configuration.
