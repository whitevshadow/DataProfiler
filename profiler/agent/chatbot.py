"""Interactive chatbot for the Agentic Data Profiler."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from typing import Any
from unittest.mock import MagicMock

# Mock transformers to avoid PyTorch dependency (we don't need it for LiteLLM)
sys.modules["transformers"] = MagicMock()
sys.modules["transformers.GPT2TokenizerFast"] = MagicMock()

if sys.platform == "win32" and sys.version_info < (3, 14):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from profiler.agent.llm_factory import get_llm_with_fallback
from profiler.agent.progress import ProgressTracker
from profiler.agent.state import AgentState
from profiler.agent.system_prompt import CHATBOT_SYSTEM_PROMPT

log = logging.getLogger(__name__)

MAX_TOOL_CHARS = 12000


def _classify_user_intent(user_message: str) -> str:
    """Backward-compatible intent helper.

    The graph now uses a generic tool-enabled loop by default, but this helper
    is kept for compatibility with existing tests and external imports.
    """
    text = (user_message or "").strip().lower()
    if not text:
        return "conversation"
    if text in {"hi", "hello", "hey", "thanks", "thank you"}:
        return "conversation"
    if text.endswith("?") and not any(k in text for k in ("profile", "detect", "generate", "list", "show")):
        return "conversation"
    return "data_request"


def _tool_routing_guidance(user_message: str) -> str | None:
    """Return optional per-turn routing guidance.

    Generic chatbot mode does not inject request-specific hard-coded routing.
    """
    del user_message
    return None


def create_chat_graph(tools: list[Any], llm: Any):
    """Create a generic LangGraph chat graph for the given tools and model."""
    llm_with_tools = llm.bind_tools(tools)

    async def agent_node(state: AgentState):
        messages = state["messages"]

        # Add system message if not present
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=CHATBOT_SYSTEM_PROMPT)] + list(messages)

        response = await llm_with_tools.ainvoke(_trim_messages(messages))
        return {"messages": [response]}

    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=MemorySaver())


def _infer_transport(url: str) -> str:
    lowered = (url or "").lower()
    if "/mcp" in lowered or lowered.endswith("/mcp"):
        return "streamable_http"
    return "sse"


async def load_mcp_tools(
    mcp_url: str,
    transport: str | None = None,
    extra_servers: dict[str, dict[str, Any]] | None = None,
) -> list[Any]:
    """Load and de-duplicate LangChain tools from one or more MCP servers."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    resolved_transport = transport or _infer_transport(mcp_url)
    servers: dict[str, dict[str, Any]] = {
        "file-profiler": {
            "url": mcp_url,
            "transport": resolved_transport,
            "timeout": 60,
            "sse_read_timeout": 3600,
        }
    }
    if extra_servers:
        for name, cfg in extra_servers.items():
            merged = {
                "timeout": 60,
                "sse_read_timeout": 3600,
                **cfg,
            }
            merged.setdefault("transport", _infer_transport(str(merged.get("url", ""))))
            servers[name] = merged

    client = MultiServerMCPClient(
        servers
    )

    # Retry connection - server needs time to initialize
    tools = None
    last_error = None
    for attempt in range(15):
        try:
            tools = await client.get_tools()
            break
        except Exception as exc:
            last_error = exc
            if attempt < 14:
                await asyncio.sleep(0.5)
    
    if tools is None:
        raise ConnectionError(f"Failed to connect after 15 attempts: {last_error}")

    seen: set[str] = set()
    unique_tools = []
    for tool in tools:
        if tool.name in seen:
            log.warning("Dropping duplicate tool '%s'", tool.name)
            continue
        seen.add(tool.name)
        unique_tools.append(tool)

    return unique_tools


async def run_chatbot(
    mcp_url: str = "http://localhost:8080/sse",
    provider: str | None = None,
    model: str | None = None,
) -> None:
    """Run the interactive chatbot loop."""
    print("\n  Connecting to MCP server (may take a few seconds)...", end="", flush=True)
    try:
        tools = await load_mcp_tools(mcp_url)
    except Exception as exc:
        print(" FAILED")
        print(f"\n  Could not connect to MCP server: {exc}")
        print("\n  Make sure the server is running in another terminal:")
        print("    python -m profiler --transport sse --port 8080\n")
        return

    if not tools:
        print(" FAILED - no tools loaded.\n")
        return
    print(f" OK ({len(tools)} tools loaded)")

    llm = get_llm_with_fallback(provider=provider, model=model)
    graph = create_chat_graph(tools, llm)
    session_id = f"cli-{uuid.uuid4().hex[:12]}"
    config = {"configurable": {"thread_id": session_id}}

    _print_banner()
    while True:
        try:
            user_input = input("\n You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n  Goodbye!\n")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "q", "bye"}:
            print("\n  Goodbye!\n")
            break
        if user_input.lower() in {"help", "?"}:
            _print_help()
            continue

        print()
        await run_turn(graph, user_input, config)


