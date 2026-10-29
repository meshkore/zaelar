"""The mouth speaks the verdict (refactor2710-03).

An ACTING turn's last words are composed from what its acts ENDED in, never repaired from what the model said. Each
act reports a verdict (`started · met · unmet · unverifiable · undeclared · cannot · asked · skipped`, the one
enumeration of `nucleo/circuit/verdict.py`) and the object it reached; this module turns that into ONE line, from
the i18n bundles (`reply_<verdict>`), and says it after the words that already streamed.

The rules, in the order they decide:

  · a CONVERSING turn (no act) keeps the model's words: nothing is added;
  · a promise is a START: `started` adds nothing, because the act is under way and the model's words said so;
  · `met` names its object, and only when the words did not already name it (the comparison is with the object
    the act returned, never with a table of words) — «Done.» alone is never the line;
  · `unmet`, `cannot` and `asked` are always said: a refusal, an impossibility or our question is a fact the model
    could not know when it spoke.

Every line leaves one event (`brain` · «🗣 reply: the verdict's line») carrying `{verdict, key, object}`.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from loguru import logger

from nucleo.circuit import verdict as V
from voice import trace as _voice_trace

#: How long the reply waits for the turn's acts to answer. Past it, an act is still `started` and the model's
#: words (its promise) stand.
WAIT_S = 4.0

#: The verdicts whose line is said whatever the model's words were.
ALWAYS_SAID = (V.UNMET.name, V.CANNOT.name, V.ASKED.name)


@dataclass(frozen=True)
class Outcome:
    """What ONE act of the turn ended in: its verdict, the object it reached and, when it did not, why."""
    verdict: str
    card: str = ""
    action: str = ""
    object: str = ""
    reason: str = ""
    told: bool = False          # its own door already said it (a data-op's refusal: `data_ops.report_failure`)
    said: str = ""              # the act's OWN sentence from its fact (a card's message, a notice read back): it wins


def owes_an_act(brief) -> str:
    """"escalate" | "order" | "" — the turn's brief says, at its confidence, that this turn owed an act (CRIT-K1: a
    verdict decides whether an act was owed, never our own words). "" when the brief does not say so: nothing is
    invented then, the model's turn stands."""
    try:
        if _voice_trace.is_kickoff():      # OUR turn (the session's greeting) answers no order of his
            return ""
        from nucleo.turn import brief as tb
        esc, e_info = tb.read(brief, tb.ESCALATE_KEY, "")
        if e_info is not None and esc == "escalate":
            return "escalate"
        kind, k_info = tb.read(brief, tb.REQUEST_KEY, "")
        return "order" if (k_info is not None and kind == "order") else ""
    except Exception as e:  # noqa: BLE001
        logger.debug(f"reply: the brief was not read — {e!r}")
        return ""


def _value(verdict) -> str:
    """The verdict's name in the one vocabulary (`nucleo.circuit.verdict`); "" for a name no verdict has."""
    v = V.of(getattr(verdict, "name", verdict))
    return v.name if v else ""


def _lang():
    try:
        from i18n import langs
        return langs.current_language()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"reply: no language table — {e!r}")
        return None


def _quoted(title: str) -> str:
    return f"«{title.strip()}»"


def object_of(res) -> str:
    """The object an act reached, from the act's RESULT: a title, or a queue (what plays first, then the rest)."""
    res = res if isinstance(res, dict) else {}
    title = str(res.get("title") or "").strip()
    queued = [str(t).strip() for t in (res.get("queued") or res.get("added") or []) if str(t).strip()]
    if queued:
        head = title or queued[0]
        names = [_quoted(t) for t in [head] + [t for t in queued if t != head]][:4]
        joiner = str(getattr(_lang(), "receipt_and", "") or "+")
        return ", ".join(names[:-1]) + f" {joiner} {names[-1]}" if len(names) > 1 else names[0]
    return _quoted(title) if title else ""


def of_op(card: str, action: str, res) -> Outcome:
    """The verdict of ONE data-op, read from its result through the receipt (`op_receipt`): refused → `unmet` with
    the sentence the card may say; plainly landed → `met` with its object; anything else is still `started`."""
    from nucleo.flash import op_receipt, refusal_line
    if op_receipt.failed(res):
        return Outcome(V.UNMET.name, card, action, reason=refusal_line.speakable(card, res).strip(), told=True)
    if op_receipt.landed(res):
        return Outcome(V.MET.name, card, action, object=object_of(res))
    return Outcome(V.STARTED.name, card, action)


