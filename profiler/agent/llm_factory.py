"""LLM factory for the profiler chatbot."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


DEFAULT_NVIDIA_MODEL = "mistralai/mistral-medium-3.5-128b"
NVIDIA_API_BASE = "https://integrate.api.nvidia.com/v1"
DEFAULT_MINIMAX_MODEL = "minimaxai/minimax-m2.7"
DEFAULT_NVIDIA_REASONING_EFFORT = "high"
DEFAULT_NVIDIA_MAX_TOKENS = 16384
DEFAULT_NVIDIA_TEMPERATURE = 0.70
DEFAULT_NVIDIA_TOP_P = 1.00


def get_llm_with_fallback(
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> Any:
    """Return a LangChain chat model, defaulting to NVIDIA through LiteLLM."""
    _load_dotenv()
    provider_name = (provider or "nvidia").lower()

    if provider_name in {"nvidia", "litellm"}:
        resolved_temperature = (
            DEFAULT_NVIDIA_TEMPERATURE if temperature is None else temperature
        )
        return _chat_litellm(
            model=model or DEFAULT_NVIDIA_MODEL,
            api_base=NVIDIA_API_BASE,
            api_key=_nvidia_api_key(),
            custom_llm_provider="openai",  # NVIDIA NIM uses OpenAI-compatible API
            reasoning_effort=DEFAULT_NVIDIA_REASONING_EFFORT,
            max_tokens=DEFAULT_NVIDIA_MAX_TOKENS,
            temperature=resolved_temperature,
            top_p=DEFAULT_NVIDIA_TOP_P,
        )

    if provider_name == "openai":
        return _chat_litellm(
            model=model or os.getenv("OPENAI_MODEL", "openai/gpt-4o-mini"),
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0.1 if temperature is None else temperature,
        )

    if provider_name == "minimax":
        # MiniMax accessed through NVIDIA's OpenAI-compatible API
        return _chat_litellm(
            model=model or DEFAULT_MINIMAX_MODEL,
            api_base=NVIDIA_API_BASE,
            api_key=_nvidia_api_key(),
            custom_llm_provider="openai",
            temperature=1.0,
            top_p=0.95,
            max_tokens=8192,
            drop_params=True,  # Drop unsupported params
        )

    return _chat_litellm(model=model or provider_name, temperature=temperature)


def _chat_litellm(**kwargs: Any) -> Any:
    try:
        from langchain_litellm import ChatLiteLLM
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError(
            "langchain-litellm is required for the chatbot. "
            "Install project dependencies from pyproject.toml."
        ) from exc

    clean_kwargs = {key: value for key, value in kwargs.items() if value is not None}
    return ChatLiteLLM(**clean_kwargs)


def _nvidia_api_key() -> str | None:
    if os.getenv("NVIDIA_API_KEY"):
        return os.getenv("NVIDIA_API_KEY")
    index = 1
    while True:
        key = os.getenv(f"NVIDIA_API_KEY_{index}")
        if key:
            return key
        if index > 20:
            return None
        index += 1


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    # Load from project root's .env file
    project_root = Path(__file__).resolve().parent.parent.parent
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
