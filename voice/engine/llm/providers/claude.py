"""Anthropic Claude LLM provider (needs ANTHROPIC_API_KEY)."""
from __future__ import annotations

from livekit.agents.llm import LLM
from livekit.plugins import anthropic

from .. import registry


@registry.register("claude")
def build(model: str) -> LLM:
    return anthropic.LLM(model=model or "claude-haiku-4-5")
