"""
Visualization Engine — Main orchestrator for all visualization types

Reads relationships.json and generates:
- Relationship Confidence Charts
- ERD Diagrams
- Knowledge Graphs
- Quality Dashboards
- Full Report Dashboards
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

log = logging.getLogger(__name__)


class VisualizationEngine:
    """Main visualization engine that coordinates all chart/diagram generation."""
    
    def __init__(self, relationships_path: str = "output/relationships/relationships.json"):
        """
        Initialize the visualization engine.
        
        Args:
            relationships_path: Path to relationships.json file
        """
        self.relationships_path = Path(relationships_path)
        self.relationships_data = None
        self.output_dir = Path("output/visualizations")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def load_relationships(self) -> bool:
        """
        Load relationships.json file.
        
        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            if not self.relationships_path.exists():
                log.error(f"Relationships file not found: {self.relationships_path}")
                return False
                
            with open(self.relationships_path, 'r', encoding='utf-8') as f:
                self.relationships_data = json.load(f)
                
            log.info(f"✓ Loaded relationships.json")
            log.info(f"  Total relationships: {self.relationships_data['metadata']['total_relationships']}")
            log.info(f"  TRUE_FK count: {self.relationships_data['metadata']['true_fk_count']}")
            
            return True
            
        except Exception as e:
            log.error(f"Failed to load relationships: {e}")
            return False
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata from relationships.json."""
        if not self.relationships_data:
            return {}
        return self.relationships_data.get("metadata", {})
    
    def get_relationships(self) -> List[Dict[str, Any]]:
        """Get all relationships from relationships.json."""
        if not self.relationships_data:
            return []
        return self.relationships_data.get("relationships", [])
    
    def get_relationships_by_type(self, relationship_type: str) -> List[Dict[str, Any]]:
        """
        Get relationships filtered by type.
        
        Args:
            relationship_type: One of TRUE_FK, SEMANTICALLY_RELATED, 
                             SHARED_ENTITY_DOMAIN, POSSIBLE_REFERENCE
        
        Returns:
            List of relationships matching the type
        """
        relationships = self.get_relationships()
        return [r for r in relationships if r.get("relationship_class") == relationship_type]
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Calculate statistics from relationships data.
        
        Returns:
            Dictionary with various statistics
        """
        relationships = self.get_relationships()
        
        if not relationships:
            return {}
        
        # Count by relationship type
        type_counts = {}
        for rel in relationships:
            rel_type = rel.get("relationship_class", "UNKNOWN")
            type_counts[rel_type] = type_counts.get(rel_type, 0) + 1
        
        # Confidence distribution
        confidences = [r.get("confidence_score", 0) for r in relationships]
        
        # Semantic similarity distribution
        similarities = [r.get("semantic_similarity", 0) for r in relationships]
        
        # Containment ratio distribution
        containments = [r.get("containment_ratio", 0) for r in relationships]
        
        return {
            "type_counts": type_counts,
            "total_relationships": len(relationships),
            "confidence": {
                "min": min(confidences) if confidences else 0,
                "max": max(confidences) if confidences else 0,
                "avg": sum(confidences) / len(confidences) if confidences else 0,
            },
            "semantic_similarity": {
                "min": min(similarities) if similarities else 0,
                "max": max(similarities) if similarities else 0,
                "avg": sum(similarities) / len(similarities) if similarities else 0,
            },
            "containment_ratio": {
                "min": min(containments) if containments else 0,
                "max": max(containments) if containments else 0,
                "avg": sum(containments) / len(containments) if containments else 0,
            },
        }
    
    def generate_all(self):
        """Generate all visualization types."""
        from visualization.charts import RelationshipCharts
        from visualization.erd import ERDGenerator
        from visualization.knowledge_graph import KnowledgeGraphGenerator
        from visualization.quality_dashboard import QualityDashboard
        
        print("\n" + "=" * 80)
        print("GENERATING ALL VISUALIZATIONS")
        print("=" * 80)
        
        # Load data
        if not self.load_relationships():
            print("\n[ERROR] Failed to load relationships.json")
            return
        
        # 1. Relationship Confidence Chart
        print("\n[1/5] Generating Relationship Confidence Chart...")
        charts = RelationshipCharts(self)
        charts.generate_confidence_chart()
        
        # 2. ERD Diagram
        print("\n[2/5] Generating ERD Diagram...")
        erd = ERDGenerator(self)
        erd.generate_erd()
        
        # 3. Knowledge Graph
        print("\n[3/5] Generating Knowledge Graph...")
        kg = KnowledgeGraphGenerator(self)
        kg.generate_graph()
        
        # 4. Quality Dashboard
        print("\n[4/5] Generating Quality Dashboard...")
        quality = QualityDashboard(self)
        quality.generate_dashboard()
        
        # 5. Full Report Dashboard
        print("\n[5/5] Generating Full Report Dashboard...")
        self.generate_full_report()
        
        print("\n" + "=" * 80)
        print("✓ ALL VISUALIZATIONS GENERATED")
        print("=" * 80)
        print(f"\nOutput directory: {self.output_dir.absolute()}")
    
    def generate_full_report(self):
        """Generate a comprehensive HTML report with all visualizations."""
        output_path = self.output_dir / "full_report.html"
        
        stats = self.get_statistics()
        metadata = self.get_metadata()
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Semantic Profiling - Full Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            color: #333;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }}
        .header p {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        .content {{
            padding: 40px;
        }}
        .section {{
            margin-bottom: 40px;
        }}
        .section h2 {{
            color: #667eea;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
            margin-bottom: 20px;
            font-size: 1.8em;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }}
        .stat-card:hover {{
            transform: translateY(-5px);
        }}
        .stat-card h3 {{
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 10px;
            opacity: 0.9;
        }}
        .stat-card .value {{
            font-size: 2.5em;
            font-weight: bold;
        }}
        .visualization-links {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }}
        .viz-card {{
            background: #f8f9fa;
            border: 2px solid #e9ecef;
            border-radius: 15px;
            padding: 30px;
            text-align: center;
            transition: all 0.3s;
            cursor: pointer;
        }}
        .viz-card:hover {{
            border-color: #667eea;
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.2);
            transform: translateY(-5px);
        }}
        .viz-card h3 {{
            color: #667eea;
            margin-bottom: 15px;
            font-size: 1.4em;
        }}
        .viz-card p {{
            color: #666;
            line-height: 1.6;
        }}
        .viz-card a {{
            display: inline-block;
            margin-top: 15px;
            padding: 10px 20px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            transition: background 0.3s;
        }}
        .viz-card a:hover {{
            background: #764ba2;
        }}
        .type-breakdown {{
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            margin-top: 20px;
        }}
        .type-badge {{
            background: #f8f9fa;
            border: 2px solid #667eea;
            padding: 15px 25px;
            border-radius: 10px;
            flex: 1;
            min-width: 200px;
        }}
        .type-badge .type-name {{
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }}
        .type-badge .type-count {{
            font-size: 2em;
            font-weight: bold;
            color: #333;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            border-top: 1px solid #e9ecef;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎯 Semantic Profiling Dashboard</h1>
            <p>Complete Relationship Analysis & Visualization Report</p>
            <p style="font-size: 0.9em; margin-top: 10px;">Generated: {metadata.get('generation_timestamp', 'N/A')}</p>
        </div>
        
        <div class="content">
            <div class="section">
                <h2>📊 Key Metrics</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <h3>Total Relationships</h3>
                        <div class="value">{stats.get('total_relationships', 0):,}</div>
                    </div>
                    <div class="stat-card">
                        <h3>True Foreign Keys</h3>
                        <div class="value">{metadata.get('true_fk_count', 0):,}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Avg Confidence</h3>
                        <div class="value">{stats.get('confidence', {}).get('avg', 0):.2f}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Avg Semantic Similarity</h3>
                        <div class="value">{stats.get('semantic_similarity', {}).get('avg', 0):.2f}</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>📈 Relationship Type Breakdown</h2>
                <div class="type-breakdown">
"""
        
        # Add type breakdown
        for rel_type, count in stats.get('type_counts', {}).items():
            html += f"""
                    <div class="type-badge">
                        <div class="type-name">{rel_type.replace('_', ' ')}</div>
                        <div class="type-count">{count:,}</div>
                    </div>
"""
        
        html += """
                </div>
            </div>
            
            <div class="section">
                <h2>🎨 Available Visualizations</h2>
                <div class="visualization-links">
                    <div class="viz-card">
                        <h3>📊 Confidence Chart</h3>
                        <p>Interactive scatter plot showing relationship confidence vs semantic similarity across all relationship types.</p>
                        <a href="confidence_chart.html" target="_blank">View Chart →</a>
                    </div>
                    <div class="viz-card">
                        <h3>🗺️ ERD Diagram</h3>
                        <p>Entity Relationship Diagram showing TRUE_FK connections between tables with cardinality.</p>
                        <a href="erd_diagram.html" target="_blank">View ERD →</a>
                    </div>
                    <div class="viz-card">
                        <h3>🕸️ Knowledge Graph</h3>
                        <p>Interactive network graph showing all relationship types with force-directed layout.</p>
                        <a href="knowledge_graph.html" target="_blank">View Graph →</a>
                    </div>
                    <div class="viz-card">
                        <h3>📋 Quality Dashboard</h3>
                        <p>Comprehensive quality metrics including confidence distribution and containment analysis.</p>
                        <a href="quality_dashboard.html" target="_blank">View Dashboard →</a>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>Semantic Profiling Pipeline - Visualization Engine v1.0</p>
            <p style="font-size: 0.9em; margin-top: 5px;">Powered by relationship.json analysis</p>
        </div>
    </div>
</body>
</html>
"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"  ✓ Full report saved to: {output_path}")
