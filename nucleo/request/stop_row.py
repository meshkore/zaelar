"""nucleo/request/stop_row.py — a stop told by the ROW, never by the model's account of it (V2-852 T03/T04/T05).

Three facts of one stop, beside the verdict that decides it (`stop.py`): which thing it stops (a STEP parked on his OK is
not its task: `parked_step`, `decline_step`), what the turn may say about it (only what its door did: `in_play`,
`say_the_row`), and why the row ended (his words of the stopping turn on the record: `stopped_by_his_turn`).
"""
from __future__ import annotations

from loguru import logger

from nucleo.request import stop as _stop

DECLINE_STEP = "decline_step"
STEP_CHOICE = "he refuses or cancels only the STEP the task is waiting for his OK on; the task itself goes on"

#: Offered only while a step of a running task is parked on his OK (`parked_step`): with none, it names nothing.
_STEP_INSTRUCTIONS = ("Answer 'decline_step' when what he refuses, cancels or closes is that STEP and not the task: the "
                      "task goes on without it.")


def parked_step() -> dict | None:
    """V2-852 T03 — a STEP of a running task waiting for his OK: `{"step", "question", "task", "uid"}`, or None.

    One identity per task: a worker drives tools whose own registries number their steps (a browser tab is «2»). A
    stop said while such a step waits may be about the step — the question then offers that reading, and the stop
    of a step declines the step, never the row (`repair`). Only a step a LIVE row owns counts: a tab he drives
    himself is his own task. Never raises."""
    try:
        from widgets.navegador import tasks as _nav
        step = _nav.waiting_id()
        q = str(((_nav.get(step) or {}).get("question") or "")).strip() if step else ""
        if not q:
            return None
        row = _nav.row_of(step)
        return {"step": step, "question": q, "task": row["title"], "uid": row["uid"]} if row.get("uid") else None
    except Exception as e:  # noqa: BLE001
        return logger.debug(f"stop_decision: parked step unreadable: {e!r}") or None


def decline_step(step: dict, acted: dict | None = None) -> bool:
    """The stop of a STEP: its question is answered NO and the row runs on. True when the answer reached it."""
    try:
        from widgets.navegador import tasks as _nav
        _nav.answer(str(step["step"]), "no")
        if acted is not None:
            acted["declined_step"] = str(step["step"])
        return True
    except Exception as e:  # noqa: BLE001
        return logger.debug(f"stop_decision: the step could not be declined: {e!r}") or False



def decline_parked(acted: dict | None = None) -> list:
    """A sure `decline_step`: the step parked now is declined; no row is cancelled (the empty list says so)."""
    if (step := parked_step()):
        decline_step(step, acted)
    return []


def step_choice(criteria: dict) -> tuple[dict, str]:
    """The stop question's choices and its extra instruction: `decline_step` only while a step is parked."""
    step = parked_step()
    if not step:
        return criteria, ""
    return {**criteria, DECLINE_STEP: STEP_CHOICE}, (f" {_STEP_INSTRUCTIONS} [The task «{step['task'][:80]}» is waiting "
                                                     f"for his OK on a step: «{step['question'][:160]}»]")


# ── V2-852 T04 · the mouth speaks the row, never a stop that did not happen ──────────────────────────────────
def in_play(brief) -> bool:
    """Does the turn's stop verdict, at ANY confidence, point at ending the running errand? Then the model's words of
    the turn may narrate a stop its door has not decided yet: they wait for it (`Hold`), never said ahead of it."""
    try:
        from nucleo.turn import verdicts
        choice, info = verdicts.read(brief, _stop.KEY, None, min_confidence=0.0)
        return bool(info) and _stop.ends(choice)
    except Exception as e:  # noqa: BLE001 — unreadable: today's path, the words flow
        return logger.debug(f"stop_decision: in_play unreadable: {e!r}") or False


def row_line() -> str:
    """The rows' state in one line, in HIS language: what is still running, by its row's title. Never raises."""
    try:
        from i18n import langs
        from nucleo import dispatch
        names = []
        for t in dispatch.resolve_sessions("") or []:
            r = dispatch.get_record(t)
            if r is not None:
                from nucleo.request import title as _title
                names.append(str(getattr(r, "title", "") or "").strip() or _title.provisional(str(r.goal or "")))
        lang = langs.current_language()
        if not names:
            return str(lang.nothing_running or "")
        return str(lang.errand_still_running or "").format(task="», «".join(dict.fromkeys(names)))
    except Exception as e:  # noqa: BLE001
        return logger.debug(f"stop_decision: the rows' line unreadable: {e!r}") or ""


def say_the_row(hold, worker_acted: dict, brain, spoken, send, emit, spoken_text: str = "") -> str:
    """After the turn's acts: the words held while a stop was in play are said only if what they narrate HAPPENED.

    The model that called `stop_worker` writes «stopping it» before the door rules; a vetoed call left them said over
    a task still running (V2-852 T04, session c8a307fd: «Understood — stopping it. Nothing is running now» while the
    search went on for twenty minutes). A stop that RAN: its words stand, unless the chain already said the stop. A
    model stop the door refused: its words are dropped and the rows' state is said instead — the mechanism's outcome,
    not the model's account. No call to the stop door: the words are its answer to something else, said as written.
    Returns what the turn has said."""
    words = str(getattr(hold, "stop_words", "") or "")
    if not words:
        return spoken_text
    hold.stop_words = ""
    said = "".join(spoken or ()).strip()
    called = any(str((c or {}).get("name") or "") == "stop_worker" for c in getattr(brain, "_turn_calls", None) or ())
    if (worker_acted or {}).get("v") == "stop" or not called:
        if said:
            emit("brain", "🤐 held words — the turn already said its stop", role="system", text=words[:160],
                 extra={"cat": "flash", "kind_diag": "stop_words_dropped"})
            return spoken_text
        send(words)
        return (spoken_text + words) if spoken_text else words
    emit("brain", "🤐 the words narrated a stop that did not happen — the rows' state is said", role="system",
         text=words[:160], extra={"cat": "flash", "kind_diag": "stop_not_run"})
    if said:
        return spoken_text
    line = row_line()
    if line:
        send(line)
    return line or spoken_text
