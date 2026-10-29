"""What the turn's verdict says about the CANVAS: a sure open/close, the cards it names, the one on screen now.
Moved from `nucleo/flash/direct_action.py` (refactor2710-05 T-04); its names are read through `_da`."""
from __future__ import annotations

from nucleo.flash import direct_action as _da


def sure_canvas(brief) -> str:
    """The canvas gesture this turn SURELY asks for — close, minimize, fullscreen, exit_fullscreen — or ""."""
    try:
        from nucleo.turn import brief as _tb, verdicts as _v   # the ONE veto floor, not a private 0.9 (2.930)
        verb, _info = _tb.read(brief, _tb.CANVAS_KEY, "", min_confidence=_v.VETO)
        v = str(verb or "")
        return v if v in ("close", "minimize", "fullscreen", "exit_fullscreen", "arrange") else ""
    except Exception:  # noqa: BLE001
        return ""


def show_owed(brief, card: str) -> bool:
    """A sure `canvas = show` with a card the verdict names: an order to SHOW it, whether or not the model called (CRIT-K2)."""
    try:
        from nucleo.turn import brief as _tb, verdicts as _v   # the ONE veto floor, not a private 0.9 (2.930)
        verb, _info = _tb.read(brief, _tb.CANVAS_KEY, "", min_confidence=_v.VETO)
        return bool(card) and str(verb or "") == "show"
    except Exception as e:  # noqa: BLE001 — an unreadable verdict owes nothing
        __import__("logging").getLogger(__name__).debug("show verdict unreadable: %s", e)
        return False


def named_cards(operator_text: str) -> list[str]:
    """Every card his words NAME (alias or name, never context) — «the calendar and the messages» is two, and so is
    «cierra la agenda y los mensajes», where `identify` picks one match and the other candidate is called by its
    catalogue NAME (`naming.says_the_name`, demo sandbox 2026-10-29 C6: only the messages, not open, were read)."""
    try:
        from widgets import naming as _naming, runtime as _rt
        res = _rt.identify(operator_text or "") or {}
        if res.get("by_context"):
            return []
        cands = res.get("candidates") or []
        top = max((float(c.get("score") or 0) for c in cands), default=0.0)
        out = [str(res["match"])] if res.get("match") else [
            str(c["id"]) for c in cands if top > 0 and float(c.get("score") or 0) == top] if res.get("ambiguous") else []
        return out + [str(c["id"]) for c in cands if str(c["id"]) not in out and _naming.says_the_name(operator_text, c["id"])]
    except Exception:  # noqa: BLE001
        return []


def _open_now() -> list[str]:
    try:
        from server.voice_api import open_instances
        return [str(i) for i in open_instances() if str(i)]
    except Exception:  # noqa: BLE001
        return []


def complete_canvas(brief, *, tag_emit, emit, operator_text: str = "") -> str:
    """The model called NOTHING and the brief SURELY names a canvas gesture: do that gesture on the card the
    turn is about (the verdict's card, else the card his last turn acted on, else the only one open), through
    the same tag funnel the model's own calls use. Returns the gesture, or "". Never raises.

    Demo pass 2026-09-28: R4 «ok close the calendar» and V3 «can you make it bigger, like full screen» were both
    answered as done («calendar's closed», «it's full screen now») with nothing called."""
    from nucleo.flash import card_close as _ccl   # the body lives with the other close readers (V2-781)
    return _ccl.run_gesture(brief, tag_emit=tag_emit, emit=emit, operator_text=operator_text)


def catalogue_names(widget_id: str) -> list[str]:
    from widgets import naming as _naming
    return _naming.catalogue_names(_da._base_of(widget_id))


def _says_the_name(operator_text: str, widget_id: str) -> bool:
    from widgets import naming as _naming
    return _naming.says_the_name(operator_text, _da._base_of(widget_id))


def closes_the_named_card(brief, operator_text: str, done_ops, *, floor: float = 0.75) -> str:
    """The card to close AFTER the model's own data-op, or "".

    Demo pass 2026-09-28 (V7, twice): «ok stop the video and close youtube» ran `youtube:close` — which empties
    the player, as its manifest says — and the card stayed open, hiding every card after it. Two orders, one call.
    The verdict alone cannot tell them apart: Jev reads «close the video» (the player's content, V2-753) and
    «close youtube» (the card) both as canvas=close. What does is whether his words call the card by what it is
    CALLED (`catalogue_names`), in any language the catalogue has — «close the video» names only what it holds."""
    try:
        from nucleo.turn import brief as _tb
        verb, _info = _tb.read(brief, _tb.CANVAS_KEY, "", min_confidence=floor)
        if str(verb or "") != "close":
            return ""
        from nucleo.flash import show_target as _st
        open_now = _da._open_now()
        for wid, _action in (done_ops or []):
            if _da._says_the_name(operator_text, wid):
                target = _st.close_target(wid)
                if target and target in open_now:
                    return target
        return ""
    except Exception:  # noqa: BLE001
        return ""


def close_op_is_the_card(brief, action: str) -> bool:
    """A data-op NAMED «close» over a SURE close verdict is the card's own close, never its data.

    Demo passes 36/42 (2026-09-29, E5): «close my mail» — the model called the messaging card's `close` (a view
    action: back to the chat list), the canvas verdict read `close` sure, and the card stayed on screen while the
    reply said the mail was closed. `complete` already refuses a data action under a sure canvas gesture; this is
    the same rule for the model's OWN call, read by the door every data-op goes through."""
    return str(action or "").strip().lower() == "close" and _da.sure_canvas(brief) == "close"


def on_screen_now(widget_id: str) -> bool:
    """Whether the card is in front of him NOW — open by the canvas report, or brought by THIS turn. The report
    comes from the browser and lags the turn that presents a card: full17 M1 «show me the chart» opened it and the
    answer said «I can't pull up the chart itself here» over it, because the report still said closed."""
    base = str(widget_id or "").split("::", 1)[0].strip().lower()
    try:
        from nucleo.flash import canvas_visibility as _cvis
        if _cvis.is_open(base):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        from nucleo import canvas_focus as _cf
        return base in _cf.this_turn_cards()
    except Exception:  # noqa: BLE001
        return False
