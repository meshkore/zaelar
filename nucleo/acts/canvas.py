"""The canvas door: every card the engine shows or closes on his screen crosses `apply` (refactor2710-04 T-02).

A writer names the act, the card and its provenance (`src`, the closed set of `nucleo.canvas_arbiter`): the model's
turn (`flash`), a backstop, a worker or a task's wall, the action map, the system. For a show or a close the arbiter
judges it first — provenance, then the turn's paid verdict, then the declared leaves — and its verdict is emitted
armed (`arbiter`, with `verdict` and `source`). A vetoed act never reaches the canvas and `apply` says so; an allowed
one is the `widget` event the canvas obeys. Other ops (move, minimize, fullscreen, arrange, data logs) pass through
the same door unjudged, so there is one writer either way.
"""
from __future__ import annotations

from nucleo import canvas_arbiter as _arb

#: The ops the arbiter licenses; every other op crosses the door as it is.
JUDGED = ("show", "close")


def apply(op: str, wid: str = "", *, src: str, text: str = "", role: str = "", request: dict | None = None,
          emit=None, **extra) -> bool:
    """Put `op` on `wid` if the arbiter allows it; True when the canvas was told. `wid=""` closes every card.
    `request` is the turn the act belongs to (`canvas_arbiter.request_of` from a door that holds it), else the one
    the observer stream assembled (`request_for`). `emit` is the caller's stream (the observer by default)."""
    op = (op or "").strip().lower()
    fields = ({"id": wid} if wid else {}) | {"src": src} | extra
    if op in JUDGED:
        req = request if request is not None else _arb.request_for(extra)
        v = _arb.decide(op, wid, src, action=str(extra.get("action") or ""), **req)
        _arb._emit_verdict(op, wid, src, str(extra.get("action") or ""), v, shadow=False, brief=req.get("verdict"))
        if not v.allow and v.rule != "arbiter-error":     # an arbiter that broke fails open, its verdict on record
            return False
    if emit is None:
        from voice.observer import emit
    with _arb.judged():
        emit("widget", op, **({"text": text} if text else {}), **({"role": role} if role else {}), extra=fields)
    return True


def resolve(wid_arg: str, text: str, window, last_action, guard_target) -> tuple:
    """Which card a show means — the model's id, the guard's target or what his words name."""
    from nucleo.flash import show_target
    return show_target.resolve_show(wid_arg, text, window, last_action, guard_target)
