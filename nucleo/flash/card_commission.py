"""card_commission.py — a commission that names one of OUR cards is a read or a declared call before it is a
worker; and a read the verdict says to SHOW brings its card (V2-773, the demo's final pass).

Two measured turns on the operator's live engine, 2026-09-26, both on the calendar with the agenda CLOSED:

  · «Find me a free 45-minute slot tomorrow afternoon to talk with Ethan» — the catalogue verdict named the
    agenda (0.79 after its description learnt to say «huecos libres»), the model called `escalate`, and a
    Brain Worker spent three minutes on a question the card answers in one read. The two rungs before it
    (`direct_action.take_rung`, the act-repair pass) only see a card named through `screen_action`, which
    exists only while the card is OPEN.
  · «Show me that time in my calendar» — the model READ the agenda and answered in words; the canvas verdict
    had said `show` (0.74) and the card he asked to see stayed closed.

Both are the same shape as V2-741: the engine had paid for a verdict and then let the expensive path run. The
decision here is the model's, with the card in front (`act_repair.call_or_read_for_commission`): it may call a
declared action, read the card, or call nothing — and nothing keeps today's path, the worker. Extracted from
the voice provider for the reason the architecture ratchet keeps giving: that file grows only by extraction.
"""
from __future__ import annotations

from typing import Callable


async def before_worker(escalate_req: dict, read_req: dict, *, brief, operator_text: str, spec, emit,
                        present: Callable, apply_widget_data: Callable) -> str:
    """Try the card the catalogue verdict names. Returns "call", "read" or "" (the worker keeps the errand).

    The caller owns the precondition — a commission survived every guard and nothing in the turn acted — and
    the two rungs before this one found no OPEN card. Never raises: a second pass never breaks a turn."""
    try:
        from nucleo import danger as _danger
        from nucleo.flash import act_repair as _repair, build_decision as _bd
        card = _bd.named_card(brief)
        if not card or _danger.is_dangerous(operator_text):
            return ""
        # Any card the verdict names may take the CALL; the read half is offered only to one that can answer.
        got = await _repair.call_or_read_for_commission(operator_text, str(escalate_req.get("v") or ""), card,
                                                        spec=spec)
        if not got:
            return ""
        if got["kind"] == "call":
            present(got["widget_id"], reason="turn-order", src="flash", emit=emit)
            apply_widget_data(got["widget_id"], got["action"], got["payload"])
            escalate_req["v"], escalate_req["more"] = None, []
            emit("brain", "🎯 acción declarada en vez de un worker (la tarjeta del catálogo)",
                 text=f"{got['widget_id']}:{got['action']}", role="system",
                 extra={"cat": "flash", "widget": got["widget_id"], "action": got["action"]})
            return "call"
        if got["kind"] == "read":
            if read_req.get("v") is None:
                read_req["v"] = {"widget_id": got["widget_id"], "question": got["question"]}
            escalate_req["v"], escalate_req["more"] = None, []
            emit("brain", "🎯 lectura de la tarjeta en vez de un worker",
                 text=f"{got['widget_id']} ← {got['question'][:100]}", role="system",
                 extra={"cat": "flash", "widget": got["widget_id"], "question": got["question"][:200]})
            return "read"
    except Exception:  # noqa: BLE001
        pass
    return ""


def present_if_show(read_req: dict, *, brief, operator_text: str, is_open: Callable, present: Callable,
                    emit) -> bool:
    """A read whose turn the verdict reads as «canvas: show», over a CLOSED card, brings the card through the
    one door. A question with no show in it («when is the dentist?») stays a read. True when presented."""
    try:
        from nucleo.flash import turn_brief as _tb, widget_read as _wread
        wid = _wread.resolve(str((read_req.get("v") or {}).get("widget_id") or ""), operator_text)
        if not wid or is_open(wid):
            return False
        if _tb.read(brief, _tb.CANVAS_KEY, "neither")[0] != "show":
            return False
        return bool(present(wid, reason="turn-order", src="flash", emit=emit))
    except Exception:  # noqa: BLE001
        return False


async def after_show(acted: dict, *, brief, operator_text: str, spoken_text: str, spec, emit, present: Callable,
                     apply_widget_data: Callable) -> bool:
    """The turn SHOWED a card and said it would do something on it — the show is not the act (V2-773, email
    block). Two measured turns: «Show me only the emails from today that need my attention» opened the messaging
    card from the catalogue and promised «let me pull your inbox up and flag what needs you» — no `show_view`;
    «Open the most important one» over the open card had its spurious `escalate` turned into a show the door
    suppressed («already open»), the reply said «Opening that one now», and nothing opened. Both had the card
    in front and a promise (or a verdict naming the action); one pass asks for the call. True when a call ran."""
    try:
        from nucleo import danger as _danger
        from nucleo.flash import act_repair as _repair, clarifying as _cl, direct_action as _da, router as _router
        wid = str(acted.get("widget_id") or "").strip().lower()
        if not wid or not (spoken_text or "").strip() or _danger.is_dangerous(operator_text):
            return False
        if _cl.asks_for_missing_detail(spoken_text):
            return False
        if not (acted.get("show_suppressed") or _router.promises_action(spoken_text) or _da.names_an_order(brief)):
            return False
        got = await _repair.call_for_promise(operator_text, spoken_text, wid, spec=spec)
        if not got or str(got.get("action") or "") in ("show", "open_widget"):
            return False
        present(got["widget_id"], reason="turn-order", src="flash", emit=emit)
        apply_widget_data(got["widget_id"], got["action"], got["payload"])
        emit("brain", "🔁 abrió la tarjeta y prometió más — la llamada, en una segunda pasada",
             text=f"{got['widget_id']}:{got['action']}", role="system",
             extra={"cat": "flash", "widget": got["widget_id"], "action": got["action"],
                    "suppressed": bool(acted.get("show_suppressed"))})
        return True
    except Exception:  # noqa: BLE001
        return False
