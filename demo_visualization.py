"""
Interactive CLI for Visualization Engine

Provides a menu-driven interface for generating visualizations:
1. Relationship Confidence Chart
2. ERD Diagram
3. Knowledge Graph
4. Quality Dashboard
5. Full Report Dashboard
6. Exit
"""

import os
import sys
import logging
import webbrowser
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from visualization.engine import VisualizationEngine
from visualization.charts import RelationshipCharts
from visualization.erd import ERDGenerator
from visualization.knowledge_graph import KnowledgeGraphGenerator
from visualization.quality_dashboard import QualityDashboard

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

log = logging.getLogger(__name__)


def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header():
    """Print the application header."""
    clear_screen()
    print("=" * 80)
    print("🎨 SEMANTIC PROFILING VISUALIZATION ENGINE".center(80))
    print("=" * 80)
    print()


def print_menu():
    """Print the main menu."""
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                          SELECT VISUALIZATION                                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  1. 📊 Relationship Confidence Chart                                         ║
║     Interactive scatter plot: confidence vs semantic similarity              ║
║                                                                              ║
║  2. 🗺️  ERD Diagram                                                          ║
║     Entity Relationship Diagram with TRUE_FK connections                     ║
║                                                                              ║
║  3. 🕸️  Knowledge Graph                                                      ║
║     Interactive network visualization of all relationships                   ║
║                                                                              ║
║  4. 📋 Quality Dashboard                                                     ║
║     Comprehensive quality metrics and distribution analysis                  ║
║                                                                              ║
║  5. 📑 Full Report Dashboard                                                 ║
║     Complete report with links to all visualizations                         ║
║                                                                              ║
║  6. 🚀 Generate All Visualizations                                           ║
║     Create all visualizations at once                                        ║
║                                                                              ║
║  7. ❌ Exit                                                                   ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")


def get_choice():
    """Get user choice."""
    while True:
        try:
            choice = input("Enter your choice (1-7): ").strip()
            if choice in ['1', '2', '3', '4', '5', '6', '7']:
                return choice
            else:
                print("❌ Invalid choice. Please enter a number between 1 and 7.")
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            sys.exit(0)


def open_file_in_browser(file_path):
    """Open a file in the default web browser."""
    try:
        abs_path = Path(file_path).absolute()
        if abs_path.exists():
            webbrowser.open(f'file://{abs_path}')
            print(f"\n✓ Opened in browser: {abs_path}")
        else:
            print(f"\n❌ File not found: {abs_path}")
    except Exception as e:
        print(f"\n❌ Failed to open browser: {e}")
        print(f"   Please manually open: {file_path}")


def generate_confidence_chart(engine):
    """Generate relationship confidence chart."""
    print("\n" + "=" * 80)
    print("📊 GENERATING RELATIONSHIP CONFIDENCE CHART")
    print("=" * 80)
    
    charts = RelationshipCharts(engine)
    charts.generate_confidence_chart()
    
    output_file = engine.output_dir / "confidence_chart.html"
    
    print("\n✓ Chart generated successfully!")
    print(f"  Location: {output_file}")
    
    if input("\nOpen in browser? (y/n): ").strip().lower() == 'y':
        open_file_in_browser(output_file)


def generate_erd(engine):
    """Generate ERD diagram."""
    print("\n" + "=" * 80)
    print("🗺️  GENERATING ERD DIAGRAM")
    print("=" * 80)
    
    erd = ERDGenerator(engine)
    erd.generate_erd()
    
    output_file = engine.output_dir / "erd_diagram.html"
    
    print("\n✓ ERD diagram generated successfully!")
    print(f"  Location: {output_file}")
    
    if input("\nOpen in browser? (y/n): ").strip().lower() == 'y':
        open_file_in_browser(output_file)


