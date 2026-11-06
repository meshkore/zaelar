"""nucleo/request/ask_outside_door.py — a question about a door's act that the door never asked is COUNTED (V2-851 F2c).

The door is the one reader of «which person / which channel / which missing fact»: the model passes his words as he
said them, the door's consent verdict asks (ASK_WHICH / ASK_FACT), the asker makes the row wait with the act retained,
and his answer re-runs it (`nucleo/request/inline_ask`). A turn that ends on OUR OWN question while the brief names a
card whose actions leave the machine, and no call reached any door, asked outside it: nothing was retained, no
durable question exists, and his answer only works if the model happens to call the door next turn.

This is a measurement, never a repair: it emits one observer event `ask_outside_door` with the turn's trace and the
card the brief named, and nothing runs again (re-runs after the stream are 0 by design). What makes the model call
the door instead is the action's declaration (its manifest `usage`), not a sentence here. Since F2d the question it
counts is ALSO made durable by the turn's end (`held` below): the row waits on it, like a door's.

«Our own question» is read off the reply's closing mark, or off the directory (the reply named two or more of the
people his word reaches — `nucleo/acts/message.asked_which`): never off a word list.
A question Flash asks itself about a door's act is a DURABLE question (V2-851 F2d, `held`).

Measured: «send a message to Raquel» with two Raquels in the people block — the model asked «which Raquel?» without
calling the send door. `ask_outside_door` counted it, and that was all: no row waited, no `ask` event, and his answer
only worked if the model happened to call the door on the next turn.

Now the same question goes through THE asker (`nucleo/circuit/asker`), exactly as a door's or a worker's: the turn's
row (opened through `request/model.opened`, the one birth door, when the turn had none) waits for his answer with an
`ask_id`, the question is the reply line he already heard (`said`: the pulse never relays it again), the candidates
are the people the directory resolved for his sentence (the rows the people block showed — data, never his words
re-read), and what is
retained is his REQUEST: {kind: utterance, text, widget, actions}. The widget is the brief's verdict; the actions are
the card's declared acts that leave the machine.

His answer (screen, with its `ask_id`; or a later turn the brief's binding verdict ties to it) makes the request an
IDENTIFIED task (F2e, `nucleo/request/answered_task`): a Brain Worker takes it on THAT row with the `message` playbook,
his request and his answer as its brief, and the send's echo as `done_when` — no new row, no re-run model turn (F2d's
re-run turn said «sending it now» and called nothing in 6 of 14 runs). One answer starts at most one worker
(`inline_ask.take`, the same once-per-`ask_id` lock as a door's re-run).
"""
from __future__ import annotations

from nucleo.request import note
from nucleo.request.ending import leaving_acts

#: The observer kind (family `flash`): {trace, widget, leaves, text}.
KIND = "ask_outside_door"
#: A reply whose last character is one of these closes on a question. Punctuation, not vocabulary.
_QUESTION_MARKS = "?？؟"


def measure(brief, reply: str, *, did_act: bool, asked_which: bool = False, emit=None) -> dict | bool:
    """Emit `ask_outside_door` when this turn asked about a door's act without reaching the door. The event's extra
    ({trace, widget, leaves, which_person}) when emitted — what `held` makes durable — else False."""
    last = str(reply or "").rstrip().rstrip("»\"'”)")[-1:]
    if did_act or not (asked_which or (last and last in _QUESTION_MARKS)):
        return False
    try:   # the card the brief named
        from nucleo.turn import verdicts
        wid, _info = verdicts.read(brief, "catalog_widget", None)
        wid = "" if not wid or str(wid) == "none" else str(wid)
    except Exception as e:  # noqa: BLE001
        note(e)
        wid = ""
    leaves = leaving_acts(wid) if wid else []
    if not leaves:
        return False
    try:
        trace = ""
        from voice import trace as _trace
        trace = str(_trace.current() or "")
    except Exception as e:  # noqa: BLE001
        note(e)
    extra = {"trace": trace, "widget": wid, "leaves": leaves, "which_person": bool(asked_which)}
    try:
        if emit is None:
            from voice.observer import emit as _emit
            emit = _emit
        emit(KIND, "🚪 asked outside the door", text=str(reply or "")[:300], role="system", extra=extra)
        return extra
    except Exception as e:  # noqa: BLE001
        note(e)
        return False

