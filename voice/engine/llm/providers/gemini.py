"""Google Gemini LLM provider."""
from __future__ import annotations

from livekit.agents.llm import LLM
from livekit.plugins import google

from ...core.config import SETTINGS
from .. import registry


@registry.register("gemini")
def build(model: str) -> LLM:
    return google.LLM(model=model or "gemini-2.0-flash", api_key=SETTINGS.gemini_api_key or None)
