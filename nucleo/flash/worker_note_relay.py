"""nucleo/flash/worker_note_relay.py — a progress note on a LIVE errand's sheet is the worker's: his words go there.

search-buy-watch EN (2026-10-14). «the King Seiko hi-beat sounds good, same check though — running and real photos. if
it looks clean and well kept I'm in» — a conditional yes, the purchase hanging on a check. The turn's call was
`results:progress {state: "checking the King Seiko 5626-7041 Hi-Beat…"}`: a line in the SUMMARY tab of the sheet the
worker fills. The worker was never told, and the text channel said «Done.» — to a man waiting to hear whether his
watch passed.

`progress` is how a WORKER reports where it is (the sheet's own manifest: «Actualiza el SUMARIO»); the turn has no
progress of its own to report on an errand somebody else is running. So when the turn writes one on the sheet of a
live errand, the call is what it meant — his words, for that errand — and it is sent there, through the same
injection `send_to_worker` uses. What is said is what happens next: the errand checks it and he hears back. Every
other op, and a progress note on a sheet no live errand owns, runs as before.
"""
from __future__ import annotations

#: The sheet ops that only the worker running the errand writes.
_WORKER_OPS = frozenset({"progress"})


def owner(widget_id: str, action: str) -> dict | None:
    """The live errand whose sheet this worker-only op would write on, or None."""
    wid = str(widget_id or "").strip().lower()
    if str(action or "").strip() not in _WORKER_OPS or wid.split("::", 1)[0] != "results":
        return None
    from nucleo import dispatch as _disp
    live = [t for t in (_disp.pending_summaries() or []) if str(t.get("sheet") or "") and not t.get("waiting_on")]
    if "::" in wid:
        sheet = wid.split("::", 1)[1]
        return next((t for t in live if str(t.get("sheet")).split("::")[-1].lower() == sheet), None)
    return live[0] if len(live) == 1 else None      # the bare sheet: only when one errand can be meant


def relay(widget_id: str, action: str, operator_text: str) -> list[str]:
    """Send his words to the errand that owns this op's sheet. The errand's spoken name(s), or [] when the op is not
    one to relay (it then runs as before). Never raises."""
    try:
        t = owner(widget_id, action)
        words = str(operator_text or "").strip()
        if not t or not words:
            return []
        from nucleo import dispatch as _disp
        from nucleo.turn import named_errand as _ne
        _disp.inject_soon(str(t["id"]), words)
        rec = _disp.get_record(t["id"])
        name = _ne.spoken_name({"label": getattr(rec, "label", ""), "title": getattr(rec, "title", ""),
                                "request": t.get("request")})
        _emit(widget_id, action, str(t["id"]))
        return [name] if name else []
    except Exception as e:  # noqa: BLE001 — the op then runs as it would have
        __import__("logging").getLogger(__name__).warning("worker_note_relay failed: %s", e)
        return []


def line_for(names: list[str]) -> str:
    """What he hears: the errand checks it first and he is told what it finds. "" without a name."""
    names = [n for n in names or [] if str(n or "").strip()]
    if not names:
        return ""
    from i18n import langs as _lg
    return _lg.current_language().errand_relayed_next.format(what="; ".join(f"«{n}»" for n in names[:3]))


def line(parte: dict) -> str:
    """The sentence a text-channel data-op owes when one of its ops was relayed ("" when none was)."""
    ops = (parte or {}).get("ops") if isinstance(parte, dict) else None
    return line_for([n for op in ops or [] for n in (op.get("relayed_to") or [])])


def voice_line(acts) -> str:
    """The voice channel's version, from the cards this turn touched (`canvas_focus.this_turn_acts`)."""
    for card, kind, action in acts or []:
        if kind == "control" and (t := owner(card, action)):
            from nucleo.turn import named_errand as _ne
            return line_for([_ne.spoken_name({"request": t.get("request")})])
    return ""


def _emit(widget_id: str, action: str, to: str) -> None:
    try:
        from voice.observer import emit
        emit("brain", "↪️ a progress note on a live errand's sheet goes to its worker", role="system",
             extra={"cat": "flash", "id": widget_id, "action": action, "to": to})
    except Exception as e:  # noqa: BLE001
        __import__("logging").getLogger(__name__).debug("worker_note_relay emit failed: %s", e)