def generate_knowledge_graph(engine):
    """Generate knowledge graph."""
    print("\n" + "=" * 80)
    print("🕸️  GENERATING KNOWLEDGE GRAPH")
    print("=" * 80)
    
    kg = KnowledgeGraphGenerator(engine)
    kg.generate_graph()
    
    output_file = engine.output_dir / "knowledge_graph.html"
    
    print("\n✓ Knowledge graph generated successfully!")
    print(f"  Location: {output_file}")
    
    if input("\nOpen in browser? (y/n): ").strip().lower() == 'y':
        open_file_in_browser(output_file)


def generate_quality_dashboard(engine):
    """Generate quality dashboard."""
    print("\n" + "=" * 80)
    print("📋 GENERATING QUALITY DASHBOARD")
    print("=" * 80)
    
    quality = QualityDashboard(engine)
    quality.generate_dashboard()
    
    output_file = engine.output_dir / "quality_dashboard.html"
    
    print("\n✓ Quality dashboard generated successfully!")
    print(f"  Location: {output_file}")
    
    if input("\nOpen in browser? (y/n): ").strip().lower() == 'y':
        open_file_in_browser(output_file)


def generate_full_report(engine):
    """Generate full report dashboard."""
    print("\n" + "=" * 80)
    print("📑 GENERATING FULL REPORT DASHBOARD")
    print("=" * 80)
    
    engine.generate_full_report()
    
    output_file = engine.output_dir / "full_report.html"
    
    print("\n✓ Full report generated successfully!")
    print(f"  Location: {output_file}")
    
    if input("\nOpen in browser? (y/n): ").strip().lower() == 'y':
        open_file_in_browser(output_file)


def generate_all(engine):
    """Generate all visualizations."""
    engine.generate_all()
    
    output_file = engine.output_dir / "full_report.html"
    
    print("\n✓ All visualizations generated successfully!")
    
    if input("\nOpen full report in browser? (y/n): ").strip().lower() == 'y':
        open_file_in_browser(output_file)


def main():
    """Main application loop."""
    # Initialize engine
    engine = VisualizationEngine()
    
    # Show header
    print_header()
    
    # Load relationships.json
    print("Loading relationships.json...")
    if not engine.load_relationships():
        print("\n❌ ERROR: Failed to load relationships.json")
        print("\nPlease ensure relationships.json exists at:")
        print(f"  {engine.relationships_path.absolute()}")
        print("\nRun the relationship detection pipeline first:")
        print("  python demo_relationship_detection.py")
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    print("\n✓ Relationships loaded successfully!")
    
    # Show stats
    stats = engine.get_statistics()
    metadata = engine.get_metadata()
    
    print(f"\n📊 Dataset Summary:")
    print(f"   Total Relationships: {stats['total_relationships']:,}")
    print(f"   TRUE_FK Count: {metadata.get('true_fk_count', 0):,}")
    print(f"   Relationship Types: {len(stats['type_counts'])}")
    print(f"   Generated: {metadata.get('generation_timestamp', 'N/A')}")
    
    input("\nPress Enter to continue...")
    
    # Main loop
    while True:
        print_header()
        
        print(f"📊 Dataset: {stats['total_relationships']:,} relationships | " +
              f"TRUE_FK: {metadata.get('true_fk_count', 0):,}")
        
        print_menu()
        
        choice = get_choice()
        
        try:
            if choice == '1':
                generate_confidence_chart(engine)
            elif choice == '2':
                generate_erd(engine)
            elif choice == '3':
                generate_knowledge_graph(engine)
            elif choice == '4':
                generate_quality_dashboard(engine)
            elif choice == '5':
                generate_full_report(engine)
            elif choice == '6':
                generate_all(engine)
            elif choice == '7':
                print("\n" + "=" * 80)
                print("👋 Thank you for using the Visualization Engine!")
                print("=" * 80)
                print(f"\nAll visualizations saved to:")
                print(f"  {engine.output_dir.absolute()}")
                print()
                sys.exit(0)
            
            input("\nPress Enter to continue...")
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            input("\nPress Enter to continue...")


if __name__ == "__main__":
    main()
