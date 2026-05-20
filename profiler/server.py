"""MCP server for the Agentic Data Profiler."""

from __future__ import annotations

import argparse
import json
from typing import Any

from fastmcp import FastMCP

from profiler import services


def create_mcp_server() -> FastMCP:
    """Create the profiler MCP server with all v1 tools registered."""
    mcp = FastMCP("agentic-data-profiler")

    @mcp.tool
    def list_supported_files(path: str = ".") -> str:
        """List supported data files under a file or directory path."""
        return _json(services.list_supported_files(path))

    @mcp.tool
    def profile_file(path: str, sample_size: int = 1000, output_base: str = "output") -> str:
        """Profile one file and write canonical/profile JSON artifacts."""
        return _json(services.profile_file(path, sample_size, output_base))

    @mcp.tool
    def profile_directory(
        path: str,
        sample_size: int = 1000,
        output_base: str = "output",
        max_workers: int = 4,
    ) -> str:
        """Profile every supported file under a directory."""
        return _json(services.profile_directory(path, sample_size, output_base, max_workers))

    @mcp.tool
    def detect_relationships(output_base: str = "output") -> str:
        """Detect semantic relationships from existing descriptions (Stage 4 only)."""
        return _json(services.detect_relationships(output_base))

    @mcp.tool
    def enrich_descriptions(output_base: str = "output", max_workers: int = 5) -> str:
        """Generate LLM semantic descriptions for columns (enrichment only, NO relationship detection)."""
        return _json(services.enrich_descriptions(output_base, max_workers))

    @mcp.tool
    def enrich_relationships(output_base: str = "output", max_workers: int = 5) -> str:
        """DEPRECATED: Use enrich_descriptions() + detect_relationships() separately. Kept for compatibility."""
        return _json(services.enrich_relationships(output_base, max_workers))

    @mcp.tool
    def enrich_low_cardinality(
        output_base: str = "output",
        batch_size: int = 10,
        max_workers: int = 5,
        provider: str = "nvidia",
        model: str | None = None,
        min_confidence: float = 0.6,
    ) -> str:
        """Enrich low-cardinality columns with semantic intelligence using LLM."""
        return _json(
            services.enrich_low_cardinality(
                output_base, batch_size, max_workers, provider, model, min_confidence
            )
        )

    @mcp.tool
    def get_quality_summary(
        table_name: str | None = None,
        profile_path: str | None = None,
    ) -> str:
        """Summarize data-quality metrics from generated profile JSON files."""
        return _json(services.get_quality_summary(table_name, profile_path))

    @mcp.tool
    def get_table_relationships(
        table_name: str | None = None,
        relationship_class: str | None = None,
    ) -> str:
        """Return relationships filtered by table and/or relationship class."""
        return _json(services.get_table_relationships(table_name, relationship_class))

    @mcp.tool
    def generate_erd(
        relationships_path: str = "output/relationships/relationships.json",
        output_dir: str = "output/visualizations",
    ) -> str:
        """Generate an interactive ERD HTML file from relationships.json."""
        return _json(services.generate_erd(relationships_path, output_dir))

    @mcp.tool
    def generate_er_visualizations(
        relationships_path: str = "output/relationships/relationships.json",
        output_base: str = "output",
        mode: str = "full",
        min_confidence: float = 0.5,
        top_k: int | None = None,
    ) -> str:
        """Generate ER visualizations: DBML, draw.io, Mermaid, HTML, charts, and graph exports.
        
        Fully automatic ER diagram generation pipeline.
        
        Args:
            relationships_path: Path to relationships.json (default: output/relationships/relationships.json)
            output_base: Base output directory (default: output)
            mode: Generation mode (default: full)
                - "full": Generate all formats
                - "dbml": DBDiagram DBML schema only
                - "drawio": Draw.io XML files only
                - "mermaid": Mermaid ERD only
                - "html": Standalone HTML preview only
                - "charts": PNG charts only
                - "graph": Graph JSON only
            min_confidence: Minimum relationship confidence (default: 0.5)
            top_k: Max relationships to render (default: None = auto-computed)
                Auto-scaling: < 50 tables → 50, 50-200 → 100, > 200 → 200, > 10k rels → 500
        
        User can simply say "Generate DB diagram" without any parameters.
        """
        return _json(
            services.generate_er_visualizations(
                relationships_path=relationships_path,
                output_base=output_base,
                mode=mode,
                min_confidence=min_confidence,
                top_k=top_k,
            )
        )

    @mcp.tool
    def build_diagram_state(
        output_base: str = "output",
        min_confidence: float = 0.5,
        top_k: int | None = None,
        relationship_classes: list[str] | None = None,
    ) -> str:
        """Build interactive diagram state JSON from existing outputs."""
        return _json(
            services.build_diagram_state(
                output_base=output_base,
                min_confidence=min_confidence,
                top_k=top_k,
                relationship_classes=relationship_classes,
            )
        )

    @mcp.tool
    def get_table_detail(
        table_id: str,
        output_base: str = "output",
    ) -> str:
        """Return table detail payload for the diagram explorer."""
        return _json(services.get_table_detail(table_id, output_base))

    @mcp.tool
    def get_column_insights(
        column_id: str,
        output_base: str = "output",
    ) -> str:
        """Return column-level insight payload for hover cards."""
        return _json(services.get_column_insight(column_id, output_base))

    @mcp.tool
    def get_relationship_details(
        edge_id: str,
        output_base: str = "output",
    ) -> str:
        """Return relationship detail payload for edge selection."""
        return _json(services.get_relationship_detail(edge_id, output_base))

    @mcp.tool
    def export_dbml(
        output_base: str = "output",
        min_confidence: float = 0.5,
        top_k: int | None = None,
    ) -> str:
        """Export DBML schema from TRUE_FK relationships."""
        return _json(services.export_dbml(output_base, min_confidence, top_k))

    @mcp.tool
    def display_dbml(
        dbml_path: str | None = None,
        output_base: str = "output",
    ) -> str:
        """Display existing DBML schema in embedded viewer WITHOUT regeneration.
        
        Loads existing schema.dbml file and prepares it for inline chat rendering.
        Does NOT regenerate the DBML - just loads and displays what already exists.
        
        Args:
            dbml_path: Optional explicit DBML file path. If None, auto-detects from:
                - output/erd/schema.dbml
                - output/visualizations/schema.dbml
            output_base: Base output directory (default: output)
            
        User can simply say "Display dbml" or "Show schema" without parameters.
        
        Example:
            User: "Display dbml"
            Agent: display_dbml()  # Auto-loads existing schema.dbml
            Result: Embedded DBML viewer renders inline (no file path output)
        """
        return _json(services.display_dbml(dbml_path, output_base))

    @mcp.tool
    def dbml_web_renderer(
        source_type: str = "text",
        dbml_text: str | None = None,
        file_path: str | None = None,
        viewer_mode: str = "interactive",
        layout: str = "auto",
        options: dict[str, Any] | None = None,
    ) -> str:
        """Render DBML schemas into embeddable and interactive web ER views.

        Supports DBML from raw text, file path, or URL.
        Returns parsed schema metadata, relationships, HTML embed payload,
        interactive graph model, and ReactFlow component scaffold.
        """
        return _json(
            services.dbml_web_renderer(
                source_type=source_type,
                dbml_text=dbml_text,
                file_path=file_path,
                viewer_mode=viewer_mode,
                layout=layout,
                options=options,
            )
        )

    return mcp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Agentic Data Profiler MCP server.")
    parser.add_argument("--transport", default="sse", choices=["sse"], help="MCP transport mode.")
    parser.add_argument("--host", default="127.0.0.1", help="Host for the SSE server.")
    parser.add_argument("--port", default=8080, type=int, help="Port for the SSE server.")
    args = parser.parse_args(argv)

    mcp = create_mcp_server()
    try:
        mcp.run(transport=args.transport, host=args.host, port=args.port)
    except TypeError:
        mcp.run(args.transport, host=args.host, port=args.port)
    return 0


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)