async def of_ops(tasks, timeout: float = WAIT_S) -> list[Outcome]:
    """The verdicts of the turn's data-ops (`(card, task)` pairs), once they answered or `timeout` passed."""
    out: list[Outcome] = []
    try:
        pend = [t for _w, t in tasks if not t.done()]
        if pend:
            await asyncio.wait(pend, timeout=timeout)
    except Exception as e:  # noqa: BLE001 — an unreadable wait leaves every op `started`
        logger.debug(f"reply: the ops' wait failed — {e!r}")
    for w, t in tasks or []:
        card, _, action = str(w).partition("::")
        try:
            if not t.done() or t.cancelled():
                out.append(Outcome(V.STARTED.name, card, action))
                continue
            out.append(of_op(card, action, t.result()))
        except Exception as e:  # noqa: BLE001 — an unreadable verdict claims NOTHING (live 2026-10-28: «check the
            # chat» answered with his 19 chats and then «I couldn't get that done», from this branch, over an op the
            # card never refused). The failure the card reports is the only «unmet»; a raise here is ours to log.
            logger.warning(f"reply: {card}:{action} — its verdict could not be read: {e!r}")
            out.append(Outcome(V.STARTED.name, card, action))
    return out


#: Verdicts an act DECLARED during the turn without a data-op behind it (a canvas exit that found nothing, a question
#: the act asks), keyed by the turn's trace: the act runs inside the stream's pump task, and a ContextVar set there
#: never reaches the task that closes the turn.
_NOTED: dict[str, list[Outcome]] = {}


def _trace() -> str:
    try:
        from voice import trace
        return trace.current() or ""
    except Exception as e:  # noqa: BLE001
        logger.debug(f"reply: no trace for this turn — {e!r}")
        return ""


def note(outcome: Outcome) -> None:
    """An act of this turn declares its verdict (one that no data-op carries)."""
    _NOTED.setdefault(_trace(), []).append(outcome)


def taken() -> list[Outcome]:
    """The verdicts this turn's acts declared, once: reading them clears them."""
    return _NOTED.pop(_trace(), [])


#: Turns that END on our question (V2-831 T-08), by trace — apart from `_NOTED`, which the mouth pops first.
_ASKED: dict[str, str] = {}


def settle_asked(source: str) -> None:
    """This turn ends asking HIM («model»: its `[[ask]]` tag · «clarify»: the clarify door) — the `asked` verdict."""
    _ASKED[_trace()] = str(source or "")
    if len(_ASKED) > 32: _ASKED.pop(next(iter(_ASKED)))   # noqa: E701 — a bounded record of recent turns
    V.emit(V.ASKED, text=str(source or ""), source=str(source or ""))


def asked() -> bool:
    """Did this turn settle `asked`? Read, never consumed."""
    return _trace() in _ASKED


#: The memory door's declared outcome per turn (V2-831 T-19): `[ingests in flight, rows it changed about him]`.
_MEMORY: dict[str, list] = {}


def memory_settled(changed: int | None) -> None:
    """The memory door starts (`None`) or ends having written, forgotten or restored `changed` rows about him."""
    rec = _MEMORY.setdefault(_trace(), [0, 0])
    rec[:] = [rec[0] + 1, rec[1]] if changed is None else [max(0, rec[0] - 1), rec[1] + max(0, changed)]
    if len(_MEMORY) > 32: _MEMORY.pop(next(iter(_MEMORY)))   # noqa: E701 — a bounded record of recent turns


def remembered() -> bool:
    """Did this turn's memory door change something about him — an order's act with no tool? Never consumed."""
    return (_MEMORY.get(_trace()) or [0, 0])[1] > 0


def _notice_moved(said: str) -> list[Outcome]:
    """A notice this turn MOVED to ring soon today is `met` at the hour the live job rings, read back from the
    schedule (`notice_readback`) — "" when the words already said that hour."""
    try:
        from nucleo.flash import notice_readback
        text = notice_readback.moved_line(said)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"reply: the schedule was not read back — {e!r}")
        return []
    return [Outcome(V.MET.name, "cron", "create", said=text)] if text else []


