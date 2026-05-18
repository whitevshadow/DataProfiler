"""
Quality Dashboard — Comprehensive quality metrics visualization

Generates dashboards showing:
- Confidence distribution
- Containment ratio analysis
- Semantic similarity distribution
- Relationship type breakdown
- Quality score trends
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from visualization.engine import VisualizationEngine

log = logging.getLogger(__name__)


class QualityDashboard:
    """Generate comprehensive quality metrics dashboard."""
    
    def __init__(self, engine: 'VisualizationEngine'):
        """
        Initialize quality dashboard generator.
        
        Args:
            engine: VisualizationEngine instance
        """
        self.engine = engine
        self.output_dir = engine.output_dir
    
    def generate_dashboard(self):
        """Generate interactive quality metrics dashboard."""
        relationships = self.engine.get_relationships()
        stats = self.engine.get_statistics()
        metadata = self.engine.get_metadata()
        
        if not relationships:
            log.warning("No relationships for quality dashboard")
            return
        
        # Prepare data for charts
        confidence_buckets = self._bucket_values([r.get('confidence_score', 0) for r in relationships])
        similarity_buckets = self._bucket_values([r.get('semantic_similarity', 0) for r in relationships])
        containment_buckets = self._bucket_values([r.get('containment_ratio', 0) for r in relationships])
        
        # Type counts
        type_counts = stats.get('type_counts', {})
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Quality Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
        }}
        .container {{
            max-width: 1600px;
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
            font-size: 2.2em;
            margin-bottom: 10px;
        }}
        .content {{
            padding: 40px;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        .metric-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .metric-card h3 {{
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 10px;
            opacity: 0.9;
        }}
        .metric-card .value {{
            font-size: 2.5em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .metric-card .detail {{
            font-size: 0.85em;
            opacity: 0.8;
        }}
        .chart-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 30px;
            margin-bottom: 30px;
        }}
        .chart-container {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 15px;
        }}
        .chart-container h2 {{
            color: #667eea;
            margin-bottom: 15px;
            font-size: 1.3em;
        }}
        .chart {{
            width: 100%;
            height: 500px;
        }}
        .quality-score {{
            background: linear-gradient(135deg, #4CAF50 0%, #8BC34A 100%);
            color: white;
            padding: 40px;
            border-radius: 15px;
            text-align: center;
            margin-bottom: 30px;
        }}
        .quality-score h2 {{
            font-size: 1.5em;
            margin-bottom: 20px;
        }}
        .score-circle {{
            width: 200px;
            height: 200px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.2);
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto;
            border: 5px solid white;
        }}
        .score-value {{
            font-size: 4em;
            font-weight: bold;
        }}
        .recommendations {{
            background: #f8f9fa;
            padding: 30px;
            border-radius: 15px;
            margin-top: 30px;
        }}
        .recommendations h2 {{
            color: #667eea;
            margin-bottom: 20px;
        }}
        .recommendation {{
            background: white;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        .recommendation.warning {{
            border-left-color: #FF9800;
        }}
        .recommendation.success {{
            border-left-color: #4CAF50;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📋 Quality Dashboard</h1>
            <p>Comprehensive Relationship Quality Metrics</p>
            <p style="font-size: 0.9em; margin-top: 10px;">Generated: {metadata.get('generation_timestamp', 'N/A')}</p>
        </div>
        
        <div class="content">
            <!-- Key Metrics -->
            <div class="metrics-grid">
                <div class="metric-card">
                    <h3>Total Relationships</h3>
                    <div class="value">{stats['total_relationships']:,}</div>
                    <div class="detail">{metadata.get('total_candidates', 0):,} candidates analyzed</div>
                </div>
                <div class="metric-card">
                    <h3>TRUE Foreign Keys</h3>
                    <div class="value">{metadata.get('true_fk_count', 0):,}</div>
                    <div class="detail">{(metadata.get('true_fk_count', 0) / stats['total_relationships'] * 100) if stats['total_relationships'] > 0 else 0:.1f}% of total</div>
                </div>
                <div class="metric-card">
                    <h3>Avg Confidence</h3>
                    <div class="value">{stats['confidence']['avg']:.2f}</div>
                    <div class="detail">Range: {stats['confidence']['min']:.2f} - {stats['confidence']['max']:.2f}</div>
                </div>
                <div class="metric-card">
                    <h3>Avg Similarity</h3>
                    <div class="value">{stats['semantic_similarity']['avg']:.2f}</div>
                    <div class="detail">Range: {stats['semantic_similarity']['min']:.2f} - {stats['semantic_similarity']['max']:.2f}</div>
                </div>
                <div class="metric-card">
                    <h3>Avg Containment</h3>
                    <div class="value">{stats['containment_ratio']['avg']:.2f}</div>
                    <div class="detail">Range: {stats['containment_ratio']['min']:.2f} - {stats['containment_ratio']['max']:.2f}</div>
                </div>
                <div class="metric-card">
                    <h3>Relationship Types</h3>
                    <div class="value">{len(type_counts)}</div>
                    <div class="detail">{metadata.get('clusters_found', 0)} semantic clusters</div>
                </div>
            </div>
            
            <!-- Overall Quality Score -->
            <div class="quality-score">
                <h2>Overall Quality Score</h2>
                <div class="score-circle">
                    <div class="score-value">{self._calculate_quality_score(stats, metadata)}</div>
                </div>
                <p style="margin-top: 20px; font-size: 1.1em;">Based on confidence, containment, and semantic alignment</p>
            </div>
            
            <!-- Charts -->
            <div class="chart-grid">
                <div class="chart-container">
                    <h2>Confidence Distribution</h2>
                    <div id="confidenceChart" class="chart"></div>
                </div>
                <div class="chart-container">
                    <h2>Semantic Similarity Distribution</h2>
                    <div id="similarityChart" class="chart"></div>
                </div>
                <div class="chart-container">
                    <h2>Containment Ratio Distribution</h2>
                    <div id="containmentChart" class="chart"></div>
                </div>
                <div class="chart-container">
                    <h2>Relationship Type Breakdown</h2>
                    <div id="typeChart" class="chart"></div>
                </div>
            </div>
            
            <!-- Recommendations -->
            <div class="recommendations">
                <h2>Quality Recommendations</h2>
                {self._generate_recommendations(stats, metadata)}
            </div>
        </div>
    </div>
    
    <script>
        // Confidence Distribution
        const confidenceData = [{{
            x: {list(confidence_buckets.keys())},
            y: {list(confidence_buckets.values())},
            type: 'bar',
            marker: {{
                color: '#667eea',
                line: {{ color: '#764ba2', width: 2 }}
            }}
        }}];
        
        Plotly.newPlot('confidenceChart', confidenceData, {{
            xaxis: {{ title: 'Confidence Score', range: [0, 1] }},
            yaxis: {{ title: 'Count' }},
            margin: {{ t: 10 }},
            paper_bgcolor: '#f8f9fa',
            plot_bgcolor: '#fafafa'
        }}, {{ responsive: true, scrollZoom: true, displayModeBar: true }});
        
        // Similarity Distribution
        const similarityData = [{{
            x: {list(similarity_buckets.keys())},
            y: {list(similarity_buckets.values())},
            type: 'bar',
            marker: {{
                color: '#2196F3',
                line: {{ color: '#1976D2', width: 2 }}
            }}
        }}];
        
        Plotly.newPlot('similarityChart', similarityData, {{
            xaxis: {{ title: 'Semantic Similarity', range: [0, 1] }},
            yaxis: {{ title: 'Count' }},
            margin: {{ t: 10 }},
            paper_bgcolor: '#f8f9fa',
            plot_bgcolor: '#fafafa'
        }}, {{ responsive: true, scrollZoom: true, displayModeBar: true }});
        
        // Containment Distribution
        const containmentData = [{{
            x: {list(containment_buckets.keys())},
            y: {list(containment_buckets.values())},
            type: 'bar',
            marker: {{
                color: '#4CAF50',
                line: {{ color: '#388E3C', width: 2 }}
            }}
        }}];
        
        Plotly.newPlot('containmentChart', containmentData, {{
            xaxis: {{ title: 'Containment Ratio', range: [0, 1] }},
            yaxis: {{ title: 'Count' }},
            margin: {{ t: 10 }},
            paper_bgcolor: '#f8f9fa',
            plot_bgcolor: '#fafafa'
        }}, {{ responsive: true, scrollZoom: true, displayModeBar: true }});
        
        // Type Breakdown
        const typeData = [{{
            labels: {[k.replace('_', ' ') for k in type_counts.keys()]},
            values: {list(type_counts.values())},
            type: 'pie',
            marker: {{
                colors: ['#4CAF50', '#2196F3', '#FF9800', '#9C27B0', '#F44336']
            }},
            textinfo: 'label+percent',
            textposition: 'outside'
        }}];
        
        Plotly.newPlot('typeChart', typeData, {{
            margin: {{ t: 10 }},
            paper_bgcolor: '#f8f9fa'
        }}, {{ responsive: true }});
    </script>
</body>
</html>
"""
        
        output_path = self.output_dir / "quality_dashboard.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"  ✓ Quality dashboard saved to: {output_path}")
    
    def _bucket_values(self, values, num_buckets=10):
        """Bucket numeric values into histogram bins."""
        if not values:
            return {}
        
        buckets = {}
        bucket_size = 1.0 / num_buckets
        
        for val in values:
            bucket_idx = min(int(val / bucket_size), num_buckets - 1)
            bucket_label = round(bucket_idx * bucket_size, 2)
            buckets[bucket_label] = buckets.get(bucket_label, 0) + 1
        
        # Ensure all buckets exist
        for i in range(num_buckets):
            bucket_label = round(i * bucket_size, 2)
            if bucket_label not in buckets:
                buckets[bucket_label] = 0
        
        return dict(sorted(buckets.items()))
    
    def _calculate_quality_score(self, stats, metadata):
        """Calculate overall quality score (0-100)."""
        total_rels = stats.get('total_relationships', 1)
        true_fk_count = metadata.get('true_fk_count', 0)
        
        # Weight factors
        fk_ratio = true_fk_count / total_rels if total_rels > 0 else 0
        avg_confidence = stats.get('confidence', {}).get('avg', 0)
        avg_containment = stats.get('containment_ratio', {}).get('avg', 0)
        
        # Weighted score
        score = (
            fk_ratio * 30 +  # 30% weight on FK detection rate
            avg_confidence * 40 +  # 40% weight on confidence
            avg_containment * 30  # 30% weight on containment
        ) * 100
        
        return int(score)
    
    def _generate_recommendations(self, stats, metadata):
        """Generate quality improvement recommendations."""
        recommendations = []
        
        total_rels = stats.get('total_relationships', 1)
        true_fk_count = metadata.get('true_fk_count', 0)
        avg_confidence = stats.get('confidence', {}).get('avg', 0)
        avg_containment = stats.get('containment_ratio', {}).get('avg', 0)
        
        # FK detection rate
        fk_ratio = true_fk_count / total_rels if total_rels > 0 else 0
        if fk_ratio < 0.1:
            recommendations.append(
                '<div class="recommendation warning">'
                f'<strong>⚠️ Low TRUE_FK Detection Rate ({fk_ratio*100:.1f}%)</strong><br>'
                'Consider reviewing relationship detection thresholds or data quality.'
                '</div>'
            )
        elif fk_ratio > 0.2:
            recommendations.append(
                '<div class="recommendation success">'
                f'<strong>✓ Good TRUE_FK Detection Rate ({fk_ratio*100:.1f}%)</strong><br>'
                'Foreign key relationships are being detected effectively.'
                '</div>'
            )
        
        # Confidence levels
        if avg_confidence < 0.5:
            recommendations.append(
                '<div class="recommendation warning">'
                f'<strong>⚠️ Low Average Confidence ({avg_confidence:.2f})</strong><br>'
                'Many relationships have low confidence. Review semantic similarity thresholds.'
                '</div>'
            )
        elif avg_confidence > 0.7:
            recommendations.append(
                '<div class="recommendation success">'
                f'<strong>✓ High Average Confidence ({avg_confidence:.2f})</strong><br>'
                'Relationship detection is producing high-confidence results.'
                '</div>'
            )
        
        # Containment ratios
        if avg_containment < 0.3:
            recommendations.append(
                '<div class="recommendation">'
                f'<strong>ℹ️ Low Average Containment ({avg_containment:.2f})</strong><br>'
                'Most relationships are semantic rather than referential. This is normal for semantic analysis.'
                '</div>'
            )
        
        # Data quality
        if total_rels > 1000:
            recommendations.append(
                '<div class="recommendation">'
                f'<strong>ℹ️ Large Relationship Set ({total_rels:,})</strong><br>'
                'Consider filtering by confidence threshold to focus on high-quality relationships.'
                '</div>'
            )
        
        if not recommendations:
            recommendations.append(
                '<div class="recommendation success">'
                '<strong>✓ Overall Quality Looks Good</strong><br>'
                'No major quality issues detected. Keep monitoring metrics over time.'
                '</div>'
            )
        
        return '\n'.join(recommendations)
