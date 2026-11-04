"""A reply that commits to an act ends in one of three states, in both channels — never in a log line.

The class (V2-790): the model SAYS it will do (or did) something on a card, nothing ran, and only a log line said so —
the repair never opened when no verdict named the card, when a guard discarded the model's own call, or when its
second pass called nothing and told nobody why.

The mechanism, one door shared by the voice turn (`post_stream_acts` + `turn_after`) and the typed turn. Its seams
live beside it, one file per concern (V2-831 audit A10b): `promise_repair` (the second pass's `cannot_do` and what
it records), `promise_errand` (a promise of work later starts its errand), `promise_send` (the voice turn's end and a
send no act made):

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

#: The pass's outcomes, as `outcome["kind"]` records them.
CALL, JUDGED, SWALLOWED, CANNOT, STARTED = "call", "judged", "swallowed", "cannot", "started"   # last two: verdicts
HELD = "held"            # the pass's call would write what the data already holds: met, nothing ran, nothing owed


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


def write_kept_unrun(model_calls, data_done) -> str:
    """The card of a WRITE the model called that a veto kept unrun, in a turn where no data-op ran — "" otherwise.

    V2-845: a veto that dropped the write or showed the card instead set `acted`, so the promise doors read the turn as
    acted and «I'll put it in your agenda» stood over an empty agenda. A vetoed write is not the act his words owed: the
    doors read it as not acted, and the second pass (or the honest line) settles the promise. Never raises."""
    try:
        if (data_done or {}).get("v"):
            return ""
        from widgets import effects
        ran = {(_base(w), str(a or "")) for w, a in ((data_done or {}).get("ops") or ()) if w}
        for c in reversed(list(model_calls or ())):
            if not isinstance(c, dict) or c.get("name") != "widget_data":
                continue
            args = c.get("args") if isinstance(c.get("args"), dict) else {}
            wid, act = str(args.get("widget_id") or ""), str(args.get("action") or "")
            if wid and (_base(wid), act) not in ran and effects.carries(wid, act, effects.DATA_WRITE):
                return _base(wid)
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_kept: kept-unrun write unreadable: {_e!r}")
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
    from nucleo.acts import message as _message   # V2-850: «which Raquel — Salvador or Jofre?» asks, it promised nothing
    if _message.asked_which(reply, str((brief or {}).get("judged") or "") if isinstance(brief, dict) else ""):
        return ""
    kind = str((outcome or {}).get("kind") or "")
    if kind in (CALL, STARTED, JUDGED, HELD):
        return ""
    cannot = _not_kept_line(f"promise_cannot_{(outcome or {}).get('reason')}") if kind == CANNOT else ""
    if kind == CANNOT and not cannot:
        return ""        # a reason that says nothing («your reply already asks him») stays silent on every path
    memory_may_be_it = not _aimed_at_a_card(brief)   # the memory door's write is the act only for an order at no card
    if kind == CANNOT and memory_may_be_it and (_reply.remembered() or _when_memory_settles(_reply, cannot)):
        return ""        # «no card can do it» — but the act was the memory write (R1's record), done or still filing
    if kind in (CANNOT, SWALLOWED):     # the pass's declared reason, said from the pack in HIS language (never its text)
        return cannot if kind == CANNOT else _not_kept_line()
    if not owed(brief, spoken=reply) or (memory_may_be_it and _reply.owes_an_act(brief) == "order" and _reply.remembered()):
        return ""
    return "" if memory_may_be_it and _reply.owes_an_act(brief) == "order" and _when_memory_settles(_reply) \
        else _not_kept_line()


def _aimed_at_a_card(brief) -> bool:
    """The brief is SURE his order is aimed at a card — one on screen (`screen_action`) or one in the catalogue
    (`catalog_widget`). Then what the memory door filed from the same sentence («my dentist is Dr Rowan, move the
    appointment to five») is not the order's act, and «not done» is still owed (V2-831 audit A10)."""
    return bool(_aimed_card(brief))


