"""Cliente LLM del Susurro (V2-053) — una completion no-streaming contra config §susurro, fail-open.

Mismo patrón que el CORAZÓN (mem_processor): endpoint OpenAI-compatible, key resuelta POR ENDPOINT (la lección
de V2-fast-brain: nunca asumir qué key hay en el store), timeout duro, y NUNCA lanza — cualquier fallo devuelve
None y el ciclo de auditoría se anota como `error` y sigue la vida.
"""
from __future__ import annotations

import os
import time

_TIMEOUT = float(os.getenv("SUSURRO_TIMEOUT", "45") or 45)

# AIMLAPI (el endpoint por defecto desde 2026-08-09) va tras Cloudflare, que 403ea a clientes que no parecen
# navegador. COMPROBADO hoy: el UA por defecto de aiohttp SÍ pasa (200) — el que se bloqueaba era el de urllib,
# por eso `fast_client`/`memllm` lo llevan. Se manda igualmente: es gratis, iguala el patrón de los otros
# clientes y el fail-open del Susurro es SILENCIOSO por diseño — no conviene depender de la política de un CDN.
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
    """→ (contenido crudo | None, meta {model, ms, tokens, error?}). El payload COMPLETO enviado va en
    meta["request"] para la observabilidad total (regla del operador: registrar envío Y respuesta)."""
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
    # EGRESS (T304). `meta` conserva el base_url ORIGINAL a propósito: es lo que hace legible el visor
    # («esta auditoría iba a AIMLAPI»), y el enrutado real es un detalle del despliegue, no del evento.
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
            # algunos endpoints no soportan response_format → reintento sin él
            payload2 = {k: v for k, v in payload.items() if k != "response_format"}
            async with aiohttp.ClientSession(timeout=to) as s:
                async with s.post(base + "/chat/completions",
                                  headers={"Authorization": f"Bearer {key}", **_UA}, json=payload2) as r:
                    data = await r.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        meta.update(ms=round((time.time() - t0) * 1000),
                    tokens={"in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens")})
        # A ENERGY (2026-08-13). Los tokens ya se leían aquí, pero solo para PINTARLOS en el evento del
        # visor — el mismo defecto que tuvieron los Brain Workers antes de 2026-08-05: el número existía
        # y moría en un chip de UI. Susurro corre ante fricción, con un modelo POTENTE y una ventana
        # grande de conversación: es de las llamadas más caras por unidad. Un intento rechazado antes del
        # reintento sin `response_format` no se cobra (un 400 no trae `usage`).
        from nucleo import energy_meter as _energy
        _energy.meter_openai_response({"usage": usage}, base_url=base, model=model)
        return content, meta
    except Exception as e:  # noqa: BLE001 — fail-open duro
        meta.update(ms=round((time.time() - t0) * 1000), error=f"{type(e).__name__}: {e}")
        return None, meta
