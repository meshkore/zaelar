"""flash/show_target.py — resolving WHICH widget a "show me" turn means.

Extracted from `probe.py` (architecture ratchet, 2026-08-29): the three functions are one concern —
mirroring `providers/nucleo.py`'s show-guard/identify with the open>recent>catalogue precedence — and
they never touch the probe session state. Kept as a parallel impl of the voice path ON PURPOSE (see
each docstring); keep in sync with `providers/nucleo.py`.
"""
from __future__ import annotations

def _ctx_ids() -> tuple[list, list]:
    """(open_ids, recent_ids) del ESTADO para acotar `runtime.identify` (V2-078) — ESPEJO de `providers/nucleo.py::
    _identify`. Ante un empate el que está en pantalla / se usó hace poco gana. Best-effort (estado ausente → ([],[]))."""
    try:
        from memory import api as _memapi
        _st = _memapi.state() or {}
        return (_st.get("open_widgets") or []), (_st.get("recent_widgets") or [])
    except Exception:
        return [], []


def _identify_ctx(rt, query: str) -> str | None:
    """`rt.identify(query, open_ids, recent_ids)['match']` con el contexto del estado — el resolvedor con la misma
    acotación open>reciente>catálogo que usa la voz. `rt` = módulo widgets.runtime ya importado por el llamante."""
    _o, _r = _ctx_ids()
    return (rt.identify(query, open_ids=_o, recent_ids=_r) or {}).get("match")


def _show_target(text: str, context: list[dict] | None = None, last_action: str = "") -> str | None:
    """Mismo criterio que `providers/nucleo.py::_show_guard_target` (impl PARALELA — mantener en sync): verbo de
    MOSTRAR + NO crear + `runtime.identify` resuelve un widget existente → el turno real lo convierte en show."""
    import re
    import unicodedata
    n = "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()
    if re.search(r"\b(no|sin|tampoco|nunca|ni)\b[^.?!]{0,18}\b(abr|muestr|ensen|pon|saca|sube|ver)", n):
        return None
    if re.search(r"\b(crea|crear|cree|haz|hacer|genera|generar|nuev|construy|dise|monta|make|create|build|new)", n):
        return None
    if not re.search(r"\b(abr|muestr|ensen|pon|saca|sube)|quiero ver|ver mi|ense", n):
        return None
    try:
        from widgets import runtime
        # A deictic show request ("muéstramelo") gets its noun from the recent dialogue. Resolve the most recent
        # topical utterance against the same real widget catalogue instead of forcing the model to repeat a noun.
        # This is generic: weather, agenda, messages, music… are all resolved by runtime.identify, not a keyword map.
        from . import router as _router
        tail = (text or "").strip().lower().strip("¿?¡!.,;:")
        deictic = (bool(re.search(r"\b(?:muestr|ensen|abre|saca)\w*(?:lo|la|los|las)\b", n))
                    or any(_router.looks_like_bare_ref(token) for token in tail.split() if token))
        if deictic:
            for message in reversed(context or []):
                if message.get("role") != "user":
                    continue
                prior = str(message.get("content") or "").strip()
                if prior:
                    match = _identify_ctx(runtime, prior)
                    if match:
                        return match
                    break  # the grammatical antecedent is the immediately preceding user topic, never older history
            # The preceding route is stronger than fuzzy words: a LIGHT search is rendered in the built-in
            # `search` (Búsqueda / Tiempo) surface. This is action→surface continuity, not a topic keyword table.
            if last_action == "search" and runtime.get("search") is not None:
                return "search"
        return _identify_ctx(runtime, text)
    except Exception:
        return None