#: What the row retains: his request, to be said again with his answer.
UTTERANCE = "utterance"


def held(measured: dict, reply: str, said: str) -> str:
    """The turn asked about a door's act it never reached (`measured` is the `ask_outside_door` extra): its row waits
    on that question. Returns the `ask_id`, or "" when nothing could be made durable."""
    wid = str((measured or {}).get("widget") or "")
    leaves = [str(a) for a in (measured or {}).get("leaves") or []]
    q = " ".join(str(reply or "").split())
    if not (wid and leaves and q and str(said or "").strip()):
        return ""
    try:
        from nucleo.circuit import asker, ledger
        from nucleo.request import model, send_task_words
        from nucleo.runtime_ids import next_seq
        from observability import identity
        # A card whose leaving act declares its slots keeps the question on a SEND TASK: his words resolved into the
        # act's slots (the person his word names), the question about the one slot the turn lacks, and his answer
        # fills that slot on that row (`send_task.answered`) — no worker, no re-run turn.
        if (ask_id := send_task_words.hold(wid, leaves, said, q, brief=None)):
            return ask_id
        row = model.opened(wid, leaves[0], text=said)
        if not row:
            return ""
        ask_id = f"{row}-q{next_seq('inline.ask')}"
        session = identity.session_id()
        try:
            # The people his words name when they name several: the directory's own resolution of his sentence, the
            # same rows the turn's people block showed the model (`contactos.people_named`) — never his words re-read.
            from widgets.contactos import data as _cd
            cands = [str(r.get("name") or "") for r in _cd.people_named(said or "") if r.get("name")]
            cands = cands if len(cands) > 1 else []
        except Exception as e:  # noqa: BLE001
            note(e)
            cands = []
        entry = {"ask_id": ask_id, "corr_id": ask_id, "uid": row, "task_id": "", "inline": True, "action": "",
                 "question": q, "answer": "", "result": None, "session": session,
                 "consent": "ask_which" if cands else "ask_fact", "candidates": cands, "options": cands,
                 "said": True,
                 "retained": {"kind": UTTERANCE, "text": " ".join(str(said).split()), "widget": wid,
                              "actions": leaves, "slot": "", "candidates": cands}}
        ledger.store().task_patch(row, session_id=session)
        return asker.ask(row, entry)
    except Exception as e:  # noqa: BLE001 — a question that could not be made durable stays counted, as before
        note(e)
        return ""


def claimed(brief, reply: str, said: str, *, emit=None) -> int:
    """The verdict names a LEAVING act surely and no call reached its door, yet the turn did not ask: its words stand
    for an act nobody made (measured on his engine, 2026-11-05: «manda un mensaje a pablo diciendo hola» → verdicts
    `screen_action = mensajeria:send_to` 0.98, `end_state = mensajeria:sent`, `wants_words = act`; reply «Sending
    "hola" to Pablo now…» with ZERO calls — the line claimed a send that would never happen). An identified act the
    turn did not make is an IDENTIFIED TASK (§2b): the request goes to a Brain Worker on its own row with the `message`
    playbook (the same hand-off as an answered send, `answered_task`), so the start the line announced is real. Not a
    re-run after the stream: one routing decision at the close, read off verdicts the turn already paid for. Returns
    the worker's task id, or 0 when nothing qualified or started."""
    last = str(reply or "").rstrip().rstrip("»\"'”)")[-1:]
    text = " ".join(str(said or "").split())
    if not text or (last and last in _QUESTION_MARKS):
        return 0                                   # a question is `measure`/`held`'s, never a claim
    try:
        from nucleo.turn import verdicts
        from widgets import effects
        from nucleo.request import base
        target, info = verdicts.read(brief, "screen_action", None, min_confidence=verdicts.VETO)
        wid, _sep, act = str(target or "").partition(":")
        if not (info and wid and act and effects.leaves(base(wid), act)):
            return _an_order_nothing_served(brief, text, emit=emit)
        return to_message_task(wid, act, said, src="unreached", emit=emit)
    except Exception as e:  # noqa: BLE001 — never takes the turn down; the line stands as it was
        note(e)
        return 0


