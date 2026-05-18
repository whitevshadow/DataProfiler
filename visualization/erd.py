"""
ERD Generator — Entity Relationship Diagrams

Generates interactive ERD diagrams showing:
- Tables as entities
- TRUE_FK relationships as connections
- Column details
- Cardinality indicators
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Set

if TYPE_CHECKING:
    from visualization.engine import VisualizationEngine

log = logging.getLogger(__name__)


class ERDGenerator:
    """Generate Entity Relationship Diagrams from TRUE_FK relationships."""
    
    def __init__(self, engine: 'VisualizationEngine'):
        """
        Initialize ERD generator.
        
        Args:
            engine: VisualizationEngine instance
        """
        self.engine = engine
        self.output_dir = engine.output_dir
    
    def generate_erd(self):
        """Generate interactive ERD diagram using Mermaid.js."""
        # Get TRUE_FK relationships only
        true_fks = self.engine.get_relationships_by_type("TRUE_FK")
        
        if not true_fks:
            log.warning("No TRUE_FK relationships found for ERD")
            return
        
        # Collect all tables involved
        tables = set()
        for rel in true_fks:
            tables.add(rel['fk_table'])
            tables.add(rel['pk_table'])
        
        # Build Mermaid ERD
        mermaid_code = "erDiagram\n"
        
        # Add relationships
        for rel in true_fks:
            fk_table = rel['fk_table']
            pk_table = rel['pk_table']
            fk_column = rel['fk_column']
            pk_column = rel['pk_column']
            confidence = rel.get('confidence_score', 0)
            
            # Format table names (replace special chars)
            fk_table_clean = fk_table.replace('-', '_').replace('.', '_')
            pk_table_clean = pk_table.replace('-', '_').replace('.', '_')
            
            # Cardinality: FK is many-to-one typically
            mermaid_code += f'    {fk_table_clean} }}o--|| {pk_table_clean} : "{fk_column} → {pk_column}"\n'
        
        # Build HTML
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ERD Diagram</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1800px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 2em;
            margin-bottom: 10px;
        }}
        .content {{
            padding: 40px;
            overflow-x: auto;
        }}
        .stats {{
            display: flex;
            gap: 20px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }}
        .stat-card {{
            background: #f8f9fa;
            border-left: 4px solid #4CAF50;
            padding: 20px;
            border-radius: 8px;
            flex: 1;
            min-width: 200px;
        }}
        .stat-card h3 {{
            color: #4CAF50;
            font-size: 0.9em;
            margin-bottom: 5px;
        }}
        .stat-card .value {{
            font-size: 2em;
            font-weight: bold;
            color: #333;
        }}
        .zoom-controls {{
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            justify-content: center;
        }}
        .zoom-btn {{
            padding: 10px 20px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            transition: background 0.3s;
        }}
        .zoom-btn:hover {{
            background: #764ba2;
        }}
        #diagram {{
            display: flex;
            justify-content: center;
            padding: 40px;
            background: #fafafa;
            border-radius: 15px;
            min-height: 800px;
            overflow: auto;
        }}
        #diagram svg {{
            max-width: none !important;
            transform-origin: center;
            transition: transform 0.3s;
        }}
        #diagram.zoomed-in svg {{
            transform: scale(1.5);
        }}
        #diagram.zoomed-out svg {{
            transform: scale(0.7);
        }}
        .legend {{
            margin-top: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
        }}
        .legend h3 {{
            color: #667eea;
            margin-bottom: 15px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 10px;
        }}
        .legend-symbol {{
            font-family: monospace;
            font-weight: bold;
            font-size: 1.2em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🗺️ Entity Relationship Diagram</h1>
            <p>TRUE Foreign Key Relationships</p>
        </div>
        
        <div class="content">
            <div class="stats">
                <div class="stat-card">
                    <h3>Total Tables</h3>
                    <div class="value">{len(tables)}</div>
                </div>
                <div class="stat-card">
                    <h3>TRUE_FK Relationships</h3>
                    <div class="value">{len(true_fks)}</div>
                </div>
                <div class="stat-card">
                    <h3>Avg Confidence</h3>
                    <div class="value">{sum(r.get('confidence_score', 0) for r in true_fks) / len(true_fks):.2f}</div>
                </div>
            </div>
            
            <div class="zoom-controls">
                <button class="zoom-btn" onclick="resetZoom()">🔄 Reset Zoom</button>
                <button class="zoom-btn" onclick="zoomIn()">🔍 Zoom In</button>
                <button class="zoom-btn" onclick="zoomOut()">🔎 Zoom Out</button>
                <button class="zoom-btn" onclick="fitToScreen()">📐 Fit to Screen</button>
            </div>
            
            <div id="diagram">
                <pre class="mermaid">
{mermaid_code}
                </pre>
            </div>
            
            <div class="legend">
                <h3>Relationship Legend</h3>
                <div class="legend-item">
                    <span class="legend-symbol">}}o--||</span>
                    <span>Many-to-One relationship (Foreign Key → Primary Key)</span>
                </div>
                <div class="legend-item">
                    <span style="color: #4CAF50; font-weight: bold;">●</span>
                    <span>Entity (Table)</span>
                </div>
                <div class="legend-item">
                    <span style="color: #666; font-weight: bold;">→</span>
                    <span>FK Column → PK Column</span>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        mermaid.initialize({{ 
            startOnLoad: true,
            theme: 'default',
            er: {{
                fontSize: 16,
                useMaxWidth: false
            }}
        }});
        
        let currentZoom = 1;
        const diagram = document.getElementById('diagram');
        
        function resetZoom() {{
            currentZoom = 1;
            diagram.className = '';
            const svg = diagram.querySelector('svg');
            if (svg) svg.style.transform = 'scale(1)';
        }}
        
        function zoomIn() {{
            currentZoom = Math.min(currentZoom + 0.3, 3);
            const svg = diagram.querySelector('svg');
            if (svg) svg.style.transform = `scale(${{currentZoom}})`;
        }}
        
        function zoomOut() {{
            currentZoom = Math.max(currentZoom - 0.3, 0.5);
            const svg = diagram.querySelector('svg');
            if (svg) svg.style.transform = `scale(${{currentZoom}})`;
        }}
        
        function fitToScreen() {{
            const svg = diagram.querySelector('svg');
            if (svg) {{
                const containerWidth = diagram.clientWidth;
                const svgWidth = svg.getBoundingClientRect().width / currentZoom;
                currentZoom = (containerWidth * 0.9) / svgWidth;
                svg.style.transform = `scale(${{currentZoom}})`;
            }}
        }}
        
        // Enable mouse wheel zoom
        diagram.addEventListener('wheel', (e) => {{
            if (e.ctrlKey) {{
                e.preventDefault();
                if (e.deltaY < 0) {{
                    zoomIn();
                }} else {{
                    zoomOut();
                }}
            }}
        }});
    </script>
</body>
</html>
"""
        
        output_path = self.output_dir / "erd_diagram.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"  ✓ ERD diagram saved to: {output_path}")
        print(f"    Tables: {len(tables)}, Relationships: {len(true_fks)}")
