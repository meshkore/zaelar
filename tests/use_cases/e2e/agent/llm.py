"""Re-exports the voice tester's LLM client (tests/voice/e2e/agent/llm.py) — same DeepSeek/AIMLAPI +
GLM/Z.AI clients, same credentials, no reason to duplicate the HTTP/parsing code. This module exists only
so `from . import config, llm` reads the same way across every module in this package.

`call` gets one retry on top of the original: AIMLAPI sits behind Cloudflare and blips intermittently
(documented elsewhere in this codebase) — for an unattended run, one transient network error should not
waste the whole scenario's turns and cost so far. `glm_call`/`parse_json` are unchanged passthroughs.
"""
from __future__ import annotations

import os
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


# ── DRIVE de repuesto ─────────────────────────────────────────────────────────────────────────────────────
# El 2026-08-19 a las 02:34 la cuenta de AIMLAPI se quedó SIN FONDOS (403 con
# «You've run out of funds», verificado contra el cuerpo de la respuesta con las dos claves, la del arnés y la
# del motor). El modelo DRIVE —el que hace de persona— va por ahí, así que ningún caso podía producir veredicto:
# INFRA con 0 turnos, una y otra vez. Con autorización explícita del operador se releva a Z.AI, que responde.
#
# Esto NO es gratis y por eso se ESTAMPA en cada ronda (`drive_model` viaja al ledger y a la iniciativa):
#   · DRIVE y JUEZ pasan a compartir proveedor → el juicio pierde independencia de proveedor.
#   · Un caso medido con este DRIVE no es comparable con uno medido con el anterior.
# Un relevo silencioso habría dejado el tablero avanzando con dos instrumentos distintos y sin manera de saber
# qué fila se midió con cuál — exactamente el error que el arnés existe para no cometer.
_FUNDS = ("run out of funds", "top up your balance", "insufficient", "403")
_DEFAULT_DRIVE = "aimlapi"
_used_drive = _DEFAULT_DRIVE


def drive_model() -> str:
    """Qué modelo condujo la ÚLTIMA llamada de DRIVE. Lo consume `run.py` para sellar la ronda."""
    return _used_drive


def _force_zai() -> bool:
    return (os.environ.get("ZAELAR_UC_DRIVE") or "").strip().lower() in ("zai", "glm")


def call(messages: list[dict], model: str | None = None, temperature: float = 0.0, max_tokens: int = 4000) -> str:
    global _used_drive
    if _force_zai():
        _used_drive = "zai/glm"
        return _as_text(glm_call(messages, max_tokens=max_tokens))
    try:
        out = _as_text(_call(messages, model=model, temperature=temperature, max_tokens=max_tokens))
        _used_drive = _DEFAULT_DRIVE
        return out
    except Exception as first:
        time.sleep(2.0)
        try:
            out = _as_text(_call(messages, model=model, temperature=temperature, max_tokens=max_tokens))
            _used_drive = _DEFAULT_DRIVE
            return out
        except Exception as second:
            # Solo se releva cuando el proveedor dice que es de SALDO. Un timeout o un 500 son pasajeros y
            # relevarlos escondería una avería del titular tras un modelo distinto para siempre.
            blob = f"{first} {second}".lower()
            if not any(x in blob for x in _FUNDS):
                raise
            _used_drive = "zai/glm"
            return _as_text(glm_call(messages, max_tokens=max_tokens))


__all__ = ["call", "glm_call", "judge_call", "parse_json", "drive_model"]
