"""
Relationship Charts — Interactive charts for relationship analysis

Generates:
- Confidence vs Semantic Similarity scatter plots
- Relationship type distribution
- Containment ratio histograms
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from visualization.engine import VisualizationEngine

log = logging.getLogger(__name__)


class RelationshipCharts:
    """Generate relationship confidence and distribution charts."""
    
    def __init__(self, engine: 'VisualizationEngine'):
        """
        Initialize chart generator.
        
        Args:
            engine: VisualizationEngine instance
        """
        self.engine = engine
        self.output_dir = engine.output_dir
    
    def generate_confidence_chart(self):
        """Generate interactive confidence vs similarity scatter plot."""
        relationships = self.engine.get_relationships()
        stats = self.engine.get_statistics()
        
        if not relationships:
            log.warning("No relationships to chart")
            return
        
        # Group by relationship type
        data_by_type = {}
        for rel in relationships:
            rel_type = rel.get("relationship_class", "UNKNOWN")
            if rel_type not in data_by_type:
                data_by_type[rel_type] = []
            
            data_by_type[rel_type].append({
                "confidence": rel.get("confidence_score", 0),
                "similarity": rel.get("semantic_similarity", 0),
                "containment": rel.get("containment_ratio", 0),
                "fk_table": rel.get("fk_table", ""),
                "fk_column": rel.get("fk_column", ""),
                "pk_table": rel.get("pk_table", ""),
                "pk_column": rel.get("pk_column", ""),
            })
        
        # Colors for different relationship types
        colors = {
            "TRUE_FK": "#4CAF50",
            "SEMANTICALLY_RELATED": "#2196F3",
            "SHARED_ENTITY_DOMAIN": "#FF9800",
            "POSSIBLE_REFERENCE": "#9C27B0",
            "FALSE_POSITIVE": "#F44336",
        }
        
        # Build HTML with Plotly.js
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Relationship Confidence Chart</title>
    <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
        }
        .container {
            max-width: 1600px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 {
            font-size: 2em;
            margin-bottom: 10px;
        }
        .content {
            padding: 30px;
        }
        .zoom-controls {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            justify-content: center;
        }
        .zoom-btn {
            padding: 10px 20px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            transition: background 0.3s;
        }
        .zoom-btn:hover {
            background: #764ba2;
        }
        #chart {
            width: 100%;
            height: 900px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: #f8f9fa;
            border-left: 4px solid #667eea;
            padding: 15px;
            border-radius: 8px;
        }
        .stat-card h3 {
            color: #667eea;
            font-size: 0.9em;
            margin-bottom: 5px;
        }
        .stat-card .value {
            font-size: 1.8em;
            font-weight: bold;
            color: #333;
        }
        .legend {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            margin-top: 20px;
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .legend-color {
            width: 20px;
            height: 20px;
            border-radius: 50%;
        }
        .legend-text {
            font-weight: 500;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Relationship Confidence Analysis</h1>
            <p>Confidence Score vs Semantic Similarity</p>
        </div>
        
        <div class="content">
            <div class="stats">
"""
        
        # Add statistics
        html += f"""
                <div class="stat-card">
                    <h3>Total Relationships</h3>
                    <div class="value">{stats['total_relationships']:,}</div>
                </div>
                <div class="stat-card">
                    <h3>Avg Confidence</h3>
                    <div class="value">{stats['confidence']['avg']:.2f}</div>
                </div>
                <div class="stat-card">
                    <h3>Avg Similarity</h3>
                    <div class="value">{stats['semantic_similarity']['avg']:.2f}</div>
                </div>
                <div class="stat-card">
                    <h3>Avg Containment</h3>
                    <div class="value">{stats['containment_ratio']['avg']:.2f}</div>
                </div>
"""
        
        html += """
            </div>
            
            <div class="zoom-controls">
                <button class="zoom-btn" onclick="resetZoom()">🔄 Reset Zoom</button>
                <button class="zoom-btn" onclick="zoomIn()">🔍 Zoom In</button>
                <button class="zoom-btn" onclick="zoomOut()">🔎 Zoom Out</button>
            </div>
            
            <div id="chart"></div>
            
            <div class="legend">
"""
        
        # Add legend
        for rel_type, color in colors.items():
            count = stats['type_counts'].get(rel_type, 0)
            html += f"""
                <div class="legend-item">
                    <div class="legend-color" style="background: {color};"></div>
                    <span class="legend-text">{rel_type.replace('_', ' ')} ({count:,})</span>
                </div>
"""
        
        html += """
            </div>
        </div>
    </div>
    
    <script>
        const data = [
"""
        
        # Add data for each relationship type
        for rel_type, items in data_by_type.items():
            color = colors.get(rel_type, "#999")
            
            x_values = [item['similarity'] for item in items]
            y_values = [item['confidence'] for item in items]
            hover_texts = [
                f"<b>{item['fk_table']}.{item['fk_column']}</b><br>" +
                f"→ {item['pk_table']}.{item['pk_column']}<br>" +
                f"Confidence: {item['confidence']:.3f}<br>" +
                f"Similarity: {item['similarity']:.3f}<br>" +
                f"Containment: {item['containment']:.3f}"
                for item in items
            ]
            
            html += f"""
            {{
                x: {x_values},
                y: {y_values},
                mode: 'markers',
                type: 'scatter',
                name: '{rel_type.replace("_", " ")}',
                marker: {{
                    color: '{color}',
                    size: 8,
                    opacity: 0.7,
                    line: {{
                        color: 'white',
                        width: 1
                    }}
                }},
                text: {hover_texts},
                hovertemplate: '%{{text}}<extra></extra>'
            }},
"""
        
        html += """
        ];
        
        const layout = {
            title: {
                text: 'Relationship Confidence vs Semantic Similarity',
                font: { size: 20 }
            },
            xaxis: {
                title: 'Semantic Similarity',
                range: [0, 1],
                gridcolor: '#e0e0e0'
            },
            yaxis: {
                title: 'Confidence Score',
                range: [0, 1],
                gridcolor: '#e0e0e0'
            },
            hovermode: 'closest',
            plot_bgcolor: '#fafafa',
            paper_bgcolor: 'white',
            showlegend: true,
            legend: {
                x: 1.02,
                y: 1,
                xanchor: 'left',
                yanchor: 'top'
            }
        };
        
        const config = {
            responsive: true,
            displayModeBar: true,
            modeBarButtonsToRemove: ['lasso2d', 'select2d'],
            scrollZoom: true,
            toImageButtonOptions: {
                format: 'png',
                filename: 'relationship_confidence_chart',
                height: 1200,
                width: 1600,
                scale: 2
            }
        };
        
        Plotly.newPlot('chart', data, layout, config);
        
        // Zoom control functions
        function resetZoom() {
            Plotly.relayout('chart', {
                'xaxis.range': [0, 1],
                'yaxis.range': [0, 1]
            });
        }
        
        function zoomIn() {
            Plotly.relayout('chart', {
                'xaxis.range': [0.3, 0.7],
                'yaxis.range': [0.3, 0.7]
            });
        }
        
        function zoomOut() {
            Plotly.relayout('chart', {
                'xaxis.range': [-0.1, 1.1],
                'yaxis.range': [-0.1, 1.1]
            });
        }
    </script>
</body>
</html>
"""
        
        output_path = self.output_dir / "confidence_chart.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"  ✓ Confidence chart saved to: {output_path}")
