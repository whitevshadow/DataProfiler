from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from file_profiler.agent.chatbot import create_chat_graph


class FakeToolCallingModel:
    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, messages):
        if any(isinstance(message, ToolMessage) for message in messages):
            return AIMessage(content="Profile completed.")
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "fake_profile_file",
                    "args": {"path": "data/warehouse_colors.csv"},
                    "id": "call-1",
                }
            ],
        )


@tool
def fake_profile_file(path: str) -> str:
    """Fake profile tool for graph tests."""
    return f"profiled {path}"


@pytest.mark.asyncio
async def test_chat_graph_calls_tool_and_returns_final_message():
    graph = create_chat_graph([fake_profile_file], FakeToolCallingModel())

    result = await graph.ainvoke(
        {"messages": [("user", "profile this file")], "mode": "autonomous"},
        config={"configurable": {"thread_id": "test-thread"}},
    )

    assert result["messages"][-1].content == "Profile completed."
