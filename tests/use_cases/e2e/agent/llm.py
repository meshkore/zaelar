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


def _as_text(content) -> str:
    """Flatten a reply whose `content` came back as a LIST of parts instead of a string.

    Cost a real scenario (`buy-known-product__es`, 2026-08-18): the broker returned OpenAI's structured
    content form — `[{"type": "text", "text": "..."}]` — and `driver.py`'s `.strip()` on it raised
    `'list' object has no attribute 'strip'`, killing the scenario mid-run. Both shapes are legal in that API
    and which one arrives is the provider's choice, not ours, so the caller cannot be the place that knows.
    Non-text parts are dropped rather than stringified: a `str(dict)` of an image part inside the tester's next
    utterance would be worse than saying nothing.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text") or "" for part in content
            if isinstance(part, dict) and (part.get("type") in (None, "text") or "text" in part))
    return "" if content is None else str(content)


def call(messages: list[dict], model: str | None = None, temperature: float = 0.0, max_tokens: int = 4000) -> str:
    try:
        return _as_text(_call(messages, model=model, temperature=temperature, max_tokens=max_tokens))
    except Exception:
        time.sleep(2.0)
        return _as_text(_call(messages, model=model, temperature=temperature, max_tokens=max_tokens))


__all__ = ["call", "glm_call", "judge_call", "parse_json"]
