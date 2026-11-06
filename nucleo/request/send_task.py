"""nucleo/request/send_task.py — a send is ONE linear task: his data travel with their origin, one door decides.

Measured on his engine (2026-11-06, requests T9–T12): «mándale un whatsapp a Raquel diciendo: sexta prueba» — the
brief read it right (`wants_words = act`), Flash's call named the person and the text, and the call was DROPPED: only
his sentence reached the task. A Brain Worker then had to rediscover what he had just said — it read the messaging
card to find Raquel (a stranger's text: the session was tainted), spent four bridge calls on usage errors, and the
exit door asked «shall I?» about a text he had dictated himself. Five doors could ask (the model's prose, the counted
question, the answer bound to it, the taint, the leave rule), each reading a different truth, none reading the others.

This is the hand-off that keeps what he said. A leaving act Flash calls is RETAINED on the request's row with each
declared slot of the act and where its value came from (`exit_slots.declared`: recipient, channel, text), read by
mechanism — `message.is_his` for the person, the turn's reading for the channel, `his_text` for the words (his dictated
text is a run of HIS words, in order) — and the row is born with its end state (the card's `done_when` template over
that payload). Then:

  · every required slot has a value → the task RUNS: the retained act crosses THE exit door (`exit_gate.leave`, the
    same door a worker's act crosses; checkpoint 1 is closed by the row itself) and runs through the card's own door
    (`data_ops.dispatch_and_report`), which resolves the person or asks which, queues the send, and whose echo the
    circuit attests (`circuit.settle`, the one writer; the out-of-turn notice follows the verdict);
  · a required slot has no value → ONE durable question through the one asker (`circuit/asker`), the row waits, and
    his answer fills THAT slot on THAT row (`answered`): the same task goes on. Never a new row, never a worker.

No model runs here: a send whose person and words came out of his mouth is not reasoning, it is delivery. A Brain
Worker is still the right hands when the text must be composed from something he did not say (a reply drafted from
a third party's mail): that path keeps its worker and its taint, and the exit door asks there because a slot came
from a stranger — the protection that matters (`exit_slots`, `exit_gate.gate`).
"""
from __future__ import annotations

import time

from loguru import logger

from nucleo.request import base, note

#: The retained kind on the row's `ask` artefact: his answer fills a slot of THIS task (`inline_ask.rerun`).
KIND = "send"
#: The row artefact that holds the retained act and its slots: {widget, action, payload, slots: {slot: {key, source}}}.
SLOT = "send"
#: The source rules whose slot must carry a value before the act can run (a person, the words); `reading` (the
#: channel) and `card`/`held` are optional — the card decides the rest.
REQUIRED_RULES = ("his_words", "composed")
#: Slot sources (the exit door's vocabulary, `nucleo/workers/exit_slots.py`).
HIS, READING, AGENT, NONE = "his", "reading", "agent", "none"


def his_text(text, said) -> bool:
    """Are these words HIS — a run of the words of his sentence, in order (a model trims «uh» and punctuation, never
    adds)? Read on folded tokens, in any language; a text composed from something he did not say is not his."""
    from nucleo.acts.message_names import TOK, fold
    want = TOK.findall(fold(str(text or "")))
    have = TOK.findall(fold(str(said or "")))
    if not want or not have:
        return False
    i = 0
    for tok in have:
        if tok == want[i]:
            i += 1
            if i == len(want):
                return True
    return False


def _words_of(uid: str) -> str:
    """His words this task is about: the row's goal plus his later turns on it (an answer)."""
    try:
        from nucleo.circuit import ledger
        row = ledger.get(uid) or {}
        return " ".join(str(row.get("goal") or row.get("title") or "").split())
    except Exception as e:  # noqa: BLE001
        note(e)
        return ""


def sources(wid: str, action: str, payload: dict, said: str, *, reading=None) -> dict:
    """`{slot: {key, source}}` for the act's declared slots over this payload: where each value came from, read by the
    same mechanisms the exit door uses (`message.is_his`, the turn's channel reading, `his_text`)."""
    from nucleo.workers import exit_slots
    out: dict = {}
    for slot, d in exit_slots.declared(base(wid), action).items():
        key, rule = str(d.get("key") or slot), str(d.get("from") or "")
        v = payload.get(key)
        has = isinstance(v, str) and bool(v.strip())
        if not has:
            src = NONE
        elif rule == "his_words":
            from nucleo.acts import message
            src = HIS if message.is_his(v, [said]) else AGENT
        elif rule == "reading":
            src = READING if (_reading_names(reading, v) or his_text(v, said)) else AGENT
        elif rule == "composed":
            src = HIS if his_text(v, said) else AGENT
        else:
            src = "card"
        out[slot] = {"key": key, "rule": rule, "source": src}
    return out


