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
    def enrich_relationships(output_base: str = "output", max_workers: int = 5) -> str:
        """Generate LLM descriptions and detect semantic relationships."""
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
