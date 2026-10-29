"""A reply that commits to an act ends in one of three states, in both channels — never in a log line.

The class (V2-790): the model SAYS it will do (or did) something on a card, nothing ran, and only a log line said so —
the repair never opened when no verdict named the card, when a guard discarded the model's own call, or when its
second pass called nothing and told nobody why.

The mechanism, one door shared by the voice turn (`post_stream_acts` + `turn_after`) and the text channel
(`probe_mirrors`):

  1. `card_for_the_repair` — when no verdict names a card: the card of a call the MODEL made this turn that did not
     run (its own declared intent, no wording read), and, only when the decision model gave nothing at all, the
     card his last turn acted on (`canvas_focus`) or the one card open.
  2. The second pass (`act_repair.call_for_promise(..., outcome=)`) may also answer `cannot_do`, in his language.
  3. `honest_line` — at turn end, when nothing ran: the pass's own «I could not», or the i18n `promise_not_kept` line
     when the pass's call was swallowed by a guard or no card could be found for a committing reply.

Owed nothing: a claimed state an op of this request left on screen (V2-792), a turn that settled `asked`, an order
whose act was this turn's memory write, the session's kickoff (V2-831 T-19). Bounded: one second pass per turn, no
loop (the line is words, never a new turn), and a pass that read the words and found no promise is trusted.
"""
from __future__ import annotations

from loguru import logger as _log

#: The non-acting tool the second pass is offered beside `widget_data` (`act_repair.call_for_promise`).
CANNOT_TOOL = {
    "type": "function",
    "function": {
        "name": "cannot_do",
        "description": ("You promised or claimed an act on the card and did NOT do it: give the reason — no_action (none of "
                        "its declared actions does it), missing_detail (one does, a detail is missing), awaits_his_yes (your "
                        "reply already asks him). The engine says it in his language; you write no sentence."),
        "parameters": {"type": "object", "required": ["reason"], "properties": {"reason": {
            "type": "string", "enum": ["no_action", "missing_detail", "awaits_his_yes"]}}},
    },
}

#: The pass's outcomes, as `outcome["kind"]` records them.
CALL, JUDGED, SWALLOWED, CANNOT, STARTED = "call", "judged", "swallowed", "cannot", "started"   # last two: verdicts


def _base(wid) -> str:
    return str(wid or "").split("::", 1)[0].strip().lower()


def verdict_missing(brief) -> bool:
    """The decision model gave this turn NOTHING to read: no brief, one still in flight, or one whose every answer
    failed (an error, or confidence 0). An UNSURE verdict is not missing — it is the model's own path."""
    try:
        from nucleo import jev as _jev
        v = _jev.peek(brief)
        if not v:
            return True
        answers = [a for a in v.values() if isinstance(a, dict)] if isinstance(v, dict) else []
        return not answers or all(str(a.get("error") or "").strip() or not float(a.get("confidence") or 0.0)
                                  for a in answers)
    except Exception:  # noqa: BLE001
        return True


def unrun_model_card(model_calls, ran_ops) -> str:
    """The card of the last `widget_data` call the MODEL made this turn that did not run (a guard's discard does not
    make its card unknown) — "" when none."""
    ran = {(_base(w), str(a or "")) for w, a in (ran_ops or ()) if w}
    for c in reversed(list(model_calls or ())):
        if not isinstance(c, dict) or c.get("name") != "widget_data":
            continue
        args = c.get("args") if isinstance(c.get("args"), dict) else {}
        wid, act = _base(args.get("widget_id")), str(args.get("action") or "")
        if wid and (wid, act) not in ran:
            return wid
    return ""


def card_for_the_repair(brief, *, model_calls=(), ran_ops=(), open_ids=None) -> str:
    """The card the promise repair asks about when no verdict named one. Never raises; "" = no card."""
    try:
        card = unrun_model_card(model_calls, ran_ops)
        if card or not verdict_missing(brief):
            return card
        if open_ids is None:
            from nucleo.flash import canvas_visibility as _cv
            open_ids = _cv.open_ids()
        ids = sorted({_base(i) for i in (open_ids or ()) if _base(i)})
        from nucleo import canvas_focus as _focus
        return _base(_focus.last_turn_card(ids)) or (ids[0] if len(ids) == 1 else "")
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_kept: line 96 failed: {_e!r}")
        return ""


