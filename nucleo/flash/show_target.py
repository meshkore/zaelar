"""flash/show_target.py — resolving WHICH widget a "show me" turn means.

Extracted from `probe.py` (architecture ratchet, 2026-08-29): the three functions are one concern —
mirroring `providers/nucleo.py`'s show-guard/identify with the open>recent>catalogue precedence — and
they never touch the probe session state. Kept as a parallel impl of the voice path ON PURPOSE (see
each docstring); keep in sync with `providers/nucleo.py`.
"""
from __future__ import annotations

def _ctx_ids() -> tuple[list, list]:
    """(open_ids, recent_ids) from STATE to narrow `runtime.identify` (V2-078) — MIRROR of
    `providers/nucleo.py::_identify`. On a tie, the item on screen / used recently wins. Best-effort (missing state → ([], []))."""
    try:
        from memory import api as _memapi
        _st = _memapi.state() or {}
        return (_st.get("open_widgets") or []), (_st.get("recent_widgets") or [])
    except Exception:
        return [], []


def _identify_ctx(rt, query: str) -> str | None:
    """`rt.identify(query, open_ids, recent_ids)['match']` with state context — the resolver with the same
    open>recent>catalogue narrowing used by voice. `rt` is the `widgets.runtime` module already imported by the caller."""
    _o, _r = _ctx_ids()
    return (rt.identify(query, open_ids=_o, recent_ids=_r) or {}).get("match")


def _show_target(text: str, context: list[dict] | None = None, last_action: str = "") -> str | None:
    """Same criterion as `providers/nucleo.py::_show_guard_target` (PARALLEL implementation — keep in sync): a
    SHOW verb + NO create + `runtime.identify` resolves an existing widget → the real turn converts it to show."""
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


# Extraído de `probe.py` en la pasada del trinquete (2026-09-02). Vive aquí porque es donde un lector ya lo
# buscaba: `delivery.py` lo nombra «show_target._running_goals» desde antes de que estuviera aquí.
def _running_goals() -> list[str]:
    """The goals of the errands actually IN FLIGHT right now — what a new request has to be compared against.

    `has_active()` answers whether anything is running; this answers WHAT. Best-effort: an unreadable registry
    returns [], and `nothing_running_for` treats «cannot tell» as «assume it is this one», so a failure here
    keeps the old conduct rather than escalating twice.
    """
    try:
        from nucleo import dispatch as _disp_g
        return [str(r.get("request") or "") for r in _disp_g.pending_summaries()]
    except Exception:
        return []


def classify_alias_call(tool_calls: list, text: str) -> str:
    """V2-082, moved here from `probe.py`'s branch (ratchet, 2026-09-03, V2-567): the probe only CLASSIFIES
    alias management (the provider is the one that writes manifests) — resolve the widget and report
    `alias:add|remove:id`, or `clarify` when no widget can be located with certainty."""
    _ma = next(t for t in tool_calls if t["name"] == "manage_widget_alias")
    op = "remove" if str(_ma["args"].get("op") or "add").lower().startswith(("rem", "quit", "borr")) else "add"
    try:
        from widgets import runtime as _rta
        awid = (_ma["args"].get("widget_id") or "").strip()
        rid = awid if (awid and _rta.get(awid) is not None) else (_identify_ctx(_rta, awid or text) or "")
    except Exception:
        rid = ""
    return f"alias:{op}:{rid}" if rid else "clarify"
