#
# DIRECT brain (BRAIN=direct) — a bare OpenAI-compatible model call, no memory/tools/cron.
#
# zaelar's pre-brain baseline: the voice cascade talks straight to a fast NON-reasoning model over AIMLAPI
# (deepseek-v4-flash, validated to close the turn). No Hermes, no tag side-effects beyond what the model itself
# emits. This is just the LiveKit openai.LLM plugin pointed at AIMLAPI with zaelar's default model — the direct
# analogue of the old Pipecat OpenAILLMService path. Reasoning models are BANNED on the voice path (they stall
# the first token / never close the turn → zaelar goes mute).
#
from __future__ import annotations

from livekit.agents.llm import LLM
from livekit.plugins import openai as _openai

from ...core.config import SETTINGS
from .. import registry


@registry.register("direct")
def build(model: str = "") -> LLM:
    return _openai.LLM(
        model=model or "deepseek/deepseek-v4-flash",
        api_key=SETTINGS.aimlapi_api_key or None,
        base_url=SETTINGS.aimlapi_base_url,
    )