def _not_kept_line(key: str = "") -> str:
    """The i18n line for `key` in the session's language, else `promise_not_kept`. `awaits_his_yes` has none: "" ."""
    try:
        from i18n import langs as _langs
        L = _langs.current_language()
        if key == "promise_cannot_awaits_his_yes":
            return ""
        return str(getattr(L, key, "") or getattr(L, "promise_not_kept", "") or "").strip()
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_kept: line 115 failed: {_e!r}")
        return ""


def honest_line(reply: str, outcome: dict | None, *, acted: bool, brief=None) -> str:
    """The words owed when the turn owed an act and nothing ran — "" when something ran or nothing was owed.

    · the pass declared it cannot  → its own sentence (or the i18n line);
    · the pass's call was swallowed by a guard → the i18n line (a claim over a discarded op is not «done»);
    · the pass read the turn and called nothing → nothing (its judgement stands);
    · settled `asked` (`[[ask]]`, the clarify door) or a live worker resumed (`acted`) → nothing; no pass could run and
      the brief owed an act (`owed`) → the i18n line, unless an order's act was this turn's memory write (`remembered`)."""
    from nucleo.turn import reply as _reply   # `asked`: its `[[ask]]` or the clarify door (V2-831 T-08), never a «?»
    if acted or words_were_the_act(brief) or _reply.asked():
        return ""
    kind = str((outcome or {}).get("kind") or "")
    if kind in (CALL, STARTED, JUDGED):
        return ""
    if kind in (CANNOT, SWALLOWED):     # the pass's declared reason, said from the pack in HIS language (never its text)
        return _not_kept_line(f"promise_cannot_{(outcome or {}).get('reason')}" if kind == CANNOT else "")
    if not owed(brief) or (_reply.owes_an_act(brief) == "order" and _reply.remembered()):
        return ""
    return "" if _reply.owes_an_act(brief) == "order" and _when_memory_settles(_reply) else _not_kept_line()


def _when_memory_settles(_reply) -> bool:
    """The memory door is still filing this order (the distiller outlasted the acts' budget, pass 6 INIT #01): not a fact
    yet. Its line waits — said as the turn's follow-up only if the door filed nothing. False = say it now."""
    try:
        import asyncio
        if _reply.memory_pending():
            _LATE.add(t := asyncio.get_running_loop().create_task(_say_if_nothing_filed(_reply)))
            return bool(t.add_done_callback(_LATE.discard) or True)
    except Exception as _e:  # noqa: BLE001 — no loop to wait on: the line is said now
        _log.debug(f"promise_kept: memory wait unavailable: {_e!r}")
    return False


_LATE: set = set()


async def _say_if_nothing_filed(_reply) -> None:
    import asyncio
    import time
    deadline = time.monotonic() + 30.0       # a wall-clock bound, never an iteration count
    while _reply.memory_pending() and time.monotonic() < deadline:
        await asyncio.sleep(0.1)
    if not _reply.remembered() and (line := _not_kept_line()):
        from nucleo.flash import follow_up_pass
        follow_up_pass.deliver(line)


def words_were_the_act(brief) -> bool:
    """The brief is SURE what he asked for was words (`wants_words = tell`) and no errand: the reply that says them IS the
    act, so there is no «not done» to tell (a recipe told from memory, a question answered). refactor2710-99."""
    try:
        from nucleo.turn import brief as _tb, verdicts
        esc, e_info = verdicts.read(brief, _tb.ESCALATE_KEY, "")
        if e_info and e_info.get("used") and esc == "escalate":
            return False
        said, info = verdicts.read(brief, _tb.WORDS_KEY, "", min_confidence=verdicts.VETO)
        return bool(info and info.get("used")) and said == "tell"
    except Exception as _e:  # noqa: BLE001 — an unreadable brief leaves the receipt where it was
        _log.debug(f"promise_kept: words verdict unreadable: {_e!r}")
        return False


def _state_holds(open_ids=None) -> bool:
    """A card the previous acting turn's own op put on screen is still open, with nothing refused: a reply that
    DESCRIBES the screen describes what an op of this request made true (V2-792)."""
    try:
        if open_ids is None:
            from nucleo.flash import canvas_visibility as _cv
            open_ids = _cv.open_ids()
        from nucleo import canvas_focus as _focus
        return bool(_focus.last_turn_held(open_ids))
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_kept: state_holds failed: {_e!r}")
        return False


