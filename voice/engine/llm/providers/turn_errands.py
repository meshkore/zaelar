"""The voice turn's EXTRA errands — the second and third of one sentence — and the one it could not start.

Moved out of `turn_after.close_the_turn` (three-tasks-at-once, 2026-10-10), which sat at its size ceiling: the
create-widget backstop and the loop over `escalate_req["more"]` are the same code, with the names they read from
the provider passed in. What is new is the last step: an errand the worker pool could not take this turn
(`escalate_req["dropped"]`, recorded by the executor's cap and by the listing that rides) is SAID, in his
language (`nucleo/turn/errands_of_a_turn.not_started_line`) — the text channel says the same sentence.
"""
from __future__ import annotations

from loguru import logger

from nucleo.turn import errands_of_a_turn as _eot


def launch_the_rest(escalate_req: dict, req: str, *, _op_text: str, prev_pending, router, escalate, similar_pending,
                    emit, spoken_text: str, send, speech) -> str:
    """Launch the turn's additional errands after its main one; return the not-started sentence it said ("")."""
    # The ADDITIONAL errands of the same turn (V2-118). They go AFTER the main one and only if it survived: the
    # guards above clear `v` when the turn turns out not to be an errand (a show, a close, an answer to a worker),
    # and then the others were not errands either. Each goes through the SAME dedup as the main one — two similar
    # requests are injected into the one already running instead of opening a second session of the same thing.
    # CREATE-WIDGET BACKSTOP (V2-118 round 2, measured): of three errands, one was «móntame un widget de un juego»;
    # the model called the tool once, for the report, and the task registry of that run held NO `code` task in 14
    # turns while the turn said it was loading a platform game. The create-widget guard only covered a turn that
    # fired NOTHING; here it covers the turn that escalated something else, with the same deterministic
    # classifier, and only when none of the outgoing requests is already a create-widget one.
    # V2-155: what is added is the CLAUSE that asks for the widget, never the whole turn — with «informe» inside,
    # the dedup gave it the report's target widget and ate it by its strongest signal
    # (`router_guards.create_widget_request` has the measurement).
    _w_req = (router.create_widget_request(_op_text)
              if not any(router.looks_like_create_widget(r)
                         for r in [req, *escalate_req["more"]]) else "")
    if _w_req:
        escalate_req["more"].append(_w_req)
        emit("brain", "🏗️ crear-widget del mismo turno, sin lanzar → escalada añadida (backstop)",
             text=_w_req[:120], role="system", extra={"cat": "flash"})

    _launched = list(prev_pending) + [{"request": req}]
    for _extra_req in escalate_req["more"]:
        try:
            if similar_pending(_extra_req, _launched):
                from nucleo import dispatch as _disp4
                _disp4.inject_soon(_extra_req, _extra_req)
                emit("brain", "↪️ tarea adicional → inyección a worker vivo", text=_extra_req, role="system")
            else:
                escalate(
                    _extra_req,
                    context={"src": "voice", "surface": escalate_req["surface"].get(_extra_req, ""),
                             "asked": spoken_text})
                emit("brain", "🧭 Flash → Brain Worker (tarea adicional del mismo turno)",
                     text=_extra_req, role="system")
            _launched.append({"request": _extra_req})
        except Exception as _e_more:  # noqa: BLE001
            logger.warning(f"an additional escalation failed (the others go on): {_e_more}")

    line = _eot.not_started_line(escalate_req.get("dropped") or [])
    if line:
        send(speech.sanitize(line, drop_metadata=False))
        emit("brain", "🚫 errands this turn did not start (worker pool)", text="; ".join(escalate_req["dropped"])[:200],
             role="system", extra={"cat": "flash", "not_started": list(escalate_req["dropped"])})
    return line
