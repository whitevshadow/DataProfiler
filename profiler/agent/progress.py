"""Terminal progress display for chatbot tool execution."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any


TOOL_WEIGHTS: dict[str, float] = {
    "list_supported_files": 5,
    "profile_file": 20,
    "profile_directory": 40,
    "enrich_relationships": 80,
    "get_quality_summary": 10,
    "get_table_relationships": 10,
    "generate_erd": 5,
    "generate_er_visualizations": 15,
}
DEFAULT_TOOL_WEIGHT = 10
BAR_WIDTH = 30
SPINNER = ["|", "/", "-", "\\"]


class ProgressTracker:
    """Track visible progress across one chatbot turn."""

    def __init__(self) -> None:
        self._completed_weight = 0.0
        self._total_weight = 0.0
        self._tool_count = 0
        self._spinner_task: asyncio.Task | None = None
        self._start_time = 0.0
        self._turn_start = time.time()

    async def start_tool(self, tool_name: str, args: dict[str, Any]) -> None:
        self._tool_count += 1
        self._start_time = time.time()
        self._total_weight += TOOL_WEIGHTS.get(tool_name, DEFAULT_TOOL_WEIGHT)
        args_short = ", ".join(f"{key}={_truncate(str(value), 48)}" for key, value in args.items())
        _clear_line()
        sys.stdout.write(f"\r  [{self._tool_count}] {tool_name}({args_short})\n")
        sys.stdout.flush()
        self._spinner_task = asyncio.create_task(self._spin(tool_name))

    async def finish_tool(self, tool_name: str, content: str) -> None:
        await self.finish_thinking()
        elapsed = time.time() - self._start_time
        self._completed_weight += TOOL_WEIGHTS.get(tool_name, DEFAULT_TOOL_WEIGHT)
        summary = _extract_summary(tool_name, content)
        marker = "OK" if "error" not in content[:120].lower() else "ERR"
        pct = min(
            (self._completed_weight / self._total_weight * 100)
            if self._total_weight
            else 100,
            100,
        )
        sys.stdout.write(f"\r      {marker} Done in {_fmt_time(elapsed)} - {summary}\n")
        sys.stdout.write(f"      {_render_bar(pct)}\n")
        sys.stdout.flush()

    async def start_thinking(self) -> None:
        await self.finish_thinking()
        self._spinner_task = asyncio.create_task(self._spin("Thinking"))

    async def finish_thinking(self) -> None:
        if self._spinner_task and not self._spinner_task.done():
            self._spinner_task.cancel()
            try:
                await self._spinner_task
            except asyncio.CancelledError:
                pass
            _clear_line()

    def print_summary(self) -> None:
        if self._tool_count:
            sys.stdout.write(
                f"\n      Pipeline complete: {self._tool_count} "
                f"step{'s' if self._tool_count != 1 else ''} "
                f"in {_fmt_time(time.time() - self._turn_start)}\n"
            )
            sys.stdout.flush()

    async def _spin(self, label: str) -> None:
        index = 0
        try:
            while True:
                frame = SPINNER[index % len(SPINNER)]
                elapsed = time.time() - self._start_time if self._start_time else 0
                _clear_line()
                if label == "Thinking":
                    sys.stdout.write(f"\r      {frame} Thinking...")
                else:
                    sys.stdout.write(f"\r      {frame} {_hint(label)}... ({_fmt_time(elapsed)})")
                sys.stdout.flush()
                index += 1
                await asyncio.sleep(0.15)
        except asyncio.CancelledError:
            pass


def _hint(tool_name: str) -> str:
    return {
        "list_supported_files": "Scanning files",
        "profile_file": "Profiling file",
        "profile_directory": "Profiling directory",
        "enrich_relationships": "Detecting relationships",
        "get_quality_summary": "Summarizing quality",
        "get_table_relationships": "Loading relationships",
        "generate_erd": "Generating ERD",
        "generate_er_visualizations": "Generating ERVE exports",
    }.get(tool_name, "Running tool")


def _extract_summary(tool_name: str, content: str) -> str:
    try:
        data = json.loads(content) if content.strip().startswith(("{", "[")) else None
    except json.JSONDecodeError:
        data = None
    if isinstance(data, list):
        return f"{len(data)} item(s)"
    if not isinstance(data, dict):
        return _truncate(content.replace("\n", " "), 80)
    if tool_name == "list_supported_files":
        return f"{len(data) if isinstance(data, list) else data.get('total_files', '?')} file(s)"
    if tool_name in {"profile_file", "profile_directory"}:
        table = data.get("table_name")
        if table:
            return f"{table}: {data.get('column_count', 0)} columns"
        return f"{data.get('profiles_generated', 0)} profile(s)"
    if tool_name == "enrich_relationships":
        rels = data.get("relationships", {})
        return f"relationships output: {rels.get('output_file') or data.get('relationships_path')}"
    if tool_name == "get_quality_summary":
        return f"{data.get('table_count', 0)} table(s), {data.get('columns_with_issues', 0)} columns with issues"
    if tool_name == "get_table_relationships":
        return f"{data.get('total_relationships', 0)} relationship(s)"
    if tool_name == "generate_erd":
        return f"ERD: {data.get('erd_path', 'generated')}"
    if tool_name == "generate_er_visualizations":
        outputs = data.get("outputs", {})
        return f"ERVE {data.get('mode', 'export')}: {len(outputs)} artifact(s)"
    return _truncate(content.replace("\n", " "), 80)


def _render_bar(pct: float) -> str:
    filled = int(BAR_WIDTH * pct / 100)
    return f"[{'#' * filled}{'.' * (BAR_WIDTH - filled)}] {pct:.0f}%"


def _fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    return f"{minutes}m {seconds % 60:.0f}s"


def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def _clear_line() -> None:
    sys.stdout.write("\r\033[K")
    sys.stdout.flush()
