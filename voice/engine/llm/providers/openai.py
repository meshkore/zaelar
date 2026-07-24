"""OpenAI LLM provider (fast GPT text model behind the pipeline)."""
from __future__ import annotations

from livekit.agents.llm import LLM
from livekit.plugins import openai as _openai

from ...core.config import SETTINGS
from .. import registry


@registry.register("openai")
def build(model: str) -> LLM:
    return _openai.LLM(model=model or "gpt-4.1-mini", api_key=SETTINGS.openai_api_key or None)
