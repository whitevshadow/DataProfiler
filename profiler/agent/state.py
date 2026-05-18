"""LangGraph state for the profiler chatbot."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Conversation state kept in memory for one CLI process."""

    messages: Annotated[list[BaseMessage], add_messages]
    mode: str