def _reading_names(reading, value) -> bool:
    if reading is None or not str(value or "").strip():
        return False
    try:
        from nucleo.acts import message_channel
        from nucleo.turn import brief as _tb, verdicts
        turn = _tb.revived(reading) if isinstance(reading, dict) else reading
        choice, _info = verdicts.read(turn, message_channel.KEY, None)
        return choice not in (None, message_channel.NONE) and str(choice) == str(value).strip().lower()
    except Exception as e:  # noqa: BLE001
        note(e)
        return False


def missing(art: dict) -> tuple[str, str]:
    """The first required slot with no value: `(slot, payload key)`, or `("", "")` when the act may run."""
    for slot, d in (art.get("slots") or {}).items():
        if str(d.get("rule") or "") in REQUIRED_RULES and str(d.get("source") or NONE) == NONE:
            return slot, str(d.get("key") or slot)
    return "", ""


def artefact(uid: str) -> dict:
    try:
        from nucleo.circuit import ledger
        got = ledger.store().artifact_get(uid, SLOT)
        return got if isinstance(got, dict) else {}
    except Exception as e:  # noqa: BLE001
        note(e)
        return {}


def _keep(uid: str, art: dict) -> None:
    from nucleo.circuit import ledger
    ledger.store().artifact_put(uid, SLOT, art)


def retain(wid: str, action: str, payload: dict | None, said: str, *, reading=None, emit=None) -> str:
    """Keep Flash's leaving call on the request's row, with its slots and their origin, and the end state the card
    declares for it. The row's uid, or "" when the act declares no slots (that card keeps the worker route)."""
    from nucleo.workers import exit_slots
    if not exit_slots.declared(base(wid), action):
        return ""
    try:
        from widgets import contract
        payload = contract.fold_aliases(base(wid), action, dict(payload or {}))
    except Exception as e:  # noqa: BLE001
        note(e)
        payload = dict(payload or {})
    from nucleo.request import model
    uid = model.opened(wid, action, text=said)
    if not uid:
        return ""
    art = {"widget": str(wid), "action": str(action), "payload": payload,
           "slots": sources(wid, action, payload, said, reading=reading),
           "reading": dict(reading) if isinstance(reading, dict) else None,
           "heard": [" ".join(str(said or "").split())]}
    try:
        from nucleo.circuit import ledger
        from nucleo.request.answered_task import PLAYBOOK
        ledger.store().task_patch(uid, playbook=PLAYBOOK)
        _keep(uid, art)
        _end_state(uid, wid, action, payload, said)
    except Exception as e:  # noqa: BLE001 — a row that could not keep the act is a row the worker route serves
        note(e)
        return ""
    _emit(emit, "📨 send task: his data travel with their origin", f"{wid}:{action}",
          {"cat": "flash", "task_id": uid, "widget": wid, "action": action,
           "slots": {s: d["source"] for s, d in art["slots"].items()}})
    return uid


def _end_state(uid: str, wid: str, action: str, payload: dict, said: str) -> None:
    """The task is born with its end state: the card's declared template over this payload, persisted on the row (the
    circuit judges the ending by it; checkpoint 1 is closed by the row for a worker that takes it over)."""
    from nucleo.circuit import spec
    dw = spec.render(wid, action, payload)
    if not dw:
        return
    e = spec.open(dw, text=said, source="send_task", widget=wid, action=action, task_id=uid)
    if e is not None:
        spec.withdraw(e)                 # owed when the act runs (`data_ops` opens it again), not while a slot waits
        spec.persist(uid, e)