def _aimed_card(brief) -> str:
    """The card the brief is sure his order is aimed at ("" when none or unreadable) — `_aimed_at_a_card`'s reading."""
    try:
        from nucleo.turn import brief as tb
        for key in (tb.TARGET_KEY, tb.CATALOG_KEY):
            choice, info = tb.read(brief, key, "")
            if info is not None and str(choice or "") not in ("", "none"):
                return str(choice)
    except Exception as e:  # noqa: BLE001 — unreadable: the memory door may still be the act, as before
        _log.debug(f"promise_kept: the card verdicts were not read — {e!r}")
    return ""


def _when_memory_settles(_reply, line: str = "") -> bool:
    """The memory door is still filing this order (the distiller outlasted the acts' budget, pass 6 INIT #01): not a fact
    yet. Its line waits — said as the turn's follow-up only if the door filed nothing. False = say it now."""
    try:
        import asyncio
        if _reply.memory_pending():
            _LATE.add(t := asyncio.get_running_loop().create_task(_say_if_nothing_filed(_reply, line)))
            return bool(t.add_done_callback(_LATE.discard) or True)
    except Exception as _e:  # noqa: BLE001 — no loop to wait on: the line is said now
        _log.debug(f"promise_kept: memory wait unavailable: {_e!r}")
    return False


_LATE: set = set()
#: How long a turn's «not done» waits for a memory door still filing; past it the outcome is unknown and nothing is said.
MEMORY_WAIT_S = 30.0


async def _say_if_nothing_filed(_reply, line: str = "") -> None:
    import asyncio
    import time
    deadline = time.monotonic() + MEMORY_WAIT_S       # a wall-clock bound, never an iteration count
    while _reply.memory_pending() and time.monotonic() < deadline:
        await asyncio.sleep(0.1)
    if _reply.memory_pending():              # still filing at the bound: unknown — «not done» would be a guess
        return
    if not _reply.remembered() and (line := line or _not_kept_line()):
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


def _live_work_covers(brief, spoken: str = "") -> bool:
    """Is a LIVE errand what this order is about? Not «is anything running» — the question
    `escalation_guard.covered_by_live_work` already answers for the escalation gate (session 092569ab: an unrelated
    worker annulled a commission that was then never born).

    docs-report-lands-as-document__us (V2-834 T20): «ok, let me know when it's filled in» with the report's worker live
    was told «I haven't done it». The fix first read ANY live errand as cover, which silenced «not done» for every order
    while something ran — «add the dentist on Thursday» over a ten-minute search (S1 audit H1). The yardstick is the
    attribution's own (`named_errand.named`, no word list): the errand his sentence names; else, when the brief is sure
    the order is for a card, only an errand that owns that card (`owns_card`: its results sheet or document); else the
    errand our previous reply was about, which is what «it» points at. Parked errands are not live work: they wait on
    him."""
    try:
        from nucleo.turn import named_errand as _ne
        live = [e for e in _ne.known() if not e.get("parked")]
        if not live:
            return False
        said = str((brief or {}).get("judged") or "") if isinstance(brief, dict) else ""
        if said and _ne.named(said, live):
            return True
        card = _aimed_card(brief)
        if card:                      # sure his order is for a card: covered only if a live errand owns that card
            return any(_ne.owns_card(e, card) for e in live if card.split("::", 1)[0] in ("results", "documento"))
        from nucleo.turn import our_question as _oq
        prev = _oq.previous_reply(spoken)  # «it» with no card and nothing named: the errand our previous reply was about
        return bool(prev) and bool(_ne.named(prev, live))
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_kept: live-work cover unreadable: {_e!r}")
        return False


def owed(brief, *, open_ids=None, spoken: str = "") -> bool:
    """Does a turn that ran nothing (and had no pass) owe «not done»? The brief decides (CRIT-K1): an order or escalation,
    unless an op of this request left that state on screen (V2-792) — never for a sure canvas gesture (C6, 2026-10-29)."""
    try:
        from nucleo.turn import reply as _reply
        if _live_work_covers(brief, spoken):
            return False   # «let me know when it's filled in» over THAT errand: the work covers it (V2-834 T20)
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
