"""Interactive CLI for the ER Visualization Engine."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from profiler.erve import ERVEConfig, ERVEEngine


MENU = """
============================================================
ER VISUALIZATION ENGINE (ERVE)
============================================================
1 -> Relationship Chart
2 -> dbdiagram ERD
3 -> draw.io ERD
4 -> Mermaid ERD
5 -> Interactive HTML
6 -> Graph Export
7 -> Full Export
8 -> Exit
------------------------------------------------------------
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate ERVE artifacts from relationship.json.")
    parser.add_argument(
        "--relationships-path",
        default="output/relationships/relationships.json",
        help="Path to relationship.json/relationships.json.",
    )
    parser.add_argument("--output-base", default="output", help="Output base directory.")
    parser.add_argument("--min-confidence", type=float, default=0.5, help="Confidence pruning threshold.")
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Max relationships to render. Auto-computed if not specified: < 50 tables → 50, 50-200 → 100, > 200 → 200, > 10k rels → 500.",
    )
    parser.add_argument("--menu", action="store_true", help="Open the interactive menu.")
    parser.add_argument("--charts", action="store_true", help="Generate relationship charts.")
    parser.add_argument("--dbml", action="store_true", help="Generate DBML.")
    parser.add_argument("--drawio", action="store_true", help="Generate draw.io files.")
    parser.add_argument("--mermaid", action="store_true", help="Generate Mermaid ERD.")
    parser.add_argument("--html", action="store_true", help="Generate interactive HTML ERD.")
    parser.add_argument("--graph", action="store_true", help="Generate graph JSON and graph HTML.")
    parser.add_argument("--full", action="store_true", help="Generate all ERVE artifacts.")
    args = parser.parse_args(argv)

    config = ERVEConfig(
        relationships_path=args.relationships_path,
        output_base=args.output_base,
        min_confidence=args.min_confidence,
        top_k=args.top_k,
    )
    engine = ERVEEngine(config=config)

    selected_modes = []
    for flag, mode in [
        (args.charts, "charts"),
        (args.dbml, "dbml"),
        (args.drawio, "drawio"),
        (args.mermaid, "mermaid"),
        (args.html, "html"),
        (args.graph, "graph"),
        (args.full, "full"),
    ]:
        if flag:
            selected_modes.append(mode)

    if args.menu or not selected_modes:
        return run_menu(engine)

    payloads = [_run_mode_direct(engine, mode) for mode in selected_modes]
    print(json.dumps(payloads[0] if len(payloads) == 1 else payloads, indent=2))
    return 0


def run_menu(engine: ERVEEngine) -> int:
    """Open the interactive ERVE menu and dispatch generated scripts."""

    script_result = engine.ensure_scripts()
    scripts = script_result["outputs"]

    while True:
        engine.load()
        metrics = engine.graph_metrics()
        print(MENU)
        print(
            f"Dataset: {metrics['raw_relationship_count']:,} raw relationships | "
            f"{metrics['relationship_count']:,} after pruning | "
            f"{metrics['table_count']:,} tables"
        )
        choice = input("\nEnter choice (1-8): ").strip()
        mode = {
            "1": "charts",
            "2": "dbml",
            "3": "drawio",
            "4": "mermaid",
            "5": "html",
            "6": "graph",
            "7": "full",
        }.get(choice)

        if choice == "8":
            print("\nExiting ERVE.")
            return 0
        if mode is None:
            print("\nInvalid choice. Please enter 1-8.")
            continue

        script_key = {
            "charts": "generate_charts",
            "dbml": "generate_dbml",
            "drawio": "generate_drawio",
            "mermaid": "generate_mermaid",
            "html": "generate_html",
            "graph": "generate_graph",
            "full": "generate_all",
        }[mode]
        script = Path(scripts[script_key])
        print(f"\n[ERVE] Running {script.name}...")
        result = _run_generated_script(engine, script)
        if result.returncode == 0:
            print(result.stdout.strip())
        else:
            print(result.stdout.strip())
            print(result.stderr.strip())
        input("\nPress Enter to continue...")


def _run_mode_direct(engine: ERVEEngine, mode: str) -> dict[str, Any]:
    if mode == "full":
        return engine.generate_full_export()
    return getattr(engine, f"generate_{mode}")()


def _run_generated_script(engine: ERVEEngine, script: Path) -> subprocess.CompletedProcess[str]:
    config = engine.config
    cmd = [
        sys.executable,
        str(script),
        "--relationships-path",
        str(config.relationships_path),
        "--output-base",
        str(config.output_base),
        "--min-confidence",
        str(config.min_confidence),
    ]
    if config.top_k is not None:
        cmd.extend(["--top-k", str(config.top_k)])
    return subprocess.run(cmd, text=True, capture_output=True, timeout=300)


if __name__ == "__main__":
    raise SystemExit(main())
