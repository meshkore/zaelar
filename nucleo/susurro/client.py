"""Cliente LLM del Susurro (V2-053) — una completion no-streaming contra config §susurro, fail-open.

Mismo patrón que el CORAZÓN (mem_processor): endpoint OpenAI-compatible, key resuelta POR ENDPOINT (la lección
de V2-fast-brain: nunca asumir qué key hay en el store), timeout duro, y NUNCA lanza — cualquier fallo devuelve
None y el ciclo de auditoría se anota como `error` y sigue la vida.
"""
from __future__ import annotations

import os
import time

_TIMEOUT = float(os.getenv("SUSURRO_TIMEOUT", "45") or 45)


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
    if "openai.com" in u:
        return os.getenv("OPENAI_API_KEY", "")
    if "x.ai" in u:
        return os.getenv("XAI_API_KEY", "")
    if "groq.com" in u:
        return os.getenv("GROQ_API_KEY", "")
    if "aimlapi" in u:
        return os.getenv("AIMLAPI_KEY", "")
    if any(h in u for h in ("11434", "localhost", "127.0.0.1")):
        return "local"
    return os.getenv("OPENAI_API_KEY", "")


async def audit_llm(window_text: str) -> tuple[str | None, dict]:
    """→ (contenido crudo | None, meta {model, ms, tokens, error?}). El payload COMPLETO enviado va en
    meta["request"] para la observabilidad total (regla del operador: registrar envío Y respuesta)."""
    from . import catalog
    c = cfg()
    model = str(c.get("model") or "gpt-4.1-mini")
    base = str(c.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    key = resolved_api_key(base, str(c.get("api_key") or "").strip())
    messages = [
        {"role": "system", "content": catalog.SYSTEM},
        {"role": "user", "content": window_text},
    ]
    payload = {"model": model, "temperature": 0, "messages": messages,
               "response_format": {"type": "json_object"}}
    meta: dict = {"model": model, "base_url": base, "request": payload}
    if not key:
        meta["error"] = "sin api key para el endpoint"
        return None, meta
    t0 = time.time()
    try:
        import aiohttp
        to = aiohttp.ClientTimeout(total=_TIMEOUT)
        async with aiohttp.ClientSession(timeout=to) as s:
            async with s.post(base + "/chat/completions",
                              headers={"Authorization": f"Bearer {key}"}, json=payload) as r:
                data = await r.json()
        if not isinstance(data, dict) or "choices" not in data:
            # algunos endpoints no soportan response_format → reintento sin él
            payload2 = {k: v for k, v in payload.items() if k != "response_format"}
            async with aiohttp.ClientSession(timeout=to) as s:
                async with s.post(base + "/chat/completions",
                                  headers={"Authorization": f"Bearer {key}"}, json=payload2) as r:
                    data = await r.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        meta.update(ms=round((time.time() - t0) * 1000),
                    tokens={"in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens")})
        return content, meta
    except Exception as e:  # noqa: BLE001 — fail-open duro
        meta.update(ms=round((time.time() - t0) * 1000), error=f"{type(e).__name__}: {e}")
        return None, meta
