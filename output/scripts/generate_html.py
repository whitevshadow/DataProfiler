"""Generated ERVE helper script for html export."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from profiler.erve import ERVEConfig, ERVEEngine


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ERVE html export.")
    parser.add_argument("--relationships-path", default='F:\\agentic_profiler\\new\\output\\relationships\\relationships.json')
    parser.add_argument("--output-base", default='F:\\agentic_profiler\\new\\output')
    parser.add_argument("--min-confidence", type=float, default=0.7)
    parser.add_argument("--top-k", type=int, default=None)
    args = parser.parse_args()

    engine = ERVEEngine(config=ERVEConfig(
        relationships_path=args.relationships_path,
        output_base=args.output_base,
        min_confidence=args.min_confidence,
        top_k=args.top_k,
    ))
    result = getattr(engine, "generate_html_export", None)
    if result is None:
        if "html" == "full":
            payload = engine.generate_full_export()
        else:
            payload = getattr(engine, "generate_html")()
    else:
        payload = result()
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
