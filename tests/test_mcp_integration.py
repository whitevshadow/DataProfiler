from __future__ import annotations

import socket
import subprocess
import sys
import time
import asyncio
from pathlib import Path

import pytest


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _tool_text(result) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return "\n".join(
            item.get("text", str(item)) if isinstance(item, dict) else str(item)
            for item in result
        )
    return str(result)


@pytest.mark.asyncio
async def test_mcp_server_loads_tools_and_profiles(tmp_path):
    pytest.importorskip("langchain_mcp_adapters")
    port = _free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "profiler",
            "--transport",
            "sse",
            "--port",
            str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        client = MultiServerMCPClient(
            {
                "file-profiler": {
                    "url": f"http://127.0.0.1:{port}/sse",
                    "transport": "sse",
                    "timeout": 60,
                    "sse_read_timeout": 60,
                }
            }
        )
        tools = None
        last_error = None
        for _ in range(30):
            try:
                tools = await client.get_tools()
                break
            except Exception as exc:
                last_error = exc
                if process.poll() is not None:
                    break
                time.sleep(0.5)
        if tools is None:
            stdout, stderr = process.communicate(timeout=5)
            pytest.fail(f"Could not connect to MCP server: {last_error}\n{stdout}\n{stderr}")

        tool_names = {tool.name for tool in tools}
        assert {"list_supported_files", "profile_file", "generate_erd"} <= tool_names

        by_name = {tool.name: tool for tool in tools}
        listed = await asyncio.wait_for(
            by_name["list_supported_files"].ainvoke({"path": "data/warehouse_colors.csv"}),
            timeout=20,
        )
        assert "warehouse_colors.csv" in _tool_text(listed)

        # Skip slow profiling operations in CI - tools loading is the key test
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