async def run_turn(graph: Any, user_input: str, config: dict[str, Any]) -> str:
    """Execute one conversational turn and print progress/final output."""
    inputs = {"messages": [HumanMessage(content=user_input)], "mode": "autonomous"}
    tracker = ProgressTracker()
    final_text = ""
    pending_tools: dict[str, dict[str, Any]] = {}

    try:
        async for event in graph.astream(inputs, config=config, stream_mode="updates"):
            for node_name, node_output in event.items():
                if node_name == "agent":
                    msg = node_output["messages"][-1]
                    if isinstance(msg, AIMessage):
                        if msg.tool_calls:
                            await tracker.finish_thinking()
                            for tool_call in msg.tool_calls:
                                tool_id = tool_call.get("id") or tool_call["name"]
                                args = tool_call.get("args", {})
                                pending_tools[tool_id] = {
                                    "name": tool_call["name"],
                                    "args": args,
                                }
                                await tracker.start_tool(tool_call["name"], args)
                        elif msg.content:
                            await tracker.finish_thinking()
                            final_text = _normalize_content(msg.content)
                        else:
                            await tracker.start_thinking()
                elif node_name == "tools":
                    for msg in node_output["messages"]:
                        if isinstance(msg, ToolMessage):
                            content = msg.content if isinstance(msg.content, str) else str(msg.content)
                            tool_info = pending_tools.pop(msg.tool_call_id, None)
                            tool_name = tool_info["name"] if tool_info else "unknown"
                            await tracker.finish_tool(tool_name, content)
    except Exception as exc:
        await tracker.finish_thinking()
        print(f"\n  Error: {exc}")
        log.exception("Agent turn failed")
        return ""

    tracker.print_summary()
    if final_text:
        print("\n Assistant:\n")
        for line in final_text.split("\n"):
            print(f"  {line}")
    return final_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Agentic Data Profiler chatbot.")
    parser.add_argument("--chat", action="store_true", help="Start interactive chat mode.")
    parser.add_argument("--mcp-url", default="http://localhost:8080/sse", help="Profiler MCP SSE URL.")
    parser.add_argument("--provider", default="nvidia", help="LLM provider name.")
    parser.add_argument("--model", default=None, help="Override chat model name.")
    args = parser.parse_args(argv)

    if not args.chat:
        parser.print_help()
        return 0

    try:
        asyncio.run(run_chatbot(mcp_url=args.mcp_url, provider=args.provider, model=args.model))
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass  # Clean exit on Ctrl+C or quit
    return 0


def _trim_messages(messages: list[Any]) -> list[Any]:
    trimmed = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            # Some providers return structured tool payload chunks; normalize to text.
            content = _normalize_content(msg.content)
            if len(content) > MAX_TOOL_CHARS:
                content = content[:MAX_TOOL_CHARS] + "\n...[truncated]"
            msg = ToolMessage(content=content, tool_call_id=msg.tool_call_id)
        elif isinstance(msg, AIMessage):
            # Normalize structured content to plain text for strict OpenAI-compatible APIs.
            if isinstance(msg.content, list):
                content = _normalize_content(msg.content)
                try:
                    msg = msg.model_copy(update={"content": content})
                except Exception:
                    msg = AIMessage(
                        content=content,
                        tool_calls=getattr(msg, "tool_calls", None),
                    )
        trimmed.append(msg)
    return trimmed


def _normalize_content(content: Any) -> str:
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                # Skip MiniMax thinking blocks
                if item.get("type") == "thinking":
                    continue
                # Extract text content
                text_parts.append(item.get("text", str(item)))
            else:
                text_parts.append(str(item))
        return " ".join(text_parts)
    return str(content)


def _print_banner() -> None:
    print("\n" + "=" * 60)
    print("  Data Profiler Chatbot")
    print("=" * 60)
    print()
    print("  Tell me where your data is and I will profile it for you.")
    print("  I can detect schemas, relationships, quality issues, and ER diagrams.")
    print()
    print("  Commands: 'help' for tips, 'quit' to exit")
    print("=" * 60)


def _print_help() -> None:
    print()
    print("  Examples:")
    print("    Profile the file at ./data/warehouse_colors.csv")
    print("    Profile all files in ./data")
    print("    What relationships exist between my tables?")
    print("    Generate an ER diagram")
    print("    Summarize data quality for warehouse_colors")
    print()
    print("  Commands:")
    print("    help, ?    show this help")
    print("    quit, exit exit the chatbot")


if __name__ == "__main__":
    raise SystemExit(main())
