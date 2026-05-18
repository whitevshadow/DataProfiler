# Visualization Engine

**Interactive Chart & ERD Generation System for Semantic Profiling Pipeline**

## Overview

The Visualization Engine extends the semantic profiling pipeline with comprehensive visualization capabilities, transforming `relationships.json` into interactive charts, ERD diagrams, knowledge graphs, and quality dashboards.

## Features

### 🎨 Visualization Types

1. **📊 Relationship Confidence Chart**
   - Interactive scatter plot: confidence vs semantic similarity
   - Color-coded by relationship type
   - Hover tooltips with detailed information
   - Powered by Plotly.js

2. **🗺️ ERD Diagram**
   - Entity Relationship Diagram showing TRUE_FK connections
   - Mermaid.js-based rendering
   - Cardinality indicators
   - Clean, professional layout

3. **🕸️ Knowledge Graph**
   - Interactive force-directed network visualization
   - All relationship types displayed
   - Drag-and-drop nodes
   - Adjustable physics parameters
   - Zoom and pan support
   - Powered by D3.js

4. **📋 Quality Dashboard**
   - Comprehensive quality metrics
   - Confidence distribution histogram
   - Semantic similarity distribution
   - Containment ratio analysis
   - Relationship type breakdown
   - Quality score calculation
   - Automated recommendations

5. **📑 Full Report Dashboard**
   - Master dashboard linking all visualizations
   - Key metrics summary
   - Quick navigation to all reports
   - Professional styling

## Architecture

```
visualization/
├── __init__.py              # Package exports
├── engine.py                # Main orchestrator
├── charts.py                # Confidence charts
├── erd.py                   # ERD diagrams
├── knowledge_graph.py       # Network graphs
└── quality_dashboard.py     # Quality metrics
```

## Pipeline Integration

### Current Pipeline Flow

```
1. Canonical Generation      → canonical.json
2. Profile Generation         → profile.json
3. LLM Descriptions          → descriptions.json
4. Relationship Detection    → relationships.json
5. Visualization Engine      → HTML dashboards (NEW!)
```

## Usage

### Interactive CLI

```bash
python demo_visualization.py
```

The CLI provides an interactive menu:

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                          SELECT VISUALIZATION                                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  1. 📊 Relationship Confidence Chart                                         ║
║  2. 🗺️  ERD Diagram                                                          ║
║  3. 🕸️  Knowledge Graph                                                      ║
║  4. 📋 Quality Dashboard                                                     ║
║  5. 📑 Full Report Dashboard                                                 ║
║  6. 🚀 Generate All Visualizations                                           ║
║  7. ❌ Exit                                                                   ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### Programmatic API

```python
from visualization.engine import VisualizationEngine

# Initialize engine
engine = VisualizationEngine("output/relationships/relationships.json")

# Load relationships
if engine.load_relationships():
    
    # Generate specific visualization
    from visualization.charts import RelationshipCharts
    charts = RelationshipCharts(engine)
    charts.generate_confidence_chart()
    
    # Or generate all at once
    engine.generate_all()
```

### Generate Individual Visualizations

```python
from visualization.engine import VisualizationEngine
from visualization.erd import ERDGenerator
from visualization.knowledge_graph import KnowledgeGraphGenerator

engine = VisualizationEngine()
engine.load_relationships()

# Generate ERD only
erd = ERDGenerator(engine)
erd.generate_erd()

# Generate knowledge graph only
kg = KnowledgeGraphGenerator(engine)
kg.generate_graph()
```

## Output

All visualizations are saved to `output/visualizations/`:

```
output/visualizations/
├── confidence_chart.html      # Confidence scatter plot
├── erd_diagram.html           # ERD diagram
├── knowledge_graph.html       # Network graph
├── quality_dashboard.html     # Quality metrics
└── full_report.html           # Master dashboard
```

## Input Format

The engine reads `relationships.json` with this structure:

