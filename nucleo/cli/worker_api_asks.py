"""nucleo/cli/worker_api_asks.py — a worker's question is DURABLE: the row waits, the act it retains is an artefact.

V2-851 §3/§3a. A worker asks through the bridge → `_register_ask` writes the row (`state=waiting`,
`waiting_for=user_answer`, `ask_id`, `ask`) and the question with its retained act to the task's artefact slot
`ask`, then emits `worker.ask`; the bus sink below turns it into the observer's `ask` event (the question on screen).
The worker's process ends after asking; an answer resumes THAT task's session (`nucleo/cli/worker_api_resume`).

The RAM registry (`worker_api._ACTS`) is only a cache of the live session's questions; the truth is the row and its
artefact, so a restart loses nothing. Which waiting task an utterance answers is never decided here: a screen answer
carries its `ask_id`, a spoken one is bound by the brief's verdict (`nucleo/cli/worker_api_bind`); the answering
lives in `nucleo/cli/worker_api_answer`.
"""
from __future__ import annotations

import time

from nucleo.circuit.ledger import USER_ANSWER  # what a task waits for when it waits for his answer


def purge_task(task_id: str) -> int:
    """A dead session's PENDING cache entries are dropped (the durable question stays on its row). Called by dispatch."""
    n = 0
    for corr, e in list(_m._ACTS.items()):
        if e.get("task_id") == str(task_id) and e.get("state") == "pending":
            _m._ACTS.pop(corr, None)
            n += 1
    return n


def _prune() -> None:
    """Prune old ANSWERED entries so the registry never grows without limit."""
    cut = time.time() - _m._ANSWERED_TTL_S
    for corr, e in list(_m._ACTS.items()):
        if e.get("state") == "answered" and float(e.get("created") or 0) < cut:
            _m._ACTS.pop(corr, None)


# The durable half — artefact, the row's wait, the question on screen — is THE asker's, shared with the inline path.
from nucleo.circuit.asker import (  # noqa: E402,F401 — one asker for the worker and the inline door
    _note, artefact as _artefact, emit_ask, keep as _keep,
)


def _register_ask(rec, question: str, action: str = "ask_user", retained: dict | None = None,
                  options: list | None = None) -> str:
    """Record a question (ask_user or an act's CONFIRM, §v3·K): the row WAITS, the retained act is an artefact, and
    `worker.ask` is emitted. The session is marked parked: its process ends and an answer resumes it by id."""
    _m._prune()
    corr = _m._new_corr(rec.task_id, action)
    uid = str(getattr(rec, "uid", "") or "")
    opts = [str(o) for o in (options or []) if str(o or "").strip()]
    entry = {"corr_id": corr, "ask_id": corr, "task_id": str(rec.task_id), "uid": uid, "action": action,
             "question": question, "state": "pending", "answer": "", "result": None, "retained": retained or {},
             "options": opts, "session": str(getattr(rec, "native_sid", "") or ""), "created": time.time()}
    _m._ACTS[corr] = entry
    rec.waiting_on = "user"
    rec.ask = question
    rec.ask_corr = corr
    try:
        rec.parked = True              # the session ends after asking; `_finish` parks it instead of closing
    except Exception as e:  # noqa: BLE001
        _note(e)
    from nucleo.circuit import asker
    asker.ask(uid, entry, bus_id=str(rec.task_id))
    return corr


# ── what waits (the rows are the truth) ────────────────────────────────────────────────────────────────────
def open_asks() -> list[dict]:
    """Every task that waits for his answer, oldest first: `{task_id (row id), ask_id, question, title, since}`."""
    out = []
    try:
        from nucleo.circuit import ledger
        _ts = ledger.store()
        rows = _ts.tasks_where(states=("waiting",), visible_only=False, limit=50)
    except Exception:  # noqa: BLE001
        rows = []
    for r in rows:
        if str(r.get("waiting_for") or "") != USER_ANSWER or not r.get("ask_id"):
            continue
        art = _artefact(str(r.get("id") or ""))
        out.append({"task_id": str(r.get("id") or ""), "ask_id": str(r.get("ask_id") or ""),
                    "question": str(r.get("ask") or ""), "title": str(r.get("title") or r.get("goal") or ""),
                    "since": int(r.get("waiting_since") or 0),
                    # an inline door's ASK_WHICH: the candidates the binding verdict chooses among (V2-851 §3a)
                    "candidates": [str(c) for c in (art.get("candidates") or [])], "said": bool(art.get("said"))})
    return out


def open_ask(uid: str) -> dict | None:
    """The question task `uid` waits on, or None when it waits on none."""
    return next((a for a in open_asks() if a["task_id"] == str(uid or "")), None)


def has_pending_ask() -> bool:
    return bool(open_asks()) or any(e["state"] == "pending" for e in _m._ACTS.values())


def pending_asks() -> list[dict]:
    """Open questions, oldest first, for the voice relay — never a binding (`worker_api_bind` binds)."""
    seen, out = set(), []
    for a in open_asks():
        seen.add(a["ask_id"])
        out.append({"corr_id": a["ask_id"], "ask_id": a["ask_id"], "task_id": a["task_id"], "said": a["said"],
                    "question": a["question"], "action": (_artefact(a["task_id"]).get("action") or "ask_user")})
    for e in sorted(_m._ACTS.values(), key=lambda e: e["created"]):
        if e["state"] == "pending" and e["corr_id"] not in seen:
            out.append({"corr_id": e["corr_id"], "ask_id": e["corr_id"], "task_id": e.get("uid") or e["task_id"],
                        "question": e["question"], "action": e["action"]})
    return out


def _clear_waiting(task_id: str, corr_id: str) -> None:
    try:
        from nucleo import dispatch
        rec = dispatch.get_record(task_id)
        if rec is not None and getattr(rec, "ask_corr", "") == corr_id:
            rec.waiting_on = ""
            rec.ask = ""
            rec.ask_corr = ""
    except Exception as e:  # noqa: BLE001
        _note(e)


from nucleo.cli import worker_api as _m  # noqa: E402 — last, so importing this module first still resolves
