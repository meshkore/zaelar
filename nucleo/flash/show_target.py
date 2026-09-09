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


def show_instance(rid: str, text: str = "", last_spoken: str = "") -> tuple[str, str, str]:
    """WHICH CARD of `rid` a «enséñamelo» means → `(id_to_show, question, chosen_label)`.

    The SAME decision the voice channel takes in `providers/widget_intent._show_target_instance`, single-sourced
    in `widgets/instances.resolve_show`; what lived here was the plumbing around it, written twice. V2-605 gave
    that decision a third input (`last_spoken`, so the same question is never asked twice) and a third output
    (which card we had to choose when the operator had already been asked and still did not pick) — a shape
    change is exactly when two hand-copied call sites drift, and this channel is the one that historically gets
    left behind (V2-176, V2-252, V2-539).

    Fail-soft to «show the base, as always»: an unreadable canvas must not invent an ambiguity mid-turn.
    """
    try:
        from server.voice_api import open_instances
        from widgets import instances as _inst
        out = _inst.resolve_show(rid, open_instances(), text, last_spoken)
    except Exception:  # noqa: BLE001
        return rid, "", ""
    if out.get("ask"):
        return "", str(out["ask"]), ""
    return str(out.get("id") or rid), "", str(out.get("chose") or "")


def last_assistant_line(window) -> str:
    """The last thing THIS channel said — the probe's equivalent of the voice provider's `_last_spoken`."""
    return next((str(m.get("content") or "") for m in reversed(list(window or []))
                 if (m or {}).get("role") == "assistant"), "")


def show_card(rid: str, text: str = "") -> str:
    """The CARD id a backstop should show — narrows a base to its live instance, never asks (V2-605 F2).

    The asking door is `show_instance`; this is for the deterministic backstops, which have no conversation to
    hold. Fail-soft to the base: an unreadable canvas must not change what a backstop shows.
    """
    try:
        from server.voice_api import open_instances
        from widgets import instances as _inst
        return _inst.show_id(rid, open_instances(), text)
    except Exception:  # noqa: BLE001
        return rid


def fullscreen_target(widget_id: str, text: str = "") -> str:
    """WHICH card a `fullscreen_widget` call means — ONE decision, read by both channels (V2-252).

    Order of resolution: the id the model gave (exact, then `identify` over it or the turn text), and finally
    **the card that IS at full screen right now**, reported by the canvas in `state.maximized_widget`.

    That last step is the whole point (V2-609). `widget_id` used to be REQUIRED and «sal de pantalla
    completa» names no widget, so the model had nothing legal to pass — and instead of asking, it answered
    «Hecho.» having emitted no tool at all (measured live 2026-09-07 18:54:27; the engine's own friction
    detector logged «data-op fantasma» and was in cooldown). The operator's point is exactly right: with one
    card at full screen, the target is not ambiguous, it is *obvious* — and the canvas already knew it. A
    verb whose object the system can see and the model cannot is a verb the model will decline to use.

    Returns "" when nothing resolves. Deliberately never falls back to "the only open widget": leaving full
    screen when nothing is at full screen would TOGGLE a card INTO it — the exact opposite of the order.
    """
    rid = (widget_id or "").strip()
    try:
        from widgets import runtime as rt
    except Exception:
        return rid
    if rid:
        # He named something: exact id, else resolve THAT name. Never the turn text — see below.
        try:
            if rt.get(rid) is not None:
                return rid
            m = _identify_ctx(rt, rid) or ""
            if m and rt.get(m) is not None:
                return m
        except Exception:
            pass
        return ""
    # No name given. `identify` over the TURN TEXT would answer here — with one card open it narrows to
    # that card and «sal de pantalla completa» resolves to it happily (verified: it does). That is the one
    # answer this function must never give: nothing is at full screen, so toggling that card would put it
    # INTO full screen — the exact opposite of the order, on the operator's own most common canvas. An
    # empty argument means «the one that is at full screen» and nothing else; when there is none, the
    # honest result is nothing, and the caller asks.
    try:
        from memory import api as _memapi
        maxw = str(((_memapi.state() or {}).get("maximized_widget") or "")).strip()
        if maxw and rt.get(maxw) is not None:
            return maxw
    except Exception:
        pass
    return ""


def fullscreen_dispatch(args: dict, text: str, tag_emit, emit, deduped: dict) -> None:
    """The provider's whole `fullscreen_widget` branch body (extracted paying the architecture ratchet,
    V2-635): resolve the card (V2-609, above) and route by what the turn actually SAYS. Measured 2026-09-09
    (session 34386d8f): «Johnny pausa el vídeo» became fullscreen (pure drag — no screen-size words at all),
    and «minimiza el vídeo» became fullscreen TWICE, because the toggle was the only route and on a
    non-maximized card the toggle does the exact opposite. Shrink orders now ride the canvas `minimize`
    event (desktop.shrink: exit fullscreen → restore maximize → rail chip); a call licensed by nothing is
    discarded and counts as handled (`deduped`) — same posture as stop_worker's GUARD 2."""
    from nucleo.flash import canvas_license as _lic
    verdict = _lic.fullscreen_license(text)
    if not verdict:
        emit("brain", "🛡️ fullscreen_widget ignorado — el turno no habla de tamaño de pantalla (context-bleed)",
             text=(text or "")[:120], role="system",
             extra={"cat": "flash", "kind_diag": "fullscreen_without_order"})
        deduped["v"] = True
        return
    rid = fullscreen_target((args.get("widget_id") or "").strip(), text)
    if not rid:
        return
    if verdict == "minimize":
        tag_emit("minimize", {"id": rid})
        emit("brain", "⤵️ fullscreen_widget con orden de ENCOGER → canvas minimize", text=rid, role="system")
        return
    tag_emit("show", {"id": rid})     # por si no estaba abierto todavía
    tag_emit("fullscreen", {"id": rid})
    emit("brain", "⛶ fullscreen_widget → canvas", text=rid, role="system")