def owed(brief, *, open_ids=None) -> bool:
    """Does a turn that ran nothing (and had no pass) owe «not done»? The brief decides (CRIT-K1): an order or escalation,
    unless an op of this request left that state on screen (V2-792) — never for a sure canvas gesture (C6, 2026-10-29)."""
    try:
        from nucleo.turn import reply as _reply
        return bool(_reply.owes_an_act(brief)) and (bool(__import__("nucleo.flash.direct_action", fromlist=["x"]).sure_canvas(brief)) or not _state_holds(open_ids))
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_kept: owed failed: {_e!r}")
        return False


def close(reply: str, outcome: dict | None, *, acted: bool, emit=None, brief=None) -> str:
    """`honest_line`, said on the timeline when it is owed. Both channels call this at the end of the turn."""
    line = honest_line(reply, outcome, acted=acted, brief=brief)
    if line and emit is not None:
        try:
            emit("brain", "🤝 promesa cerrada — dice que no lo ha hecho", text=line[:160], role="system",
                 extra={"cat": "flash", "kind_diag": "promise_closed", "source": "brief",
                        "outcome": str((outcome or {}).get("kind") or "no_pass"), "reply": (reply or "")[:160]})
        except Exception as _e:  # noqa: BLE001
            _log.debug(f"promise_kept: line 154 failed: {_e!r}")
    return line


# ── a promise of work handed over LATER starts its errand (V2-794) ──────────────────────────────────────────

def deferred_errand(reply: str, outcome: dict | None, *, acted: bool, model_calls=(), brief=None) -> bool:
    """Does this turn owe an ERRAND rather than a «not done»? «You'll have them in a while» after a sure `escalate`, with
    nothing run or routed, no model call (a call a guard ate is the honest line's case) and no pass that ran, refused
    or was swallowed: only a worker can keep it. Pure; never raises."""
    try:
        if acted or str((outcome or {}).get("kind") or "") not in ("", JUDGED) \
                or any(isinstance(c, dict) and c.get("name") for c in (model_calls or ())):
            return False
        from nucleo.turn import reply as _reply
        return _reply.owes_an_act(brief) == "escalate"
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_kept: deferred_errand failed: {_e!r}")
        return False


def start_deferred(reply: str, outcome: dict | None, *, acted: bool, brief, model_calls, op_text: str, escalate,
                   emit) -> bool:
    """The voice door: start the errand a deferred promise owes, through the turn's own escalation (the same portal
    every escalation crosses). True when it was started — the turn end then owes no line."""
    if escalate is None or not (op_text or "").strip() or not deferred_errand(reply, outcome, acted=acted,
                                                                              model_calls=model_calls, brief=brief):
        return False
    try:
        from nucleo import surfaces as _surf
        escalate(op_text, context={"src": "voice", "surface": _surf.from_brief(brief), "promised": (reply or "")[:300]})
        if outcome is not None:
            outcome["kind"] = STARTED
        emit("brain", "🧭 Flash → Brain Worker (escalada registrada)", text=op_text[:200], role="system",
             extra={"cat": "flash", "kind_diag": "promise_started", "reply": (reply or "")[:160]})
        return True
    except Exception as _e:  # noqa: BLE001
        _log.warning(f"promise_kept: the deferred errand could not start: {_e!r}")
        return False


def say_the_start(escalate_req: dict, spoken_text: str, *, send, speech) -> str:
    """An errand a door started in the model's place («⚖️ a commission, not a play») on a turn that said nothing: its
    start line (`escalate_req["say"]`, the i18n «I'm on it — it isn't done yet»), so the turn is not mute. ""."""
    line = str((escalate_req or {}).pop("say", "") or "").strip()
    if not line or (spoken_text or "").strip():
        return ""
    send(speech.sanitize(line, drop_metadata=False))
    return line


# ── the seams, kept here so the turn bodies that call them only shrink ───────────────────────────────────

#: The sentence the second pass's prompt gains when it may answer `cannot_do` (`act_repair.call_for_promise`).
_CANNOT_LINE = (" If you promised or claimed an act on «{wid}» and did not do it, call `cannot_do` instead with its "
                "declared reason.")


def offer_line(outcome: dict | None) -> str:
    return _CANNOT_LINE if outcome is not None else ""


