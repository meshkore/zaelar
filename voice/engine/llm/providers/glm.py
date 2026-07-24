"""Z.ai GLM LLM provider (OpenAI-compatible endpoint; reasoning-oriented)."""
from __future__ import annotations

from livekit.agents.llm import LLM
from livekit.plugins import openai as _openai

from ...core.config import SETTINGS
from .. import registry


@registry.register("glm")
def build(model: str) -> LLM:
    return _openai.LLM(
        model=model or SETTINGS.glm_model,
        api_key=SETTINGS.zai_api_key or None,
        base_url=SETTINGS.zai_base_url,
    )
