"""The canvas door: every card the engine shows or closes on his screen crosses `apply` (refactor2710-04 T-02).

A writer names the act, the card and its provenance (`src`, the arbiter's closed set). A show or close is judged by the
arbiter first and its verdict emitted armed (`arbiter`, with `verdict` and `source`); a veto never reaches the canvas
and `apply` says so. Other ops cross the same door unjudged, so there is one writer either way.
"""
from __future__ import annotations

from nucleo.acts import canvas_arbiter as _arb, canvas_turn as _turn
from voice import canvas_src

#: The ops the arbiter licenses; every other op crosses the door as it is.
JUDGED = ("show", "close")


def apply(op: str, wid: str = "", *, src: str, text: str = "", role: str = "", request: dict | None = None,
          emit=None, **extra) -> bool:
    """Put `op` on `wid` if the arbiter allows it; True when the canvas was told. `wid=""` closes every card.
    `request` is the turn the act belongs to (`canvas_turn.request_of` from a door that holds it), else the one
    the observer stream assembled (`canvas_turn.request_for`). `emit` is the caller's stream (the observer by default)."""
    op = (op or "").strip().lower()
    fields = ({"id": wid} if wid else {}) | {"src": src} | extra
    if op in JUDGED:
        req = request if request is not None else _turn.request_for(extra)
        v = _arb.decide(op, wid, src, action=str(extra.get("action") or ""), **req)
        _turn._emit_verdict(op, wid, src, str(extra.get("action") or ""), v, shadow=False, brief=req.get("verdict"))
        # an arbiter that broke fails open; a REPORT of what the screen already did is recorded, judged, never held
        if not v.allow and v.rule != "arbiter-error" and not canvas_src.is_report(src):
            return False
    if emit is None:
        from voice.observer import emit
    with _turn.judged():
        emit("widget", op, **({"text": text} if text else {}), **({"role": role} if role else {}), extra=fields)
    return True


def resolve(wid_arg: str, text: str, window, last_action, guard_target) -> tuple:
    """Which card a show means — the model's id, the guard's target or what his words name."""
    from nucleo.flash import show_target
    return show_target.resolve_show(wid_arg, text, window, last_action, guard_target)


def close_ordered(text: str, *, brief=None, called: bool = False, handle=None) -> tuple[bool, str]:
    """Does this turn ORDER a close? `(ordered, source)` — the one close licence (refactor2710-04b T-01).

    His words (never our `[SISTEMA]` notes) are read by the close grammar, and the turn's paid brief completes it:
      · a close verb orders it, unless the brief reads a NEGATION of it — a sure `canvas=neither` beside a sure
        `request_type` that is neither order nor answer («yo no te he dicho que cerraras el vídeo», CRIT-K8c);
      · a negated or narrated close («no lo cierres», «you closed it») never orders one, whatever a model says;
      · his answer to OUR «which one should I close?» carries that question's licence («Las dos.»);
      · when the model `called` a close, a sure `canvas=close` read from `handle` (the brief) forgives a grammar miss.
    `source` is grammar | verdict | answer | jev | none, so the trail says which reader moved."""
    from nucleo.flash import canvas_license as _lic, close_answer as _ca, close_guards as _cg
    his = _lic._his_words(text)
    if _cg.looks_like_close(his):
        return (False, "verdict") if brief is not None and _denies_close(brief) else (True, "grammar")
    if _cg.is_negated_or_narrated(his):
        return False, "none"
    if _ca.answers(brief):
        return True, "answer"
    if called:
        from nucleo.flash import show_target as _st
        verb, info = _st.resolve_canvas_verb(handle)
        if verb == "close" and (info or {}).get("used"):
            return True, "jev"
    return False, "none"


def _denies_close(brief) -> bool:
    """A sure `canvas=neither` alone is no negation (the verdict can miss the canvas half of an order); with a sure
    reading of the turn as something other than an order or an answer it is (V2-812 T-05)."""
    try:
        from nucleo.flash import turn_brief as _tb
        verb, _info = _tb.read(brief, _tb.CANVAS_KEY, "")
        if str(verb or "") != "neither":
            return False
        kind, kinfo = _tb.read(brief, _tb.REQUEST_KEY, "")
        return bool(kinfo and kinfo.get("used")) and str(kind or "") not in ("order", "answer")
    except Exception as e:  # noqa: BLE001 — an unread brief is no negation: the close the grammar saw stands
        from loguru import logger
        logger.debug(f"canvas.close_ordered: brief unread — {e}")
        return False
