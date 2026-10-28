"""A reply that commits to an act ends in one of three states, in both channels — never in a log line.

The class (V2-790): the model SAYS it will do something on a card («I'll open its videos tab», «te lo subo y le
quito el silencio») or that it already did («there, its videos tab is open»), nothing ran, and the engine only
wrote `⚠️ promesa sin acción` on the timeline. The operator waited minutes, asked «what are you waiting for?»,
and got the same promise again. Three ways the existing repair never opened:

  · its card came ONLY from the decision model (`card_commission.named_or_catalogue`), so with the decision model
    unavailable no card was ever named and no second pass ran;
  · the model DID name its card — it emitted the call — and one of our guards discarded it (a replay of the
    previous turn's op); the turn then counted as «no tool», the verdict named nothing, and a reply claiming the
    act reached him unqualified;
  · a second pass that called nothing told nobody whether the words promised nothing or the card could not do it.

The mechanism, one door shared by the voice turn (`post_stream_acts` + `turn_after`) and the text channel
(`probe_mirrors`):

  1. `card_for_the_repair` — when no verdict names a card: the card of a call the MODEL made this turn that did not
     run (its own declared intent, no wording read), and, only when the decision model gave nothing at all, the
     card his last turn acted on (`canvas_focus`) or the one card open.
  2. The second pass (`act_repair.call_for_promise(..., outcome=)`) may also answer `cannot_do` — the model's own
     declaration, in his language, that no declared action does it. It records WHICH of the three it was.
  3. `honest_line` — at turn end, when nothing ran: the pass's own «I could not», or, when the pass's call was
     swallowed by a guard or no card could be found for a committing reply, the i18n `promise_not_kept` line.

A reply that only DESCRIBES what is on screen and leaves the next act to him owes nothing (V2-792): the verdict's
`ask_first` stands the line down at any confidence, and a claimed state an op of this request left on screen holds.

Bounded: one second pass per turn (the door that already existed), no loop (the line is words, never a new turn),
and a pass that read the words and found no promise is trusted — the line is never said over its judgement.
"""
from __future__ import annotations

from loguru import logger as _log

#: The non-acting tool the second pass is offered beside `widget_data` (`act_repair.call_for_promise`).
CANNOT_TOOL = {
    "type": "function",
    "function": {
        "name": "cannot_do",
        "description": ("You promised or claimed an act on the card and NONE of its declared actions can do it: say "
                        "so. `say` is ONE short sentence to the operator, in HIS language, telling him plainly that "
                        "you have not done it and why — no promise of a later attempt."),
        "parameters": {"type": "object", "properties": {"say": {"type": "string"}}, "required": ["say"]},
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
    """The card of the last `widget_data` call the MODEL made this turn that did not run — "" when none.

    The model's call names its card; a guard that discarded it does not make the card unknown."""
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
        focus = _base(_focus.last_turn_card(ids))
        if focus:
            return focus
        return ids[0] if len(ids) == 1 else ""
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_kept: line 96 failed: {_e!r}")
        return ""


def _not_kept_line() -> str:
    try:
        from i18n import langs as _langs
        return str(getattr(_langs.current_language(), "promise_not_kept", "") or "").strip()
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_kept: line 115 failed: {_e!r}")
        return ""


def honest_line(reply: str, outcome: dict | None, *, acted: bool, brief=None) -> str:
    """The words owed when the turn owed an act and nothing ran — "" when something ran or nothing was owed.

    · the pass declared it cannot  → its own sentence (or the i18n line);
    · the pass's call was swallowed by a guard → the i18n line (a claim over a discarded op is not «done»);
    · the pass read the turn and called nothing → nothing (its judgement stands);
    · no pass could run (no card) and the brief says an act was owed (`owed`) → the i18n line."""
    if acted or words_were_the_act(brief):
        return ""
    kind = str((outcome or {}).get("kind") or "")
    if kind in (CALL, STARTED, JUDGED):
        return ""
    if kind == CANNOT:
        return str((outcome or {}).get("say") or "").strip() or _not_kept_line()
    if kind == SWALLOWED:
        return _not_kept_line()
    return _not_kept_line() if owed(brief) else ""


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
    """Does a turn that ran nothing (and had no pass) owe «not done»? The brief's verdict decides (CRIT-K1): an order or
    an escalation at its confidence, unless an op of this request already left that state on screen (V2-792)."""
    try:
        from nucleo.turn import reply as _reply
        return bool(_reply.owes_an_act(brief)) and not _state_holds(open_ids)
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
    """Does this turn owe an ERRAND rather than a «not done»? Pure; never raises.

    «I'll put the forty together for you… you'll have them on the card in a while»: the brief said the turn commissions
    background work (`escalate`), the model called nothing, no card took a second pass, and nothing was started — so
    «in a while» was a promise nobody would keep; only a worker can keep it. Not when: something ran or was routed;
    the model made any call (a call a guard ate is the honest line's case, V2-753); the pass ran a call, declared it
    cannot, or was swallowed."""
    try:
        if acted:
            return False
        if str((outcome or {}).get("kind") or "") not in ("", JUDGED):
            return False
        if any(isinstance(c, dict) and c.get("name") for c in (model_calls or ())):
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
_CANNOT_LINE = (" If you promised or claimed an act on «{wid}» and NONE of its declared actions can do it, call "
                "`cannot_do` instead, with one short sentence for the operator saying plainly that you have not done "
                "it and why.")


def offer_line(outcome: dict | None) -> str:
    return _CANNOT_LINE if outcome is not None else ""


def offer_tools(outcome: dict | None) -> list:
    """The extra tool the pass is offered — none unless the caller owns an outcome. Opens the record as JUDGED."""
    if outcome is None:
        return []
    outcome["kind"] = JUDGED
    return [CANNOT_TOOL]


def took(outcome: dict | None, name: str, args) -> bool:
    """True when the pass's call was its `cannot_do` (recorded, never a widget call)."""
    if outcome is None or name != "cannot_do":
        return False
    outcome.update(kind=CANNOT, say=str((args or {}).get("say") or "").strip()[:240])
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
        pass
    return None


def say_after(reply: str, data_done: dict, *, acted, send, speech, window: list, emit, turn=None) -> str:
    """The voice turn end: a deferred promise's errand started, else the honest line, said by the mouth
    (`nucleo/turn/reply.py`, verdict `cannot` or `unmet`) after what streamed and kept in the dialog window.
    `turn` = `(brief, model_calls, op_text, escalate)` of the voice turn, or None."""
    outcome = data_done.setdefault("promise", {}) if isinstance(data_done, dict) else None
    brief = turn[0] if turn else None
    if turn and start_deferred(reply, outcome, acted=bool(acted), brief=brief, model_calls=turn[1], op_text=turn[2],
                               escalate=turn[3], emit=emit):
        return ""
    line = close(reply, outcome, acted=bool(acted), emit=emit, brief=brief)
    if line:
        from nucleo.turn import reply as _reply
        verdict = "cannot" if str((outcome or {}).get("kind") or "") == CANNOT else "unmet"
        _reply.speak([_reply.Outcome(verdict, "turn", "promise", said=line)], (reply or "").strip(), send, speech)
        if window and window[-1].get("role") == "assistant":
            window[-1]["content"] = (str(window[-1].get("content") or "") + " " + line).strip()
    return line
