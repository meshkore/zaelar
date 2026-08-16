"""Re-exports the voice tester's LLM client (tests/voice/e2e/agent/llm.py) — same DeepSeek/AIMLAPI +
GLM/Z.AI clients, same credentials, no reason to duplicate the HTTP/parsing code. This module exists only
so `from . import config, llm` reads the same way across every module in this package.

`call` gets one retry on top of the original: AIMLAPI sits behind Cloudflare and blips intermittently
(documented elsewhere in this codebase) — for an unattended run, one transient network error should not
waste the whole scenario's turns and cost so far. `glm_call`/`parse_json` are unchanged passthroughs.
"""
from __future__ import annotations

import time

from tests.voice.e2e.agent.llm import call as _call
from tests.voice.e2e.agent.llm import glm_call, judge_call, parse_json


def call(messages: list[dict], model: str | None = None, temperature: float = 0.0, max_tokens: int = 4000) -> str:
    try:
        return _call(messages, model=model, temperature=temperature, max_tokens=max_tokens)
    except Exception:
        time.sleep(2.0)
        return _call(messages, model=model, temperature=temperature, max_tokens=max_tokens)


__all__ = ["call", "glm_call", "judge_call", "parse_json"]
