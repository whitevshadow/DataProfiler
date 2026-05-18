from __future__ import annotations

import subprocess
import sys


def test_file_profiler_help():
    result = subprocess.run(
        [sys.executable, "-m", "file_profiler", "--help"],
        text=True,
        capture_output=True,
        timeout=20,
    )

    assert result.returncode == 0
    assert "--transport" in result.stdout


def test_agent_help():
    result = subprocess.run(
        [sys.executable, "-m", "file_profiler.agent", "--help"],
        text=True,
        capture_output=True,
        timeout=20,
    )

    assert result.returncode == 0
    assert "--chat" in result.stdout


def test_chatbot_importable():
    import file_profiler.agent.chatbot as chatbot

    assert callable(chatbot.create_chat_graph)
