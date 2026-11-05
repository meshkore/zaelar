"""nucleo/cli/worker_api_asks.py — a worker's question is DURABLE: the row waits, the act it retains is an artefact.

V2-851 §3/§3a. A worker asks through the bridge → `_register_ask` writes the row (`state=waiting`,
`waiting_for=user_answer`, `ask_id`, `ask`) and the question with its retained act to the task's artefact slot
`ask`, then emits `worker.ask`; the bus sink below turns it into the observer's `ask` event (the question on screen).
The worker's process ends after asking; an answer resumes THAT task's session (`nucleo/cli/worker_api_resume`).

The RAM registry (`worker_api._ACTS`) is only the cache the bridge's re-poll reads; the truth is the row and its
artefact, so a restart loses nothing. Which waiting task an utterance answers is never decided here: a screen answer
carries its `ask_id`, a spoken one is bound by the brief's verdict (`nucleo/cli/worker_api_bind`); the answering
lives in `nucleo/cli/worker_api_answer`.
"""
from __future__ import annotations

import time

from loguru import logger



def _note(e: BaseException) -> None:
    """A step of the ask path that failed is said (debug), never swallowed: the row stays the truth either way."""
    import sys
    logger.debug(f"worker_api_asks: {sys._getframe(1).f_code.co_name} — {type(e).__name__}: {e}")

#: The task artefact slot that holds the open question and the act it retains.
ASK_SLOT = "ask"
#: What a task waits for when it waits for his answer (`ledger.USER_ANSWER`).
USER_ANSWER = "user_answer"
#: The observer kind of a question on screen: {task_id, ask_id, text, session, options?, among?}.
EV_ASK = "ask"


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


# ── the row (adapter over `ledger.waiting/resumed`, which F1a lands; the fallback writes the same columns) ──────
def _row_waits(uid: str, ask_id: str, question: str) -> None:
    if not uid:
        return
    from nucleo.circuit import ledger
    fn = getattr(ledger, "waiting", None)
    if callable(fn):
        fn(uid, USER_ANSWER, ask_id, question)
        return
    from memory import tasks_store as _ts
    row = _ts.task_get(uid)
    if row is None or str(row.get("state") or "") in _ts.DONE_STATES:
        return
    now = int(time.time())
    _ts.task_patch(uid, state="waiting", waiting_for=USER_ANSWER, waiting_since=now, deadline=now + 7 * 86400,
                   ask_id=ask_id, ask=str(question or "")[:600])


def _row_resumed(uid: str) -> None:
    if not uid:
        return
    from nucleo.circuit import ledger
    fn = getattr(ledger, "resumed", None)
    if callable(fn):
        fn(uid)
        return
    from memory import tasks_store as _ts
    row = _ts.task_get(uid)
    if row and row.get("state") == "waiting" and row.get("waiting_for"):
        _ts.task_patch(uid, state="running", waiting_for="", waiting_since=None, deadline=None)


def _artefact(uid: str) -> dict:
    if not uid:
        return {}
    try:
        from memory import tasks_store as _ts
        got = _ts.artifact_get(uid, ASK_SLOT)
        return got if isinstance(got, dict) else {}
    except Exception as e:  # noqa: BLE001
        _note(e)
        return {}


def _keep(uid: str, entry: dict) -> None:
    if not uid:
        return
    try:
        from memory import tasks_store as _ts
        _ts.artifact_put(uid, ASK_SLOT, entry)
    except Exception as e:  # noqa: BLE001
        _note(e)


# ── the question on screen: `worker.ask` has a subscriber, and its evidence is the observer's `ask` event ───────
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
    _keep(uid, entry)
    try:
        _row_waits(uid, corr, question)
    except Exception as e:  # noqa: BLE001
        _note(e)
    _subscribe()
    try:
        import bus
        bus.emit_sync("worker.ask", {"id": rec.task_id, "task_id": uid or str(rec.task_id), "ask_id": corr,
                                     "corr_id": corr, "question": question, "session": entry["session"],
                                     **({"options": opts} if opts else {})})
    except Exception as e:  # noqa: BLE001
        _note(e)
    return corr


# ── what waits (the rows are the truth) ────────────────────────────────────────────────────────────────────
def open_asks() -> list[dict]:
    """Every task that waits for his answer, oldest first: `{task_id (row id), ask_id, question, title, since}`."""
    out = []
    try:
        from memory import tasks_store as _ts
        rows = _ts.tasks_where(states=("waiting",), visible_only=False, limit=50)
    except Exception:  # noqa: BLE001
        rows = []
    for r in rows:
        if str(r.get("waiting_for") or "") != USER_ANSWER or not r.get("ask_id"):
            continue
        out.append({"task_id": str(r.get("id") or ""), "ask_id": str(r.get("ask_id") or ""),
                    "question": str(r.get("ask") or ""), "title": str(r.get("title") or r.get("goal") or ""),
                    "since": int(r.get("waiting_since") or 0)})
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
        out.append({"corr_id": a["ask_id"], "ask_id": a["ask_id"], "task_id": a["task_id"],
                    "question": a["question"], "action": (_artefact(a["task_id"]).get("action") or "ask_user")})
    for e in sorted(_m._ACTS.values(), key=lambda e: e["created"]):
        if e["state"] == "pending" and e["corr_id"] not in seen:
            out.append({"corr_id": e["corr_id"], "ask_id": e["corr_id"], "task_id": e.get("uid") or e["task_id"],
                        "question": e["question"], "action": e["action"]})
    return out


def active_ask() -> dict | None:
    """The oldest open question — what the voice relay recounts next. Only a RELAY: no answer is ever bound by age."""
    p = _m.pending_asks()
    return p[0] if p else None


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
