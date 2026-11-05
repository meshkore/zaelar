"""nucleo/request/own_question.py — a question Flash asks itself about a door's act is a DURABLE question (V2-851 F2d).

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

from loguru import logger

#: What the row retains: his request, to be said again with his answer.
UTTERANCE = "utterance"


def _note(e: BaseException) -> None:
    import sys
    logger.debug(f"own_question: {sys._getframe(1).f_code.co_name} — {type(e).__name__}: {e}")


def _candidates(said: str) -> list[str]:
    """The people his words name when they name several: the directory's own resolution of his sentence, the same
    rows the turn's people block showed the model (`contactos.people_named`) — never his words re-read here."""
    try:
        from widgets.contactos import data as _cd
        rows = _cd.people_named(said or "")
        names = [str(r.get("name") or "") for r in rows if r.get("name")]
        return names if len(names) > 1 else []
    except Exception as e:  # noqa: BLE001
        _note(e)
        return []


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
        from nucleo.request import model
        from nucleo.runtime_ids import next_seq
        from observability import identity
        row = model.opened(wid, leaves[0], text=said)
        if not row:
            return ""
        ask_id = f"{row}-q{next_seq('inline.ask')}"
        session = identity.session_id()
        cands = _candidates(said)
        entry = {"ask_id": ask_id, "corr_id": ask_id, "uid": row, "task_id": "", "inline": True, "action": "",
                 "question": q, "answer": "", "result": None, "session": session,
                 "consent": "ask_which" if cands else "ask_fact", "candidates": cands, "options": cands,
                 "said": True,
                 "retained": {"kind": UTTERANCE, "text": " ".join(str(said).split()), "widget": wid,
                              "actions": leaves, "slot": "", "candidates": cands}}
        ledger.store().task_patch(row, session_id=session)
        return asker.ask(row, entry)
    except Exception as e:  # noqa: BLE001 — a question that could not be made durable stays counted, as before
        _note(e)
        return ""