def to_message_task(wid: str, act: str, said: str, *, src: str, why: str = "", emit=None) -> int:
    """A leaving act the turn could not make itself becomes its OWN task: a row for the card's act and a Brain Worker
    on it with the `message` playbook (§2b — the worker resolves the facts or asks). Shared by a sure act no call
    reached (`claimed`) and a routed send whose turn stopped a worker and started nothing in its place
    (`nucleo/turn/routed_sends.keep`). Returns the worker id, or 0."""
    from nucleo.circuit import ledger
    from nucleo.request import model
    from nucleo.request.answered_task import PLAYBOOK
    text = " ".join(str(said or "").split())
    # The row is born with what his words already resolve (the person, as his word) and its end state, so the worker
    # composes the text and sends — it never rediscovers the person from the inbox (`send_task.retain`).
    row = send_task_row(wid, act, said) or model.opened(wid, act, text=said)
    if not (row and text):
        return 0
    ledger.store().task_patch(row, playbook=PLAYBOOK)
    from nucleo.acts.errand import escalate_to_slowbrain
    tid = int(escalate_to_slowbrain(text, context={"src": src, "kind": "generic", "task_uid": row,
                                                   "playbook": PLAYBOOK, "surface": "voz"}) or 0)
    if emit is None:
        from voice.observer import emit as _emit
        emit = _emit
    emit("brain", "🚪 a leaving act the turn could not make → its task", text=text[:300], role="system",
         extra={"cat": "flash", "task_id": row, "widget": wid, "act": act, "worker": tid, "src": src, "why": why})
    return tid


def _an_order_nothing_served(brief, text: str, *, emit=None) -> int:
    """V2-852 (his engine, 2026-11-05): «Pregúntale a Raquel cuándo vuelve» was read `request_type = order` 0.94, the
    send itself only `mensajeria:send_to` 0.43, and the reply «I'll try again — let me get a message to Raquel now»
    went out with ZERO calls and no task: a start announced with nothing behind it. A SURE order that no door served,
    that is not answered by words (`wants_words` is not «tell») and that the turn did not ask about is an identified
    request whose act the turn could not make: when the act it leaned to (any confidence) LEAVES the machine, it goes to
    a Brain Worker with the `message` playbook (§2b — the worker resolves the facts or asks). An order about the screen
    stays the turn's. Returns the worker id or 0."""
    from nucleo.turn import verdicts
    kind, info = verdicts.read(brief, "request_type", None, min_confidence=verdicts.VETO)
    words, _w = verdicts.read(brief, "wants_words", None)
    if not (info and str(kind or "") == "order") or str(words or "") == "tell":
        return 0
    leaned, _l = verdicts.read(brief, "screen_action", None, min_confidence=0.0)
    wid, _sep, act = str(leaned or "").partition(":")
    from widgets import effects
    from nucleo.request import base
    if not (wid and act and effects.leaves(base(wid), act)):
        return 0          # an order about the screen stays the turn's: a card act is never a worker's 15 s
    from nucleo.request.answered_task import PLAYBOOK
    ctx = {"src": "unserved", "kind": "generic", "surface": "voz", "playbook": PLAYBOOK}
    from nucleo.acts.errand import escalate_to_slowbrain
    tid = int(escalate_to_slowbrain(text, context=ctx) or 0)
    if emit is None:
        from voice.observer import emit as _emit
        emit = _emit
    emit("brain", "🚪 a sure order no door served → its task", text=text[:300], role="system",
         extra={"cat": "flash", "worker": tid, "leaned": str(leaned or ""), "playbook": ctx.get("playbook", "")})
    return tid


def send_task_row(wid: str, act: str, said: str) -> str:
    """The send task's row for an act the turn never called: retained with the person his words name (`send_task`),
    "" when the act declares no slots or nothing of his resolves."""
    try:
        from nucleo.request import send_task, send_task_words
        payload = send_task_words.payload_from_words(wid, act, said)
        return send_task.retain(wid, act, payload, said) if payload else ""
    except Exception as e:  # noqa: BLE001
        note(e)
        return ""