```json
{
  "metadata": {
    "total_candidates": 6060,
    "total_relationships": 6060,
    "true_fk_count": 177,
    "clusters_found": 1,
    "generation_timestamp": "2026-05-15 17:22:21"
  },
  "relationships": [
    {
      "fk_table": "sales_orders",
      "fk_column": "customerid",
      "pk_table": "sales_customers",
      "pk_column": "customerid",
      "relationship_class": "TRUE_FK",
      "confidence_score": 0.95,
      "semantic_similarity": 0.89,
      "containment_ratio": 1.0,
      "reasoning": [
        "Perfect containment (1.00)",
        "Strong semantic alignment (0.89)",
        "Validated as TRUE foreign key relationship"
      ]
    }
  ]
}
```

## Relationship Types

The visualization engine supports all relationship classifications:

- **TRUE_FK**: Validated foreign key relationships
- **SEMANTICALLY_RELATED**: Similar meaning, no FK
- **SHARED_ENTITY_DOMAIN**: Same business domain
- **POSSIBLE_REFERENCE**: Weak evidence
- **FALSE_POSITIVE**: Rejected

## Quality Metrics

The quality dashboard calculates:

- **Overall Quality Score**: Weighted score (0-100) based on:
  - FK detection rate (30%)
  - Average confidence (40%)
  - Average containment (30%)

- **Distribution Analysis**:
  - Confidence score distribution
  - Semantic similarity distribution
  - Containment ratio distribution

- **Automated Recommendations**:
  - Low FK detection warnings
  - Confidence level alerts
  - Data quality suggestions

## Technology Stack

- **Plotly.js**: Interactive scatter plots and charts
- **D3.js v7**: Force-directed network graphs
- **Mermaid.js v10**: ERD diagrams
- **Pure HTML/CSS/JS**: No backend required, fully self-contained

## Browser Compatibility

All visualizations work in modern browsers:
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Performance

- **Knowledge Graph**: Limits to 500 relationships to prevent clutter
  - Prioritizes TRUE_FK and high-confidence relationships
  - Adjustable physics for optimal layout

- **Charts**: Handles 10,000+ data points smoothly

- **File Size**: Each HTML file is 20-100KB (fully self-contained)

## Customization

### Colors

Relationship type colors are defined in each module:

```python
colors = {
    "TRUE_FK": "#4CAF50",           # Green
    "SEMANTICALLY_RELATED": "#2196F3",  # Blue
    "SHARED_ENTITY_DOMAIN": "#FF9800",  # Orange
    "POSSIBLE_REFERENCE": "#9C27B0",    # Purple
    "FALSE_POSITIVE": "#F44336",        # Red
}
```

### Thresholds

Adjust in `quality_dashboard.py`:

```python
def _calculate_quality_score(self, stats, metadata):
    score = (
        fk_ratio * 30 +      # FK detection weight
        avg_confidence * 40 + # Confidence weight
        avg_containment * 30  # Containment weight
    ) * 100
    return int(score)
```

## Examples

### Full Pipeline Run

```bash
# 1. Run relationship detection (if not done)
python demo_relationship_detection.py

# 2. Launch visualization CLI
python demo_visualization.py

# 3. Select option 6 to generate all visualizations

# 4. View full_report.html in browser
```

### Quick API Usage

```python
from visualization.engine import VisualizationEngine

engine = VisualizationEngine()
if engine.load_relationships():
    engine.generate_all()
    print(f"✓ Visualizations saved to: {engine.output_dir}")
```

## Troubleshooting

### "Failed to load relationships.json"

Ensure the relationship detection pipeline has been run:

```bash
python demo_relationship_detection.py
```

### Empty Visualizations

Check that `relationships.json` contains data:

```bash
python -c "import json; print(json.load(open('output/relationships/relationships.json'))['metadata'])"
```

### Browser Not Opening

Manually open the HTML files:

```bash
# Windows
start output/visualizations/full_report.html

# macOS
open output/visualizations/full_report.html

# Linux
xdg-open output/visualizations/full_report.html
```

## Future Enhancements

- [ ] Export to PNG/PDF
- [ ] Filtering by confidence threshold
- [ ] Timeline view for relationship evolution
- [ ] Comparison dashboards for multiple runs
- [ ] Real-time updates via websockets
- [ ] Custom color schemes
- [ ] CSV export of metrics

## License

Part of the Semantic Profiling Pipeline project.

---

**Questions?** See `docs/VISUALIZATION_ENGINE.md` for detailed technical documentation.
