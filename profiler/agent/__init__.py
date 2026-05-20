"""Conversational agent for the Agentic Data Profiler."""

from __future__ import annotations

__all__ = ["run_chatbot"]

async def run_chatbot(*args, **kwargs):
	"""Lazy import to avoid module execution warnings in `python -m` mode."""
	from profiler.agent.chatbot import run_chatbot as _run_chatbot

	return await _run_chatbot(*args, **kwargs)
