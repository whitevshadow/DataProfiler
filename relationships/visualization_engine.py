"""
Visualization Engine for Schema Profiling Pipeline

Generates interactive charts, ERD diagrams, and knowledge graphs
from relationship detection results.

Capabilities:
    - Relationship confidence distribution charts
    - Entity-Relationship Diagrams (ERD)
    - Knowledge graph visualizations
    - Quality dashboard with metrics
    - Interactive HTML reports
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict, Counter
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
import pandas as pd
import networkx as nx
from datetime import datetime

# Set style
sns.set_theme(style="whitegrid")
plt.rcParams['figure.figsize'] = (12, 8)
plt.rcParams['font.size'] = 10


@dataclass
class RelationshipStats:
    """Statistical summary of relationships."""
    total_relationships: int
    true_fk_count: int
    semantically_related_count: int
    possible_reference_count: int
    shared_entity_count: int
    avg_confidence: float
    avg_semantic_similarity: float
    avg_containment: float
    tables_count: int
    columns_count: int


class VisualizationEngine:
    """
    Master visualization engine for profiling pipeline.
    
    Generates comprehensive visual analytics from relationship detection results.
    """
    
    def __init__(self, relationships_file: str, output_dir: str = "output/visualizations"):
        """
        Initialize visualization engine.
        
        Args:
            relationships_file: Path to relationships.json
            output_dir: Output directory for visualizations
        """
        self.relationships_file = Path(relationships_file)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load relationship data
        with open(self.relationships_file, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        
        self.metadata = self.data.get("metadata", {})
        self.relationships = self.data.get("relationships", [])
        
        # Compute statistics
        self.stats = self._compute_statistics()
        
        print(f"[VIZ] Loaded {len(self.relationships)} relationships")
        print(f"[VIZ] TRUE_FK: {self.stats.true_fk_count}")
        print(f"[VIZ] Output: {self.output_dir}")
    
    def _compute_statistics(self) -> RelationshipStats:
        """Compute statistical summary of relationships."""
        
        if not self.relationships:
            return RelationshipStats(
                total_relationships=0,
                true_fk_count=0,
                semantically_related_count=0,
                possible_reference_count=0,
                shared_entity_count=0,
                avg_confidence=0.0,
                avg_semantic_similarity=0.0,
                avg_containment=0.0,
                tables_count=0,
                columns_count=0
            )
        
        # Count by class
        class_counts = Counter(r["relationship_class"] for r in self.relationships)
        
        # Average metrics
        confidences = [r["confidence_score"] for r in self.relationships]
        similarities = [r["semantic_similarity"] for r in self.relationships]
        containments = [r["containment_ratio"] for r in self.relationships]
        
        # Unique tables and columns
        tables = set()
        columns = set()
        for r in self.relationships:
            tables.add(r["fk_table"])
            tables.add(r["pk_table"])
            columns.add((r["fk_table"], r["fk_column"]))
            columns.add((r["pk_table"], r["pk_column"]))
        
        return RelationshipStats(
            total_relationships=len(self.relationships),
            true_fk_count=class_counts.get("TRUE_FK", 0),
            semantically_related_count=class_counts.get("SEMANTICALLY_RELATED", 0),
            possible_reference_count=class_counts.get("POSSIBLE_REFERENCE", 0),
            shared_entity_count=class_counts.get("SHARED_ENTITY_DOMAIN", 0),
            avg_confidence=sum(confidences) / len(confidences) if confidences else 0.0,
            avg_semantic_similarity=sum(similarities) / len(similarities) if similarities else 0.0,
            avg_containment=sum(containments) / len(containments) if containments else 0.0,
            tables_count=len(tables),
            columns_count=len(columns)
        )
    
    def generate_confidence_chart(self) -> str:
        """
        Generate relationship confidence distribution chart.
        
        Returns:
            Path to saved chart
        """
        print("[VIZ] Generating confidence chart...")
        
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('Relationship Detection Analysis', fontsize=16, fontweight='bold')
        
        # 1. Confidence Distribution by Class
        ax1 = axes[0, 0]
        df = pd.DataFrame(self.relationships)
        
        for cls in df['relationship_class'].unique():
            subset = df[df['relationship_class'] == cls]
            ax1.hist(subset['confidence_score'], alpha=0.6, label=cls, bins=30)
        
        ax1.set_xlabel('Confidence Score')
        ax1.set_ylabel('Frequency')
        ax1.set_title('Confidence Score Distribution by Relationship Class')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 2. Relationship Class Pie Chart
        ax2 = axes[0, 1]
        class_counts = df['relationship_class'].value_counts()
        colors = {'TRUE_FK': '#2ecc71', 'SEMANTICALLY_RELATED': '#3498db', 
                  'POSSIBLE_REFERENCE': '#f39c12', 'SHARED_ENTITY_DOMAIN': '#9b59b6'}
        
        wedges, texts, autotexts = ax2.pie(
            class_counts.values,
            labels=class_counts.index,
            autopct='%1.1f%%',
            colors=[colors.get(cls, '#95a5a6') for cls in class_counts.index],
            startangle=90
        )
        ax2.set_title(f'Relationship Distribution ({len(self.relationships)} total)')
        
        # 3. Semantic Similarity vs Containment Scatter
        ax3 = axes[1, 0]
        for cls in df['relationship_class'].unique():
            subset = df[df['relationship_class'] == cls]
            ax3.scatter(
                subset['semantic_similarity'],
                subset['containment_ratio'],
                alpha=0.5,
                label=cls,
                s=50
            )
        
        ax3.set_xlabel('Semantic Similarity')
        ax3.set_ylabel('Containment Ratio')
        ax3.set_title('Semantic Similarity vs Containment')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        ax3.set_xlim(0, 1)
        ax3.set_ylim(0, 1.1)
        
        # 4. Top 10 Most Confident Relationships
        ax4 = axes[1, 1]
        top_rels = df.nlargest(10, 'confidence_score')
        y_pos = range(len(top_rels))
        labels = [f"{r['fk_table']}.{r['fk_column']} → {r['pk_table']}.{r['pk_column']}"[:40] 
                  for _, r in top_rels.iterrows()]
        
        bars = ax4.barh(y_pos, top_rels['confidence_score'])
        for i, bar in enumerate(bars):
            cls = top_rels.iloc[i]['relationship_class']
            bar.set_color(colors.get(cls, '#95a5a6'))
        
        ax4.set_yticks(y_pos)
        ax4.set_yticklabels(labels, fontsize=8)
        ax4.set_xlabel('Confidence Score')
        ax4.set_title('Top 10 Highest Confidence Relationships')
        ax4.grid(True, alpha=0.3, axis='x')
        
        plt.tight_layout()
        output_path = self.output_dir / "confidence_analysis.png"
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"[VIZ] Saved: {output_path}")
        return str(output_path)
    
    def generate_erd_diagram(self, max_tables: int = 20) -> str:
        """
        Generate Entity-Relationship Diagram.
        
        Args:
            max_tables: Maximum number of tables to include
        
        Returns:
            Path to saved ERD
        """
        print("[VIZ] Generating ERD diagram...")
        
        # Build graph
        G = nx.DiGraph()
        
        # Add only TRUE_FK relationships for ERD
        true_fks = [r for r in self.relationships if r["relationship_class"] == "TRUE_FK"]
        
        # Count relationships per table to prioritize
        table_rel_count = Counter()
        for rel in true_fks:
            table_rel_count[rel["fk_table"]] += 1
            table_rel_count[rel["pk_table"]] += 1
        
        # Select top tables
        top_tables = set([t for t, _ in table_rel_count.most_common(max_tables)])
        
        # Add edges
        for rel in true_fks:
            if rel["fk_table"] in top_tables and rel["pk_table"] in top_tables:
                G.add_edge(
                    rel["pk_table"],
                    rel["fk_table"],
                    label=f"{rel['fk_column']}",
                    confidence=rel["confidence_score"]
                )
        
        if len(G.nodes) == 0:
            print("[VIZ] No TRUE_FK relationships found for ERD")
            return ""
        
        # Draw
        fig, ax = plt.subplots(figsize=(20, 16))
        
        # Layout
        pos = nx.spring_layout(G, k=2, iterations=50, seed=42)
        
        # Draw nodes (tables)
        nx.draw_networkx_nodes(
            G, pos,
            node_color='#3498db',
            node_size=3000,
            alpha=0.9,
            ax=ax
        )
        
        # Draw edges (relationships)
        edges = G.edges()
        weights = [G[u][v]['confidence'] for u, v in edges]
        
        nx.draw_networkx_edges(
            G, pos,
            edge_color='#2c3e50',
            width=[w * 3 for w in weights],
            alpha=0.6,
            arrows=True,
            arrowsize=20,
            arrowstyle='->',
            connectionstyle='arc3,rad=0.1',
            ax=ax
        )
        
        # Draw labels
        nx.draw_networkx_labels(
            G, pos,
            font_size=8,
            font_weight='bold',
            font_color='white',
            ax=ax
        )
        
        # Draw edge labels
        edge_labels = nx.get_edge_attributes(G, 'label')
        nx.draw_networkx_edge_labels(
            G, pos,
            edge_labels,
            font_size=6,
            font_color='#e74c3c',
            ax=ax
        )
        
        ax.set_title(
            f'Entity-Relationship Diagram (Top {len(G.nodes)} Tables, {len(G.edges)} TRUE_FK)',
            fontsize=16,
            fontweight='bold',
            pad=20
        )
        ax.axis('off')
        
        plt.tight_layout()
        output_path = self.output_dir / "erd_diagram.png"
        plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        
        print(f"[VIZ] Saved: {output_path}")
        return str(output_path)
    
    def generate_knowledge_graph(self, min_confidence: float = 0.6) -> str:
        """
        Generate knowledge graph with all relationship types.
        
        Args:
            min_confidence: Minimum confidence threshold
        
        Returns:
            Path to saved graph
        """
        print("[VIZ] Generating knowledge graph...")
        
        # Build graph
        G = nx.Graph()
        
        # Filter by confidence
        filtered_rels = [r for r in self.relationships if r["confidence_score"] >= min_confidence]
        
        # Add edges with attributes
        for rel in filtered_rels[:500]:  # Limit for visualization
            G.add_edge(
                f"{rel['fk_table']}.{rel['fk_column']}",
                f"{rel['pk_table']}.{rel['pk_column']}",
                relationship_class=rel["relationship_class"],
                confidence=rel["confidence_score"],
                similarity=rel["semantic_similarity"]
            )
        
        if len(G.nodes) == 0:
            print(f"[VIZ] No relationships above confidence {min_confidence}")
            return ""
        
        # Draw
        fig, ax = plt.subplots(figsize=(24, 20))
        
        # Layout
        pos = nx.spring_layout(G, k=1, iterations=50, seed=42)
        
        # Node colors by relationship type
        node_colors = []
        for node in G.nodes():
            # Count relationship types
            types = [G[node][neighbor]['relationship_class'] for neighbor in G.neighbors(node)]
            if 'TRUE_FK' in types:
                node_colors.append('#2ecc71')
            elif 'SEMANTICALLY_RELATED' in types:
                node_colors.append('#3498db')
            else:
                node_colors.append('#95a5a6')
        
        # Draw nodes
        nx.draw_networkx_nodes(
            G, pos,
            node_color=node_colors,
            node_size=500,
            alpha=0.8,
            ax=ax
        )
        
        # Draw edges colored by relationship type
        color_map = {
            'TRUE_FK': '#2ecc71',
            'SEMANTICALLY_RELATED': '#3498db',
            'POSSIBLE_REFERENCE': '#f39c12',
            'SHARED_ENTITY_DOMAIN': '#9b59b6'
        }
        
        for rel_type, color in color_map.items():
            edges = [(u, v) for u, v, d in G.edges(data=True) if d['relationship_class'] == rel_type]
            if edges:
                nx.draw_networkx_edges(
                    G, pos,
                    edgelist=edges,
                    edge_color=color,
                    width=2,
                    alpha=0.5,
                    ax=ax
                )
        
        # Draw labels
        labels = {node: node.split('.')[-1][:15] for node in G.nodes()}
        nx.draw_networkx_labels(
            G, pos,
            labels,
            font_size=6,
            ax=ax
        )
        
        # Legend
        legend_elements = [
            mpatches.Patch(color='#2ecc71', label='TRUE_FK'),
            mpatches.Patch(color='#3498db', label='SEMANTICALLY_RELATED'),
            mpatches.Patch(color='#f39c12', label='POSSIBLE_REFERENCE'),
            mpatches.Patch(color='#9b59b6', label='SHARED_ENTITY_DOMAIN')
        ]
        ax.legend(handles=legend_elements, loc='upper right', fontsize=10)
        
        ax.set_title(
            f'Knowledge Graph (Confidence ≥ {min_confidence}, {len(G.nodes)} nodes, {len(G.edges)} edges)',
            fontsize=16,
            fontweight='bold',
            pad=20
        )
        ax.axis('off')
        
        plt.tight_layout()
        output_path = self.output_dir / "knowledge_graph.png"
        plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        
        print(f"[VIZ] Saved: {output_path}")
        return str(output_path)
    
    def generate_quality_dashboard(self) -> str:
        """
        Generate comprehensive quality metrics dashboard.
        
        Returns:
            Path to saved dashboard
        """
        print("[VIZ] Generating quality dashboard...")
        
        fig = plt.figure(figsize=(20, 12))
        gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)
        
        # Title
        fig.suptitle('Data Quality & Relationship Detection Dashboard', 
                     fontsize=18, fontweight='bold', y=0.98)
        
        # 1. Key Metrics (top left, large)
        ax1 = fig.add_subplot(gs[0, :2])
        ax1.axis('off')
        
        metrics_text = f"""
        PIPELINE SUMMARY
        ═══════════════════════════════════════════════════════
        Total Relationships Detected: {self.stats.total_relationships:,}
        TRUE Foreign Keys: {self.stats.true_fk_count:,}
        Semantically Related: {self.stats.semantically_related_count:,}
        Possible References: {self.stats.possible_reference_count:,}
        Shared Entity Domains: {self.stats.shared_entity_count:,}
        
        Tables Analyzed: {self.stats.tables_count}
        Columns Analyzed: {self.stats.columns_count}
        
        QUALITY METRICS
        ═══════════════════════════════════════════════════════
        Avg Confidence Score: {self.stats.avg_confidence:.3f}
        Avg Semantic Similarity: {self.stats.avg_semantic_similarity:.3f}
        Avg Containment Ratio: {self.stats.avg_containment:.3f}
        
        Generation Time: {self.metadata.get('generation_timestamp', 'N/A')}
        """
        
        ax1.text(0.05, 0.5, metrics_text, fontsize=12, 
                family='monospace', verticalalignment='center',
                bbox=dict(boxstyle='round', facecolor='#ecf0f1', alpha=0.8))
        
        # 2. Confidence Score Box Plot by Class
        ax2 = fig.add_subplot(gs[0, 2])
        df = pd.DataFrame(self.relationships)
        
        df.boxplot(column='confidence_score', by='relationship_class', ax=ax2, patch_artist=True)
        ax2.set_title('Confidence by Class')
        ax2.set_xlabel('')
        ax2.set_ylabel('Confidence Score')
        plt.sca(ax2)
        plt.xticks(rotation=45, ha='right', fontsize=8)
        
        # 3. Semantic Similarity Distribution
        ax3 = fig.add_subplot(gs[1, 0])
        ax3.hist(df['semantic_similarity'], bins=30, color='#3498db', alpha=0.7, edgecolor='black')
        ax3.axvline(self.stats.avg_semantic_similarity, color='red', linestyle='--', 
                   label=f'Avg: {self.stats.avg_semantic_similarity:.2f}')
        ax3.set_xlabel('Semantic Similarity')
        ax3.set_ylabel('Frequency')
        ax3.set_title('Semantic Similarity Distribution')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        # 4. Containment Ratio Distribution
        ax4 = fig.add_subplot(gs[1, 1])
        ax4.hist(df['containment_ratio'], bins=30, color='#2ecc71', alpha=0.7, edgecolor='black')
        ax4.axvline(self.stats.avg_containment, color='red', linestyle='--',
                   label=f'Avg: {self.stats.avg_containment:.2f}')
        ax4.set_xlabel('Containment Ratio')
        ax4.set_ylabel('Frequency')
        ax4.set_title('Containment Ratio Distribution')
        ax4.legend()
        ax4.grid(True, alpha=0.3)
        
        # 5. Confidence Score Distribution
        ax5 = fig.add_subplot(gs[1, 2])
        ax5.hist(df['confidence_score'], bins=30, color='#e74c3c', alpha=0.7, edgecolor='black')
        ax5.axvline(self.stats.avg_confidence, color='blue', linestyle='--',
                   label=f'Avg: {self.stats.avg_confidence:.2f}')
        ax5.set_xlabel('Confidence Score')
        ax5.set_ylabel('Frequency')
        ax5.set_title('Confidence Score Distribution')
        ax5.legend()
        ax5.grid(True, alpha=0.3)
        
        # 6. Top Tables by Relationship Count
        ax6 = fig.add_subplot(gs[2, 0])
        table_counts = Counter()
        for rel in self.relationships:
            table_counts[rel['fk_table']] += 1
            table_counts[rel['pk_table']] += 1
        
        top_tables = table_counts.most_common(10)
        tables, counts = zip(*top_tables) if top_tables else ([], [])
        
        y_pos = range(len(tables))
        ax6.barh(y_pos, counts, color='#9b59b6')
        ax6.set_yticks(y_pos)
        ax6.set_yticklabels([t[:25] for t in tables], fontsize=8)
        ax6.set_xlabel('Relationship Count')
        ax6.set_title('Top 10 Most Connected Tables')
        ax6.grid(True, alpha=0.3, axis='x')
        
        # 7. Relationship Class Breakdown
        ax7 = fig.add_subplot(gs[2, 1])
        class_counts = df['relationship_class'].value_counts()
        colors_list = ['#2ecc71', '#3498db', '#f39c12', '#9b59b6']
        
        ax7.bar(range(len(class_counts)), class_counts.values, 
               color=colors_list[:len(class_counts)])
        ax7.set_xticks(range(len(class_counts)))
        ax7.set_xticklabels(class_counts.index, rotation=45, ha='right', fontsize=8)
        ax7.set_ylabel('Count')
        ax7.set_title('Relationship Class Distribution')
        ax7.grid(True, alpha=0.3, axis='y')
        
        # 8. Quality Score (composite metric)
        ax8 = fig.add_subplot(gs[2, 2])
        ax8.axis('off')
        
        # Calculate quality score (weighted average)
        quality_score = (
            0.5 * self.stats.avg_confidence +
            0.3 * self.stats.avg_semantic_similarity +
            0.2 * (self.stats.true_fk_count / max(self.stats.total_relationships, 1))
        )
        
        # Quality grade
        if quality_score >= 0.8:
            grade, color = 'A', '#2ecc71'
        elif quality_score >= 0.6:
            grade, color = 'B', '#3498db'
        elif quality_score >= 0.4:
            grade, color = 'C', '#f39c12'
        else:
            grade, color = 'D', '#e74c3c'
        
        quality_text = f"""
        OVERALL QUALITY SCORE
        
        {quality_score:.2f} / 1.00
        
        Grade: {grade}
        """
        
        ax8.text(0.5, 0.5, quality_text, fontsize=20, fontweight='bold',
                ha='center', va='center',
                bbox=dict(boxstyle='round', facecolor=color, alpha=0.3, 
                         edgecolor=color, linewidth=3))
        
        plt.tight_layout()
        output_path = self.output_dir / "quality_dashboard.png"
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"[VIZ] Saved: {output_path}")
        return str(output_path)
    
    def generate_full_report(self) -> Dict[str, str]:
        """
        Generate all visualizations at once.
        
        Returns:
            Dictionary mapping visualization name to file path
        """
        print("\n" + "="*60)
        print("GENERATING FULL VISUALIZATION REPORT")
        print("="*60 + "\n")
        
        results = {}
        
        try:
            results['confidence_chart'] = self.generate_confidence_chart()
        except Exception as e:
            print(f"[ERROR] Confidence chart failed: {e}")
        
        try:
            results['erd_diagram'] = self.generate_erd_diagram()
        except Exception as e:
            print(f"[ERROR] ERD diagram failed: {e}")
        
        try:
            results['knowledge_graph'] = self.generate_knowledge_graph()
        except Exception as e:
            print(f"[ERROR] Knowledge graph failed: {e}")
        
        try:
            results['quality_dashboard'] = self.generate_quality_dashboard()
        except Exception as e:
            print(f"[ERROR] Quality dashboard failed: {e}")
        
        print("\n" + "="*60)
        print("VISUALIZATION REPORT COMPLETE")
        print("="*60)
        print(f"\nGenerated {len([v for v in results.values() if v])} visualizations")
        print(f"Output directory: {self.output_dir}\n")
        
        return results


def interactive_visualization_menu(relationships_file: str):
    """
    Interactive CLI menu for visualization selection.
    
    Args:
        relationships_file: Path to relationships.json
    """
    engine = VisualizationEngine(relationships_file)
    
    while True:
        print("\n" + "="*60)
        print("VISUALIZATION ENGINE - INTERACTIVE MENU")
        print("="*60)
        print(f"\nDataset: {engine.stats.total_relationships:,} relationships")
        print(f"TRUE_FK: {engine.stats.true_fk_count:,} | Tables: {engine.stats.tables_count}")
        print("\n" + "-"*60)
        print("Select Visualization:")
        print("-"*60)
        print("1. Relationship Confidence Chart")
        print("2. ERD Diagram (Entity-Relationship)")
        print("3. Knowledge Graph")
        print("4. Quality Dashboard")
        print("5. Full Report (All Visualizations)")
        print("6. Exit")
        print("-"*60)
        
        choice = input("\nEnter choice (1-6): ").strip()
        
        if choice == '1':
            print("\n[GENERATING] Confidence Chart...")
            path = engine.generate_confidence_chart()
            print(f"\n✓ Saved: {path}")
            input("\nPress Enter to continue...")
        
        elif choice == '2':
            max_tables = input("Max tables to show (default=20): ").strip()
            max_tables = int(max_tables) if max_tables.isdigit() else 20
            print(f"\n[GENERATING] ERD Diagram (top {max_tables} tables)...")
            path = engine.generate_erd_diagram(max_tables)
            if path:
                print(f"\n✓ Saved: {path}")
            input("\nPress Enter to continue...")
        
        elif choice == '3':
            min_conf = input("Min confidence threshold (default=0.6): ").strip()
            min_conf = float(min_conf) if min_conf else 0.6
            print(f"\n[GENERATING] Knowledge Graph (confidence ≥ {min_conf})...")
            path = engine.generate_knowledge_graph(min_conf)
            if path:
                print(f"\n✓ Saved: {path}")
            input("\nPress Enter to continue...")
        
        elif choice == '4':
            print("\n[GENERATING] Quality Dashboard...")
            path = engine.generate_quality_dashboard()
            print(f"\n✓ Saved: {path}")
            input("\nPress Enter to continue...")
        
        elif choice == '5':
            print("\n[GENERATING] Full Report...")
            results = engine.generate_full_report()
            print("\n✓ All visualizations generated!")
            for name, path in results.items():
                if path:
                    print(f"  - {name}: {path}")
            input("\nPress Enter to continue...")
        
        elif choice == '6':
            print("\n✓ Exiting visualization engine...")
            break
        
        else:
            print("\n✗ Invalid choice. Please enter 1-6.")
            input("Press Enter to continue...")