def offer_tools(outcome: dict | None) -> list:
    """The extra tool the pass is offered — none unless the caller owns an outcome. Opens the record as JUDGED."""
    if outcome is not None:
        outcome["kind"] = JUDGED
    return [CANNOT_TOOL] if outcome is not None else []


def took(outcome: dict | None, name: str, args) -> bool:
    """True when the pass's call was its `cannot_do` (recorded, never a widget call)."""
    if outcome is None or name != "cannot_do":
        return False
    outcome.update(kind=CANNOT, reason=str((args or {}).get("reason") or "no_action").strip()[:40])
    return True


def called(outcome: dict | None, call):
    """Record that the pass produced a call (passes it through)."""
    if call and outcome is not None:
        outcome["kind"] = CALL
    return call


def card_and_outcome(card: str, brief, brain, data_done: dict) -> tuple[str, dict]:
    """The voice door: the verdict's card or the fallback one, and the turn's outcome record (`data_done`)."""
    return (card or card_for_the_repair(brief, model_calls=getattr(brain, "_turn_calls", None),
                                        ran_ops=data_done.get("ops")), data_done.setdefault("promise", {}))


def landed(call, outcome: dict, *, run, acted: dict, data_done: dict, escalate_req: dict, emit):
    """Run the repaired call; the call when it RAN (or asked, or became a worker), None when a guard swallowed it —
    then the outcome says so and the turn end owes the honest line instead of a claim."""
    if not call:
        return None
    run()
    if acted.get("widget") or data_done.get("v") or escalate_req.get("v") is not None:
        return call
    outcome["kind"] = SWALLOWED
    try:
        emit("brain", "🛡️ la segunda pasada no llegó a ejecutarse — no se da por hecho",
             text=f"{call.get('widget_id')}:{call.get('action')}", role="system",
             extra={"cat": "flash", "widget": call.get("widget_id"), "action": call.get("action")})
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_kept: line 217 failed: {_e!r}")
    return None


def an_errand_was_reached() -> bool:
    """This turn STARTED a worker, injected into one or answered one — whatever lane did it (`consequence.reached`).
    Then its verdict is `started`, never «not done» (refactor2710-99, docs-report-lands-as-document__es)."""
    try:
        from nucleo import consequence
        return consequence.reached("worker.spawn", "worker.inject", "worker.answer")
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_kept: errand reach unreadable: {_e!r}")
        return False


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
    line = close(reply, outcome, acted=bool(acted), emit=emit, brief=brief) or unsent_line(brief, (data_done or {}).get("ops"))
    if line:
        from nucleo.turn import reply as _reply
        verdict = "cannot" if str((outcome or {}).get("kind") or "") == CANNOT else "unmet"
        _reply.speak([_reply.Outcome(verdict, "turn", "promise", said=line)], (reply or "").strip(), send, speech)
        if window and window[-1].get("role") == "assistant":
            window[-1]["content"] = (str(window[-1].get("content") or "") + " " + line).strip()
    return line


def unsent_line(brief, ran_ops=()) -> str:
    """«Nothing has gone out» when the brief is SURE the turn sends for him (`errand_class`) and nothing that sends ran:
    no `external.send` op, no send door or errand, no confirm this turn opened — facts, never the reply (V2-831 R11)."""
    try:
        from nucleo import consequence
        from nucleo.acts import errand
        from nucleo.turn import verdicts
        from voice import trace
        from widgets import confirm, effects
        from nucleo.turn import reply as _reply   # a SURE sends_for_him on a turn that owes an act (a remember is not one)
        cls, info = verdicts.read(brief, errand.CLASS_KEY, "", min_confidence=verdicts.VETO)
        if cls != "sends_for_him" or not (info or {}).get("used") or not _reply.owes_an_act(brief) \
                or consequence.reached("messaging.tag", "cluster.send", "architect.send", "worker.spawn", "worker.inject") \
                or any(effects.carries(w, a, effects.EXTERNAL_SEND) for w, a in (ran_ops or ())) \
                or any(p.get("trace_id") == trace.current() for p in confirm.pending().values()):
            return ""
        from i18n import langs
        return str(getattr(langs.current_language(), "send_not_done", "") or "").strip()
    except Exception as _e:  # noqa: BLE001 — an unreadable turn claims nothing
        _log.debug(f"promise_kept: unsent unreadable: {_e!r}")
        return ""
