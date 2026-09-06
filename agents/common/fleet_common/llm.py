"""LLM access — always through the LiteLLM gateway with the agent's virtual key.

Agents never hold a provider key; a revoked/over-budget virtual key turns into a
clean 401/429 here rather than silent failure elsewhere (risks #2, #5).
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from .config import Settings


def chat_model(settings: Settings, model: str | None = None, temperature: float = 0.0) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=f"{settings.litellm_base_url.rstrip('/')}/v1",
        api_key=settings.litellm_api_key,
        model=model or settings.model,
        temperature=temperature,
        timeout=600,
        max_retries=2,
    )
