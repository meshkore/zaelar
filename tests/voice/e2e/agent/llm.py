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
_NO_TEMP = ("opus", "claude", "sonnet", "(retirado)")   # these reject a temperature param on AIMLAPI


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


# Provider transients: worth another attempt. A 401/402/404 is not — that is configuration or balance, and
# retrying it only burns time.
_TRANSIENT = ("429", "500", "502", "503", "504", "timed out", "timeout", "Temporary failure",
              "VACÍA")


def deepseek_direct_call(messages: list[dict], model: str | None = None, temperature: float = 0.0,
                         max_tokens: int = 2000) -> str:
    """DeepSeek from its OWN endpoint (OpenAI-compatible), not through the AIMLAPI broker.

    First leg of the judge fallback, per the operator's provider order (direct → broker → last resort). Raises
    so the caller can move down the chain. Note the model name has no vendor prefix here: the broker catalogues
    `deepseek/deepseek-v4-flash`, the vendor answers to `deepseek-v4-flash`, and using the wrong one gets a 404
    that looks exactly like an outage.
    """
    if not config.DEEPSEEK_KEY:
        raise RuntimeError("no DEEPSEEK_API_KEY")
    model = model or config.DEEPSEEK_JUDGE_MODEL
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if temperature is not None:
        payload["temperature"] = temperature
    req = urllib.request.Request(
        config.DEEPSEEK_BASE.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {config.DEEPSEEK_KEY}", "Content-Type": "application/json",
                 "User-Agent": _UA},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def judge_call(messages: list[dict], max_tokens: int = 2000) -> tuple[str, str]:
    """The JUDGE call: GLM (Z.AI) when configured, else/on-error DeepSeek. Returns (text, model_used).

    The fallback leg RETRIES on transient provider errors, and that is not a nicety: on 2026-08-20 the
    use-case suite lost `book-hotel-night-known__es` TWICE in a row — two full eight-minute conversations,
    already measured, thrown away because the judge got `429 → 503` and `429 → 504`. Losing the judgement
    loses the whole round; retrying it costs one call. Anything non-transient (no balance, bad key, unknown
    model) fails immediately, because retrying that only burns the clock.
    """
    import sys
    import time as _t
    if config.JUDGE_PROVIDER == "zai" and config.ZAI_KEY:
        try:
            return glm_call(messages, max_tokens=max_tokens), config.ZAI_JUDGE_MODEL
        except Exception as e:  # no balance / quota / transport → DeepSeek fallback (never lose the judgement)
            print(f"[judge] GLM unavailable ({str(e)[:80]}) → DeepSeek fallback", file=sys.stderr)
    # DIRECT before the broker: the vendor's endpoint stayed up through the same runs in which the broker
    # returned 429/503/504 and cost three measured rounds.
    if config.DEEPSEEK_KEY:
        try:
            txt = deepseek_direct_call(messages, max_tokens=max_tokens)
            if not (txt or "").strip():
                # AN EMPTY BODY IS NOT AN ANSWER, and treating it as one is how a leg that "worked" loses a
                # round. Measured 2026-08-20, fourth INFRA on the same case: the direct leg returned 200 with
                # empty content (a reasoning model can spend the whole output budget thinking), the judge saw
                # no JSON, retried its own prompt three times against the same silent leg and gave up. The
                # chain existed and never advanced, because nothing had raised.
                raise RuntimeError("respuesta VACÍA (200 sin contenido)")
            return (txt, config.DEEPSEEK_JUDGE_MODEL)
        except Exception as e:
            print(f"[judge] DeepSeek direct unusable ({str(e)[:80]}) → AIMLAPI broker", file=sys.stderr)
    last = None
    for attempt in range(3):
        try:
            txt = call(messages, model=config.JUDGE_MODEL, temperature=0.0, max_tokens=max_tokens)
            if not (txt or "").strip():
                raise RuntimeError("respuesta VACÍA (200 sin contenido)")
            return (txt, config.JUDGE_MODEL)
        except Exception as e:
            last = e
            if not any(t in str(e) for t in _TRANSIENT):
                raise
            if attempt < 2:
                wait = 8 * (attempt + 1)
                print(f"[judge] {config.JUDGE_MODEL} transient ({str(e)[:60]}) → retrying in {wait}s "
                      f"({attempt + 1}/2)", file=sys.stderr)
                _t.sleep(wait)
    raise last


def parse_json(txt: str):
    txt = (txt or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", txt, re.S)
    if m:
        txt = m.group(1).strip()
    i, j = txt.find("{"), txt.rfind("}")
    return json.loads(txt[i:j + 1])
