"""nucleo/circuit/asker.py — THE asker: a task's question is durable, whoever asks it (V2-851 §3/§3a).

One function for both paths that ask him something on a task's behalf: a worker through the bridge
(`nucleo/cli/worker_api_asks._register_ask`) and a door that answered an inline act with a consent ASK
(`nucleo/request/inline_ask`). `ask()` keeps the question and the act it retains on the task's artefact slot `ask`,
makes the row WAIT (`ledger.waiting`, `waiting_for=user_answer`, `ask_id`, `ask`) and emits `worker.ask`, whose bus
subscriber below is the observer's `ask` event — the question on screen. The row and its artefact are the truth; a
restart loses nothing.

Who answers is never decided here: a screen answer carries its `ask_id`, a spoken one is bound by the brief's verdict
(`nucleo/cli/worker_api_bind`), and the answering lives in `nucleo/cli/worker_api_answer`.
"""
from __future__ import annotations

import time

from loguru import logger

#: The task artefact slot that holds the open question and the act it retains.
ASK_SLOT = "ask"
#: The observer kind of a question on screen: {task_id, ask_id, text, session, options?, among?}.
EV_ASK = "ask"


def _note(e: BaseException) -> None:
    """A step of the ask path that failed is said (debug), never swallowed: the row stays the truth either way."""
    import sys
    logger.debug(f"asker: {sys._getframe(1).f_code.co_name} — {type(e).__name__}: {e}")


def artefact(uid: str) -> dict:
    """The question's artefact on row `uid` ({} when there is none)."""
    if not uid:
        return {}
    try:
        from nucleo.circuit import ledger
        got = ledger.store().artifact_get(uid, ASK_SLOT)
        return got if isinstance(got, dict) else {}
    except Exception as e:  # noqa: BLE001
        _note(e)
        return {}


def keep(uid: str, entry: dict) -> None:
    if not uid:
        return
    try:
        from nucleo.circuit import ledger
        ledger.store().artifact_put(uid, ASK_SLOT, entry)
    except Exception as e:  # noqa: BLE001
        _note(e)


def emit_ask(*, task_id: str, ask_id: str, text: str, session: str = "", options=None, among=None) -> None:
    """The `ask` event the screen reads. `options` only when the asker declared them, `among` only for ASK_WHICH."""
    extra = {"task_id": str(task_id or ""), "ask_id": str(ask_id or ""), "text": str(text or ""),
             "session": str(session or "")}
    if options:
        extra["options"] = [str(o) for o in options]
    if among:
        extra["among"] = [str(t) for t in among]
    try:
        from voice import observer
        observer.emit(EV_ASK, "❓ ask", text=str(text or "")[:400], role="system", extra=extra)
    except Exception as e:  # noqa: BLE001
        _note(e)


def _on_bus(ev: dict) -> None:
    """The `worker.ask` subscriber (a bus sink: synchronous, survives no `bus.reset`, so it is re-armed per ask)."""
    if not isinstance(ev, dict) or ev.get("topic") != "worker.ask":
        return
    p = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
    emit_ask(task_id=p.get("task_id") or "", ask_id=p.get("ask_id") or p.get("corr_id") or "",
             text=p.get("question") or "", session=p.get("session") or "", options=p.get("options"))


def _subscribe() -> None:
    try:
        import bus
        bus.add_sink(_on_bus)          # idempotent
    except Exception as e:  # noqa: BLE001
        _note(e)


def ask(uid: str, entry: dict, *, bus_id: str = "") -> str:
    """Record the question `entry` ({ask_id, question, retained, options, session, …}) on row `uid`: the artefact
    keeps it, the row waits for his answer, and the question goes on screen. Returns its `ask_id`."""
    ask_id = str(entry.get("ask_id") or "")
    entry.setdefault("created", time.time())
    entry.setdefault("state", "pending")
    keep(uid, entry)
    if uid:
        try:
            from nucleo.circuit import ledger
            ledger.waiting(uid, ledger.USER_ANSWER, ask_id, str(entry.get("question") or ""))
        except Exception as e:  # noqa: BLE001
            _note(e)
    _subscribe()
    opts = [str(o) for o in (entry.get("options") or []) if str(o or "").strip()]
    try:
        import bus
        bus.emit_sync("worker.ask", {"id": bus_id or uid, "task_id": uid or bus_id, "ask_id": ask_id,
                                     "corr_id": ask_id, "question": str(entry.get("question") or ""),
                                     "session": str(entry.get("session") or ""), **({"options": opts} if opts else {})})
    except Exception as e:  # noqa: BLE001
        _note(e)
    return ask_id


def reshow(asks) -> int:
    """Put open questions back on screen (no voice): after a restart the screen that showed them is a new one."""
    n = 0
    for a in asks or []:
        art = artefact(a["task_id"])
        emit_ask(task_id=a["task_id"], ask_id=a["ask_id"], text=a.get("question") or art.get("question") or "",
                 session=str(art.get("session") or ""), options=art.get("options"))
        n += 1
    return n
