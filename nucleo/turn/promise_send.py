"""The voice turn's end for a promise (split from `promise_kept`, V2-831 audit A10b): a deferred errand started, else
the honest line said by the mouth; and the one act a reply must never claim unseen — a send («nothing has gone out»,
V2-831 R11/R11b)."""
from __future__ import annotations

from loguru import logger as _log

from nucleo.turn.promise_kept import CANNOT, _LATE, _base, close
from nucleo.turn.promise_errand import an_errand_was_reached, start_deferred


def say_after(reply: str, data_done: dict, *, acted, send, speech, window: list, emit, turn=None) -> str:
    """The voice turn end: a deferred promise's errand started, else the honest line, said by the mouth
    (`nucleo/turn/reply.py`, verdict `cannot` or `unmet`) after what streamed and kept in the dialog window.
    `turn` = `(brief, model_calls, op_text, escalate)` of the voice turn, or None."""
    outcome = data_done.setdefault("promise", {}) if isinstance(data_done, dict) else None
    brief = turn[0] if turn else None
    acted = acted or an_errand_was_reached()
    if turn and start_deferred(reply, outcome, acted=bool(acted), brief=brief, model_calls=turn[1], op_text=turn[2],
                               escalate=turn[3], emit=emit):
        return ""
    ops = (data_done or {}).get("ops")
    if not (line := close(reply, outcome, acted=bool(acted), emit=emit, brief=brief) or unsent_line(brief, ops)):
        reply_promised_a_send(reply, brief, ops)
    if line:
        from nucleo.turn import reply as _reply
        verdict = "cannot" if str((outcome or {}).get("kind") or "") == CANNOT else "unmet"
        _reply.speak([_reply.Outcome(verdict, "turn", "promise", said=line)], (reply or "").strip(), send, speech)
        if window and window[-1].get("role") == "assistant":
            window[-1]["content"] = (str(window[-1].get("content") or "") + " " + line).strip()
    return line


def _nothing_sent(ran_ops) -> bool:
    """No op declaring `external.send` ran, no send door or errand was reached, no confirm this turn opened."""
    from nucleo import consequence
    from voice import trace
    from widgets import confirm, effects
    return not (consequence.reached("messaging.tag", "cluster.send", "architect.send", "worker.spawn", "worker.inject")
                or any(effects.carries(w, a, effects.EXTERNAL_SEND) for w, a in (ran_ops or ()))
                or any(p.get("trace_id") == trace.current() for p in confirm.pending().values()))


def _send_line() -> str:
    from i18n import langs
    return str(getattr(langs.current_language(), "send_not_done", "") or "").strip()


def unsent_line(brief, ran_ops=()) -> str:
    """«Nothing has gone out» when the brief is SURE the turn sends for him (`errand_class`), the turn owes an act (a
    remember is not one) and nothing that sends ran — facts, never the reply (V2-831 R11). "" otherwise. Never raises."""
    try:
        from nucleo.acts import errand
        from nucleo.turn import reply as _reply, verdicts
        cls, info = verdicts.read(brief, errand.CLASS_KEY, "", min_confidence=verdicts.VETO)
        sure = cls == "sends_for_him" and (info or {}).get("used") and _reply.owes_an_act(brief)
        return _send_line() if sure and _nothing_sent(ran_ops) else ""
    except Exception as _e:  # noqa: BLE001 — an unreadable turn claims nothing
        _log.debug(f"promise_kept: unsent unreadable: {_e!r}")
        return ""


def _can_send(open_ids=None) -> bool:
    """A messaging connector is on, or a card on screen declares an act that sends (`external.send`)."""
    from config import connectors
    from widgets import effects, runtime
    if any(connectors.enabled(p) for p in connectors._ENABLED_ENV):      # the messaging connectors config declares
        return True
    if open_ids is None:
        from nucleo.flash import canvas_visibility
        open_ids = canvas_visibility.open_ids()
    return any(effects.carries(w, a, effects.EXTERNAL_SEND) for w in {_base(i) for i in open_ids or ()}
               for a in ((runtime.get(w) or {}).get("actions") or {}))


def reply_promised_a_send(reply: str, brief, ran_ops=(), *, open_ids=None):
    """A turn that owes an order, can send and sent nothing asks ONE closed question over OUR reply, in the background:
    does it promise a send? «yes» → «nothing has gone out», as the turn's follow-up (R11b). The task, or None."""
    try:
        from nucleo.turn import reply as _reply
        if not (reply or "").strip() or _reply.owes_an_act(brief) != "order" or not _nothing_sent(ran_ops) \
                or not _can_send(open_ids):
            return None
        import asyncio
        _LATE.add(task := asyncio.get_running_loop().create_task(_ask_the_reply(reply)))
        task.add_done_callback(_LATE.discard)
        return task
    except Exception as _e:  # noqa: BLE001 — no loop or no state: nothing is asked
        _log.debug(f"promise_kept: reply promise not asked: {_e!r}")
        return None


async def _ask_the_reply(reply: str) -> str:
    import asyncio
    from nucleo import jev
    from nucleo.turn import brief as tb, verdicts
    out = await asyncio.to_thread(jev.choose_many_sync, reply, {tb.PROMISE_KEY: {
        "instructions": tb.PROMISE_INSTRUCTIONS, "criteria": dict(tb.PROMISE_CRITERIA)}}, question_id="reply-promise")
    v = (out or {}).get(tb.PROMISE_KEY) or {}
    if v.get("choice") != "promises_a_send" or float(v.get("confidence") or 0.0) < verdicts.VETO or not (line := _send_line()):
        return ""
    from nucleo.flash import follow_up_pass
    follow_up_pass.deliver(line)
    return line