def _question(uid: str, art: dict, slot: str, key: str, question: str = "", candidates=None,
              consent: str = "") -> str:
    """The task waits on ONE question about one slot, through the one asker; his answer fills it (`answered`)."""
    from nucleo import consent as _consent
    from nucleo.circuit import asker, ledger
    from nucleo.runtime_ids import next_seq
    from observability import identity
    cands = [str(c) for c in (candidates or []) if str(c or "").strip()]
    q = " ".join(str(question or "").split()) or _missing_line(art, slot)
    ask_id = f"{uid}-q{next_seq('inline.ask')}"
    session = identity.session_id()
    entry = {"ask_id": ask_id, "corr_id": ask_id, "uid": uid, "task_id": "", "inline": True,
             "action": art.get("action"), "question": q, "answer": "", "result": None, "session": session,
             "consent": consent or (_consent.ASK_WHICH if cands else _consent.ASK_FACT),
             "candidates": cands, "options": cands, "said": True,
             "retained": {"kind": KIND, "widget": art.get("widget"), "action": art.get("action"),
                          "payload": dict(art.get("payload") or {}), "slot": key, "slot_name": slot,
                          "candidates": cands}}
    ledger.store().task_patch(uid, session_id=session)
    return asker.ask(uid, entry)


def _missing_line(art: dict, slot: str) -> str:
    """The question for a slot with no value, from the language table (`send_missing_<slot>`), the person named."""
    who = ""
    try:
        from nucleo import on_his_behalf as _ob
        who = ", ".join(_ob.who_of(str(art.get("widget") or ""), str(art.get("action") or ""), art.get("payload")))
    except Exception as e:  # noqa: BLE001
        note(e)
    try:
        from i18n import langs
        tpl = str(getattr(langs.current_language(), f"send_missing_{slot}", "") or "")
        if tpl:
            return tpl.format(who=who or "?")
    except Exception as e:  # noqa: BLE001
        note(e)
    return f"{slot}? ({who})"


def commission(wid: str, action: str, payload: dict | None, said: str, *, reading=None, emit=None,
               asked_line: str = "") -> str:
    """Flash's leaving call becomes the task: retained with its slots, then run — or asked for the one slot it lacks.
    `asked_line`: the question the turn's mouth ALREADY said about it (the model asked in prose) — it becomes the row's
    question, never said twice. Returns the row's uid, or "" when this card's act is not a send task (the caller keeps
    its worker route)."""
    uid = retain(wid, action, payload, said, reading=reading, emit=emit)
    if not uid:
        return ""
    art = artefact(uid)
    slot, key = missing(art)
    if slot:
        q = " ".join(str(asked_line or "").split()) or _missing_line(art, slot)
        ask_id = _question(uid, art, slot, key, q)
        if not asked_line:
            _said_asked(wid, action, q)
        _emit(emit, "❓ send task: one slot has no value — asked on its row", q, {"cat": "flash", "task_id": uid,
              "slot": slot, "ask_id": ask_id})
        return uid
    _said_started(uid, wid, action, art)
    _schedule(uid)
    return uid


def _said_asked(wid: str, action: str, q: str) -> None:
    try:
        from nucleo.circuit import verdict as V
        from nucleo.turn import reply
        reply.note(reply.Outcome(V.ASKED.name, base(wid), action, reason=q))
    except Exception as e:  # noqa: BLE001
        note(e)


def _said_started(uid: str, wid: str, action: str, art: dict) -> None:
    """The turn's mouth says the START, from the row — never that it left: `started` names the person; the ending
    is the circuit's line, out of turn, when the echo attests it."""
    try:
        from nucleo import on_his_behalf as _ob
        from nucleo.circuit import verdict as V
        from nucleo.turn import reply
        who = ", ".join(_ob.who_of(str(art.get("widget") or ""), str(art.get("action") or ""), art.get("payload")))
        reply.note(reply.Outcome(V.STARTED.name, base(wid), action, object=who))
    except Exception as e:  # noqa: BLE001
        note(e)


def _schedule(uid: str) -> None:
    """Run the task off the turn's stream (the mouth never waits for a connector)."""
    import asyncio
    from nucleo.request.send_task_run import run
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(run(uid))
        return
    loop.create_task(run(uid))


def _emit(emit, label: str, text: str, extra: dict) -> None:
    try:
        if emit is None:
            from voice.observer import emit as _e
            emit = _e
        emit("brain", label, text=str(text or "")[:300], role="system", extra=extra)
    except Exception as e:  # noqa: BLE001
        note(e)
