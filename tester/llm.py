"""Self-contained LLM clients for the tester (independent of zaelar's voice path).

Two providers, per the operator's model-routing directive (2026-07-07):
  · DRIVE (what the tester says to zaelar) → DeepSeek via AIMLAPI (cheap, high-frequency).
  · JUDGE (competent evaluation/reasoning) → GLM via Z.AI's coding-plan endpoint (Anthropic-compatible),
    with automatic FALLBACK to DeepSeek if Z.AI errors (no balance / quota exhausted).
NEVER expensive AIMLAPI models (opus…) — burns the balance. Uses the DEDICATED tester keys."""
from __future__ import annotations

import json
import re
import urllib.request

from . import config

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_NO_TEMP = ("opus", "claude", "sonnet", "haiku")   # these reject a temperature param on AIMLAPI


def call(messages: list[dict], model: str | None = None, temperature: float = 0.0, max_tokens: int = 4000) -> str:
    """DeepSeek (AIMLAPI, OpenAI-compatible). Used for DRIVING and as the judge fallback."""
    model = model or config.DRIVE_MODEL
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if temperature is not None and not any(t in model.lower() for t in _NO_TEMP):
        payload["temperature"] = temperature
    req = urllib.request.Request(
        config.AIMLAPI_BASE.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {config.TESTER_KEY}", "Content-Type": "application/json", "User-Agent": _UA},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def glm_call(messages: list[dict], model: str | None = None, max_tokens: int = 2000) -> str:
    """GLM via Z.AI's coding-plan endpoint (Anthropic Messages API). Raises on any error so the caller can
    fall back. Converts OpenAI-style messages → Anthropic (system string + user/assistant turns)."""
    if not config.ZAI_KEY:
        raise RuntimeError("no TESTER_ZAI_KEY")
    model = model or config.ZAI_JUDGE_MODEL
    system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
    turns = [{"role": m["role"], "content": m["content"]} for m in messages if m.get("role") in ("user", "assistant")]
    if not turns:
        turns = [{"role": "user", "content": system}]; system = ""
    payload = {"model": model, "max_tokens": max_tokens, "messages": turns}
    if system:
        payload["system"] = system
    req = urllib.request.Request(
        config.ZAI_BASE.rstrip("/") + "/v1/messages",
        data=json.dumps(payload).encode(),
        headers={"x-api-key": config.ZAI_KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json", "User-Agent": _UA},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
    parts = data.get("content") or []
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


def judge_call(messages: list[dict], max_tokens: int = 2000) -> tuple[str, str]:
    """The JUDGE call: GLM (Z.AI) when configured, else/on-error DeepSeek. Returns (text, model_used)."""
    if config.JUDGE_PROVIDER == "zai" and config.ZAI_KEY:
        try:
            return glm_call(messages, max_tokens=max_tokens), config.ZAI_JUDGE_MODEL
        except Exception as e:  # no balance / quota / transport → DeepSeek fallback (never lose the judgement)
            import sys
            print(f"[judge] GLM unavailable ({str(e)[:80]}) → DeepSeek fallback", file=sys.stderr)
    return call(messages, model=config.JUDGE_MODEL, temperature=0.0, max_tokens=max_tokens), config.JUDGE_MODEL


def parse_json(txt: str):
    txt = (txt or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", txt, re.S)
    if m:
        txt = m.group(1).strip()
    i, j = txt.find("{"), txt.rfind("}")
    return json.loads(txt[i:j + 1])
