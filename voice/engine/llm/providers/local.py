"""Local LLM provider (LOCAL profile default).

On-machine via an OpenAI-compatible local server — Ollama (:11434/v1, MLX-backed
since 0.19) or mlx_lm.server. The fast orchestrator: low TTFT, no per-token cost,
no network hop; escalate hard turns to a remote provider.
"""
from __future__ import annotations

from livekit.agents.llm import LLM
from livekit.plugins import openai as _openai

from ...core.config import SETTINGS
from .. import registry


@registry.register("local")
def build(model: str) -> LLM:
    return _openai.LLM(
        model=model or SETTINGS.local_llm_model,
        api_key="local",  # Ollama/mlx_lm ignore the value but require non-empty
        base_url=SETTINGS.local_llm_url,
    )