def _errands_that_died(said: str) -> list[Outcome]:
    """An errand that ENDED unmet (failed, not cancelled) is `unmet`, said ONCE by the mouth — the record says it
    died, whatever the model's words promised. Skipped when the words already named it by its title or goal."""
    out: list[Outcome] = []
    try:
        from nucleo import dispatch
        low = (said or "").lower()
        for row in dispatch.recently_ended_sessions():
            if row.get("ok") or str(row.get("status") or "") == "cancelled" or row.get("mouth_said"):
                continue
            name = str(row.get("title") or row.get("goal") or "").strip()
            live = dispatch._ENDED_SESSIONS.get(str(row.get("id")))
            if live is not None:
                live["mouth_said"] = True
            if name and name.lower() not in low:
                out.append(Outcome(V.UNMET.name, "errand", str(row.get("id") or ""), object=_quoted(name),
                                   reason=_quoted(name)))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"reply: the ended errands were not read — {e!r}")
    return out


def line(outcome: Outcome) -> str:
    """The sentence for ONE outcome, from the bundle key of its verdict. "" when the verdict has nothing to say."""
    value = _value(outcome.verdict)
    if outcome.said and value:
        return outcome.said.strip()
    template = str(getattr(_lang(), f"reply_{value}", "") or "")
    if not template:
        return ""
    if "{object}" in template and not outcome.object:
        return ""
    if "{reason}" in template and not outcome.reason:
        if value == V.UNMET.name:
            return str(getattr(_lang(), "op_failed", "") or "")
        return ""
    return template.format(object=outcome.object, reason=outcome.reason).strip()


def _already_said(outcome: Outcome, said: str) -> bool:
    """The words named the object: every title the object quotes is in what was said."""
    titles = [t for t in outcome.object.split("«")[1:]]
    names = [t.split("»")[0].strip().lower() for t in titles]
    low = (said or "").lower()
    return bool(names) and all(n in low for n in names)


def owed(outcomes: list[Outcome], said: str) -> list[tuple[Outcome, str]]:
    """The lines the turn owes after `said`: one per outcome that must be said, in the order the acts ran."""
    lines: list[tuple[Outcome, str]] = []
    for o in outcomes:
        value = _value(o.verdict)
        if o.told:
            continue
        if value in ALWAYS_SAID or (value == V.MET.name and (o.said or o.object and not _already_said(o, said))):
            text = line(o)
            if text and text not in (t for _o, t in lines):
                lines.append((o, text))
    return lines


def _emit(o: Outcome, text: str) -> None:
    try:
        from voice.observer import emit
        emit("brain", "🗣 reply: the verdict's line", role="system", text=text[:160],
             extra={"cat": "flash", "verdict": _value(o.verdict), "key": f"reply_{_value(o.verdict)}",
                    "object": o.object[:120], "id": o.card, "action": o.action})
    except Exception as e:  # noqa: BLE001 — the trace never decides the words
        logger.debug(f"reply: event not emitted — {e!r}")


def speak(outcomes: list[Outcome], said: str, send, speech) -> str:
    """Say what `outcomes` owe after `said` and return the turn's whole text. Never raises."""
    try:
        for o, text in owed(outcomes, said):
            send((" " if said else "") + speech.sanitize(text, drop_metadata=False))
            said = f"{said} {text}".strip()
            _emit(o, text)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reply: the verdict's line was not said — {type(e).__name__}: {e}")
    return said


async def after_acts(tasks, said: str, send, speech, timeout: float = WAIT_S) -> str:
    """The turn's acts ended (its data-ops answered, or `timeout` passed): the lines of what they declared and of
    what the data-ops ended in, after `said`."""
    from nucleo.turn import brief as _tb, reply_receipts as _receipts
    end = time.monotonic() + timeout       # an ORDER with no op may be the memory door's write: waited, in budget
    while not tasks and (_MEMORY.get(_trace()) or [0])[0] and owes_an_act(_tb.of_this_turn()) == "order" and time.monotonic() < end:
        await asyncio.sleep(0.05)
    timeout = max(0.0, end - time.monotonic())
    outcomes = (taken() + _notice_moved(said) + _errands_that_died(said)
                + (await of_ops(tasks, timeout) if tasks else [])
                + await _receipts.player(said) + await _receipts.blocked_channel())
    return speak(outcomes, said, send, speech) if outcomes else said
