"""Command-line entrypoint for the profiler MCP server."""

from __future__ import annotations

import sys

from profiler.server import main


if __name__ == "__main__":
    sys.exit(main())
