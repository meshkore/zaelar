"""nucleo/request/own_question.py — a question Flash asks itself about a door's act is a DURABLE question (V2-851 F2d).

Measured: «send a message to Raquel» with two Raquels in the people block — the model asked «which Raquel?» without
calling the send door. `ask_outside_door` counted it, and that was all: no row waited, no `ask` event, and his answer
only worked if the model happened to call the door on the next turn.

Now the same question goes through THE asker (`nucleo/circuit/asker`), exactly as a door's or a worker's: the turn's
row (opened through `request/model.opened`, the one birth door, when the turn had none) waits for his answer with an
`ask_id`, the question is the reply line he already heard (`said`: the pulse never relays it again), the candidates
are the people the directory resolved for this turn (`directory.asking`, data — never his words re-read), and what is
retained is his REQUEST: {kind: utterance, text, widget, actions}. The widget is the brief's verdict; the actions are
the card's declared acts that leave the machine.

His answer (screen, with its `ask_id`; or a later turn the brief's binding verdict ties to it) resumes the row by
running ONE new turn on the text channel with «<his request> — <his answer>» on THAT row (`model.resuming`): no new
row, and the act that turn reaches settles the row through `circuit.settle` as any inline act's. One answer resumes at
most once (`inline_ask.take`, the same once-per-`ask_id` lock as a door's re-run).
"""
from __future__ import annotations

from loguru import logger

#: What the row retains: his request, to be said again with his answer.
UTTERANCE = "utterance"


def _note(e: BaseException) -> None:
    import sys
    logger.debug(f"own_question: {sys._getframe(1).f_code.co_name} — {type(e).__name__}: {e}")


def _candidates(asked_which: bool) -> list[str]:
    """The people this turn's «which one?» named, as the directory resolved them; [] when it did not ask which."""
    if not asked_which:
        return []
    try:
        from widgets import directory
        return [n for n in directory.asking() if n]
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
        cands = _candidates(bool(measured.get("which_person")))
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


def line(retained: dict, text: str, choice: int | None) -> str:
    """His request said again with his answer: the candidate the verdict chose, else his own words."""
    cands = list(retained.get("candidates") or [])
    answer = cands[int(choice)] if choice is not None and 0 <= int(choice) < len(cands) else " ".join(
        str(text or "").split())
    req = " ".join(str(retained.get("text") or "").split())
    return f"{req} — {answer}" if req and answer else ""


async def resume(uid: str, entry: dict, text: str, choice: int | None = None, *, run=None):
    """Resume row `uid` on his answer: one new text-channel turn with «request — answer», acting on that row."""
    from nucleo.circuit import ledger
    from nucleo.request import inline_ask, model
    retained = entry.get("retained") or {}
    said = line(retained, text, choice)
    if not said or not inline_ask.take(str(entry.get("ask_id") or entry.get("corr_id") or "")):
        return None
    ledger.resumed(uid)
    inline_ask.resuming(uid, retained)
    if run is None:
        from nucleo.cli.turn import run_turn as run
    sid = f"answer:{uid}"
    tok = model.resuming(uid)
    try:
        res = await run(said, sid=sid, execute=True)
    finally:
        model._RESUMES.reset(tok)
        try:
            from nucleo.cli.turn import reset
            reset(sid)
        except Exception as e:  # noqa: BLE001
            _note(e)
    try:
        from voice.observer import emit
        said_back = (res or {}).get("reply") if isinstance(res, dict) else ""
        said_back = " ".join(str(x) for x in said_back) if isinstance(said_back, list) else str(said_back or "")
        emit("brain", "↩ answer resumed its request", text=said[:300], role="system",
             extra={"cat": "flash", "task_id": uid, "ask_id": str(entry.get("ask_id") or ""),
                    "reply": said_back[:300]})
    except Exception as e:  # noqa: BLE001
        _note(e)
    return res
