"""Susurro LLM client (V2-053) — a non-streaming completion against §susurro config, fail-open.

Same pattern as the HEART (mem_processor): OpenAI-compatible endpoint, key resolved BY ENDPOINT (the lesson
from V2-fast-brain: never assume which key is in the store), hard timeout, and NEVER raises — any failure returns
None and the audit cycle is recorded as `error` and carries on.
"""
from __future__ import annotations

import os
import time

_TIMEOUT = float(os.getenv("SUSURRO_TIMEOUT", "45") or 45)

# AIMLAPI (the default endpoint since 2026-08-09) sits behind Cloudflare, which returns 403 to clients that do not
# look like a browser. VERIFIED today: aiohttp's default UA DOES pass (200) — the one being blocked was urllib's,
# which is why `fast_client`/`memllm` carry it. It is sent anyway: it is free, matches the pattern of the other
# clients, and Susurro's fail-open is SILENT by design — it is unwise to depend on a CDN's policy.
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def cfg() -> dict:
    try:
        from config import v2 as _v2
        return _v2.get("susurro") or {}
    except Exception:
        return {}


def resolved_api_key(base_url: str, explicit: str = "") -> str:
    if explicit:
        return explicit
    u = (base_url or "").lower()
    if any(h in u for h in ("11434", "localhost", "127.0.0.1")):
        return "local"
    # Single BY-ENDPOINT resolver (`nucleo/provider_keys.py`, V2-098) — this used to know only 4 of the ~9
    # endpoints (missing gemini/mistral/z.ai/deepseek/moonshot: pointing Susurro at one of those would have
    # silently resolved to ""). OPENAI_API_KEY fallback preserved — this client's own historical default, not
    # part of the shared resolver.
    from nucleo.provider_keys import key_for_endpoint
    return key_for_endpoint(u, default="") or os.getenv("OPENAI_API_KEY", "")


async def audit_llm(window_text: str) -> tuple[str | None, dict]:
    """→ (raw content | None, meta {model, ms, tokens, error?}). The COMPLETE payload sent is stored in
    meta["request"] for full observability (operator rule: record both request AND response)."""
    from . import catalog
    c = cfg()
    # Last resort when §susurro cannot be read: it must MATCH the default in `config/v2.py` (AIMLAPI broker),
    # never a direct OpenAI endpoint — there is no OPENAI_API_KEY in the cloud and this would fail in silence.
    # 2026-08-21: both moved off OpenAI together, which is the point — a literal here that drifts from the config
    # default is a fallback that only runs when something is already wrong, so nobody would notice it drifted.
    model = str(c.get("model") or "deepseek-v4-flash")
    base = str(c.get("base_url") or "https://api.aimlapi.com/v1").rstrip("/")
    key = resolved_api_key(base, str(c.get("api_key") or "").strip())
    messages = [
        {"role": "system", "content": catalog.SYSTEM},
        {"role": "user", "content": window_text},
    ]
    payload = {"model": model, "temperature": 0, "messages": messages,
               "response_format": {"type": "json_object"}}
    meta: dict = {"model": model, "base_url": base, "request": payload}
    # EGRESS (T304). `meta` deliberately preserves the ORIGINAL base_url: it is what makes the viewer readable
    # ("this audit was headed to AIMLAPI"), and the actual routing is a deployment detail, not part of the event.
    from nucleo import llm_egress
    base, key, _extra = llm_egress.route(base, key)
    if not key:
        meta["error"] = "sin api key para el endpoint"
        return None, meta
    t0 = time.time()
    try:
        import aiohttp
        to = aiohttp.ClientTimeout(total=_TIMEOUT)
        async with aiohttp.ClientSession(timeout=to) as s:
            async with s.post(base + "/chat/completions",
                              headers={"Authorization": f"Bearer {key}", **_UA}, json=payload) as r:
                data = await r.json()
        if not isinstance(data, dict) or "choices" not in data:
            # some endpoints do not support response_format → retry without it
            payload2 = {k: v for k, v in payload.items() if k != "response_format"}
            async with aiohttp.ClientSession(timeout=to) as s:
                async with s.post(base + "/chat/completions",
                                  headers={"Authorization": f"Bearer {key}", **_UA}, json=payload2) as r:
                    data = await r.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        meta.update(ms=round((time.time() - t0) * 1000),
                    tokens={"in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens")})
        # A ENERGY (2026-08-13). Tokens were already read here, but only to DISPLAY THEM in the viewer event —
        # the same defect Brain Workers had before 2026-08-05: the number existed and died in a UI chip. Susurro
        # runs under friction, with a POWERFUL model and a large conversation window: it is among the most
        # expensive calls per unit. An attempt rejected before the retry without `response_format` is not charged
        # (a 400 does not include `usage`).
        from nucleo import energy_meter as _energy
        _energy.meter_openai_response({"usage": usage}, base_url=base, model=model)
        return content, meta
    except Exception as e:  # noqa: BLE001 — fail-open duro
        meta.update(ms=round((time.time() - t0) * 1000), error=f"{type(e).__name__}: {e}")
        return None, meta
