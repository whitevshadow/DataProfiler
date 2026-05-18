"""
Knowledge Graph Generator — Interactive network visualization

Generates force-directed network graphs showing:
- All relationship types
- Color-coded by relationship class
- Interactive drag/zoom
- Hover details
- Link thickness by confidence
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Set

if TYPE_CHECKING:
    from visualization.engine import VisualizationEngine

log = logging.getLogger(__name__)


class KnowledgeGraphGenerator:
    """Generate interactive knowledge graph of all relationships."""
    
    def __init__(self, engine: 'VisualizationEngine'):
        """
        Initialize knowledge graph generator.
        
        Args:
            engine: VisualizationEngine instance
        """
        self.engine = engine
        self.output_dir = engine.output_dir
    
    def generate_graph(self):
        """Generate interactive force-directed network graph using D3.js."""
        relationships = self.engine.get_relationships()
        
        if not relationships:
            log.warning("No relationships to visualize")
            return
        
        # Collect all unique tables (nodes)
        tables = set()
        for rel in relationships:
            tables.add(rel['fk_table'])
            tables.add(rel['pk_table'])
        
        # Build nodes
        nodes = []
        table_to_idx = {}
        for idx, table in enumerate(sorted(tables)):
            table_to_idx[table] = idx
            nodes.append({
                "id": idx,
                "name": table,
            })
        
        # Build links (sample to avoid overwhelming visualization)
        # Prioritize TRUE_FK and high-confidence relationships
        sorted_relationships = sorted(
            relationships,
            key=lambda r: (
                1 if r['relationship_class'] == 'TRUE_FK' else 0,
                r.get('confidence_score', 0)
            ),
            reverse=True
        )
        
        # Take top relationships to avoid clutter
        max_links = 500
        selected_relationships = sorted_relationships[:max_links]
        
        links = []
        for rel in selected_relationships:
            source_idx = table_to_idx[rel['fk_table']]
            target_idx = table_to_idx[rel['pk_table']]
            
            links.append({
                "source": source_idx,
                "target": target_idx,
                "type": rel['relationship_class'],
                "confidence": rel.get('confidence_score', 0),
                "similarity": rel.get('semantic_similarity', 0),
                "containment": rel.get('containment_ratio', 0),
                "fk_column": rel.get('fk_column', ''),
                "pk_column": rel.get('pk_column', ''),
            })
        
        # Color mapping
        colors = {
            "TRUE_FK": "#4CAF50",
            "SEMANTICALLY_RELATED": "#2196F3",
            "SHARED_ENTITY_DOMAIN": "#FF9800",
            "POSSIBLE_REFERENCE": "#9C27B0",
            "FALSE_POSITIVE": "#F44336",
        }
        
        # Build HTML with D3.js
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Knowledge Graph</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            overflow: hidden;
        }}
        .container {{
            max-width: 1800px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
            height: calc(100vh - 40px);
            display: flex;
            flex-direction: column;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 30px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 1.8em;
            margin-bottom: 5px;
        }}
        .controls {{
            padding: 15px 30px;
            background: #f8f9fa;
            border-bottom: 1px solid #e0e0e0;
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
            align-items: center;
        }}
        .control-group {{
            display: flex;
            gap: 10px;
            align-items: center;
        }}
        .control-group label {{
            font-weight: 500;
            color: #555;
        }}
        .control-group input[type="range"] {{
            width: 150px;
        }}
        .zoom-controls {{
            display: flex;
            gap: 10px;
            border-left: 2px solid #ddd;
            padding-left: 20px;
        }}
        .zoom-btn {{
            padding: 8px 16px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9em;
            transition: background 0.3s;
        }}
        .zoom-btn:hover {{
            background: #764ba2;
        }}
        .legend {{
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 5px;
            font-size: 0.9em;
        }}
        .legend-color {{
            width: 15px;
            height: 15px;
            border-radius: 50%;
        }}
        #graph {{
            flex: 1;
            background: #fafafa;
            position: relative;
        }}
        .tooltip {{
            position: absolute;
            background: rgba(0, 0, 0, 0.9);
            color: white;
            padding: 10px 15px;
            border-radius: 8px;
            pointer-events: none;
            font-size: 0.85em;
            display: none;
            z-index: 1000;
            max-width: 300px;
        }}
        .tooltip h4 {{
            margin-bottom: 5px;
            font-size: 1em;
        }}
        .tooltip p {{
            margin: 2px 0;
            line-height: 1.4;
        }}
        .stats {{
            padding: 10px 30px;
            background: #f8f9fa;
            border-top: 1px solid #e0e0e0;
            display: flex;
            gap: 30px;
            font-size: 0.9em;
        }}
        .stat {{
            color: #555;
        }}
        .stat strong {{
            color: #667eea;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🕸️ Knowledge Graph</h1>
            <p>Interactive Network Visualization of All Relationships</p>
        </div>
        
        <div class="controls">
            <div class="control-group">
                <label for="charge">Repulsion:</label>
                <input type="range" id="charge" min="-500" max="-50" value="-200" step="10">
                <span id="chargeValue">-200</span>
            </div>
            
            <div class="control-group">
                <label for="distance">Link Distance:</label>
                <input type="range" id="distance" min="30" max="200" value="80" step="5">
                <span id="distanceValue">80</span>
            </div>
            
            <div class="legend">
                <strong>Relationships:</strong>
                {"".join(f'<div class="legend-item"><div class="legend-color" style="background: {color};"></div><span>{rtype.replace("_", " ")}</span></div>' for rtype, color in colors.items())}
            </div>
            
            <div class="zoom-controls">
                <button class="zoom-btn" onclick="resetGraphZoom()">🔄 Reset</button>
                <button class="zoom-btn" onclick="zoomGraphIn()">🔍 Zoom In</button>
                <button class="zoom-btn" onclick="zoomGraphOut()">🔎 Zoom Out</button>
                <button class="zoom-btn" onclick="centerGraph()">📍 Center</button>
            </div>
        </div>
        
        <div id="graph"></div>
        <div class="tooltip" id="tooltip"></div>
        
        <div class="stats">
            <div class="stat"><strong>Nodes:</strong> {len(nodes)} tables</div>
            <div class="stat"><strong>Links:</strong> {len(links)} relationships</div>
            <div class="stat"><strong>Note:</strong> Showing top {max_links} relationships (prioritized by TRUE_FK and confidence)</div>
        </div>
    </div>
    
    <script>
        const nodes = {nodes};
        const links = {links};
        
        const colors = {colors};
        
        const width = window.innerWidth - 80;
        const height = window.innerHeight - 280;
        
        // Create SVG
        const svg = d3.select("#graph")
            .append("svg")
            .attr("width", width)
            .attr("height", height);
        
        // Add zoom
        const g = svg.append("g");
        
        const zoom = d3.zoom()
            .scaleExtent([0.1, 8])
            .on("zoom", (event) => {{
                g.attr("transform", event.transform);
            }});
        
        svg.call(zoom);
        
        // Store zoom behavior for controls
        window.graphZoom = zoom;
        window.graphSvg = svg;
        
        // Create force simulation
        let chargeStrength = -200;
        let linkDistance = 80;
        
        const simulation = d3.forceSimulation(nodes)
            .force("link", d3.forceLink(links).id(d => d.id).distance(linkDistance))
            .force("charge", d3.forceManyBody().strength(chargeStrength))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collision", d3.forceCollide().radius(30));
        
        // Draw links
        const link = g.append("g")
            .selectAll("line")
            .data(links)
            .enter().append("line")
            .attr("stroke", d => colors[d.type] || "#999")
            .attr("stroke-opacity", 0.6)
            .attr("stroke-width", d => Math.max(1, d.confidence * 4));
        
        // Draw nodes
        const node = g.append("g")
            .selectAll("circle")
            .data(nodes)
            .enter().append("circle")
            .attr("r", 8)
            .attr("fill", "#667eea")
            .attr("stroke", "#fff")
            .attr("stroke-width", 2)
            .call(d3.drag()
                .on("start", dragstarted)
                .on("drag", dragged)
                .on("end", dragended));
        
        // Add labels
        const label = g.append("g")
            .selectAll("text")
            .data(nodes)
            .enter().append("text")
            .text(d => d.name)
            .attr("font-size", 10)
            .attr("dx", 12)
            .attr("dy", 4)
            .attr("fill", "#333");
        
        // Tooltip
        const tooltip = d3.select("#tooltip");
        
        node.on("mouseover", (event, d) => {{
            const connectedLinks = links.filter(l => l.source.id === d.id || l.target.id === d.id);
            tooltip.style("display", "block")
                .html(`
                    <h4>${{d.name}}</h4>
                    <p><strong>Connections:</strong> ${{connectedLinks.length}}</p>
                    <p><strong>Outgoing FK:</strong> ${{connectedLinks.filter(l => l.source.id === d.id).length}}</p>
                    <p><strong>Referenced by:</strong> ${{connectedLinks.filter(l => l.target.id === d.id).length}}</p>
                `);
        }})
        .on("mousemove", (event) => {{
            tooltip.style("left", (event.pageX + 15) + "px")
                .style("top", (event.pageY - 30) + "px");
        }})
        .on("mouseout", () => {{
            tooltip.style("display", "none");
        }});
        
        link.on("mouseover", (event, d) => {{
            tooltip.style("display", "block")
                .html(`
                    <h4>${{d.type.replace(/_/g, ' ')}}</h4>
                    <p><strong>From:</strong> ${{d.source.name}}.${{d.fk_column}}</p>
                    <p><strong>To:</strong> ${{d.target.name}}.${{d.pk_column}}</p>
                    <p><strong>Confidence:</strong> ${{d.confidence.toFixed(3)}}</p>
                    <p><strong>Similarity:</strong> ${{d.similarity.toFixed(3)}}</p>
                    <p><strong>Containment:</strong> ${{d.containment.toFixed(3)}}</p>
                `);
        }})
        .on("mousemove", (event) => {{
            tooltip.style("left", (event.pageX + 15) + "px")
                .style("top", (event.pageY - 30) + "px");
        }})
        .on("mouseout", () => {{
            tooltip.style("display", "none");
        }});
        
        // Update positions on tick
        simulation.on("tick", () => {{
            link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);
            
            node
                .attr("cx", d => d.x)
                .attr("cy", d => d.y);
            
            label
                .attr("x", d => d.x)
                .attr("y", d => d.y);
        }});
        
        // Drag functions
        function dragstarted(event, d) {{
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }}
        
        function dragged(event, d) {{
            d.fx = event.x;
            d.fy = event.y;
        }}
        
        function dragended(event, d) {{
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
        }}
        
        // Controls
        document.getElementById("charge").addEventListener("input", (e) => {{
            chargeStrength = +e.target.value;
            document.getElementById("chargeValue").textContent = chargeStrength;
            simulation.force("charge", d3.forceManyBody().strength(chargeStrength));
            simulation.alpha(0.3).restart();
        }});
        
        
        // Zoom control functions
        function resetGraphZoom() {{
            window.graphSvg.transition().duration(750).call(
                window.graphZoom.transform,
                d3.zoomIdentity
            );
        }}
        
        function zoomGraphIn() {{
            window.graphSvg.transition().duration(300).call(
                window.graphZoom.scaleBy,
                1.5
            );
        }}
        
        function zoomGraphOut() {{
            window.graphSvg.transition().duration(300).call(
                window.graphZoom.scaleBy,
                0.67
            );
        }}
        
        function centerGraph() {{
            window.graphSvg.transition().duration(750).call(
                window.graphZoom.transform,
                d3.zoomIdentity.translate(width / 2, height / 2).scale(1)
            );
        }}
        document.getElementById("distance").addEventListener("input", (e) => {{
            linkDistance = +e.target.value;
            document.getElementById("distanceValue").textContent = linkDistance;
            simulation.force("link", d3.forceLink(links).id(d => d.id).distance(linkDistance));
            simulation.alpha(0.3).restart();
        }});
    </script>
</body>
</html>
"""
        
        output_path = self.output_dir / "knowledge_graph.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"  ✓ Knowledge graph saved to: {output_path}")
        print(f"    Nodes: {len(nodes)}, Links: {len(links)}")
