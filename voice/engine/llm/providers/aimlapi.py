"""AIMLAPI LLM provider (remote default) — fast, low-latency OpenAI-compatible.

Default gpt-4.1-nano (~0.55s TTFT measured). Non-reasoning on purpose: a
reasoning model stalls the first token, which is exactly the latency we fight.
"""
from __future__ import annotations

from livekit.agents.llm import LLM
from livekit.plugins import openai as _openai

from ...core.config import SETTINGS
from .. import registry


@registry.register("aimlapi")
def build(model: str) -> LLM:
    return _openai.LLM(
        model=model or "gpt-4.1-nano",
        api_key=SETTINGS.aimlapi_api_key or None,
        base_url=SETTINGS.aimlapi_base_url,
    )
