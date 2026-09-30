"""nucleo/request_row.py — every request that ACTS is a row of `tasks`, the inline ones included (V2-776 M1).

## Why

Audit of 2026-09-30: «what is going on» lived in six registries — the worker session (RAM), the just-ended
snapshot (RAM, five minutes), the task row (durable, quoted only as a fallback), the third-party errand, the list,
the scheduled job — and the INLINE turn, ~70 % of what the operator asks, left nothing durable at all: its spec in
RAM for thirty minutes, its harness goal for five, its outcome for forty-five seconds. A restart, or an hour of
silence, and the agent could not say what it had just done. Manual session 7850de3f is that: the list had finished
and the agent said «it's all still running».

So a request that acts — a widget data-op, a picture search — opens ONE row here, `kind="inline"`, with the
operator's own words as `goal`, and the row ends with the circuit's verdict. The executor does not change (the op
still runs detached, inline, in milliseconds); what changes is that the RECORD knows about it.

## The shape

  · `begin(text)` — the channel says which words this turn is about, once, before any lane runs. A ContextVar, so
    the detached op tasks the turn spawns inherit it (asyncio copies the context at `create_task`).
  · `opened(widget, action)` — the first op of the turn opens the row; the next ops of the SAME turn reuse it.
    One request, one row, however many calls it took.
  · `settle(uid, verdict, outcome)` — the op's end: a spec that attested, a refusal, a spec the circuit settled
    unmet after its grace. A row that failed never reads better later in the same request.

What never opens a row: a turn with no words (the kickoff), a canvas gesture (show/close/minimize are not
requests of their own — they go through the canvas door, never through here), and a list STEP's own bookkeeping
(the list already writes its step rows; an op inside a step hangs from that step through `parent`).
"""
from __future__ import annotations

import contextvars
import itertools
import time

from loguru import logger

KIND = "inline"
_RANK = {"met": 0, "undeclared": 1, "unverifiable": 2, "unmet": 3}   # a later op never improves a failed row

_TURN: contextvars.ContextVar = contextvars.ContextVar("zaelar_request_turn", default=None)
#: The list STEP a turn is running for (set by `nucleo/batch/runner.py` around the step's turn): its ops hang from it.
_PARENT: contextvars.ContextVar = contextvars.ContextVar("zaelar_request_parent", default="")
_SEQ = itertools.count(1)


def under(step_row_id: str):
    """Mark the list step the next turn runs for. Returns the token for `_PARENT.reset`."""
    return _PARENT.set(str(step_row_id or ""))


def step_parent(_sid: str = "") -> str:
    return _PARENT.get()


def begin(text: str, *, parent: str = "", origin: str = "voz", trace: str = "") -> None:
    """This turn is about these words. No row yet — only an op opens one."""
    t = " ".join(str(text or "").split())
    _TURN.set({"text": t[:600], "uid": "", "parent": str(parent or _PARENT.get() or ""), "origin": origin or "voz",
               "trace": str(trace or "")} if t else None)


def current() -> dict | None:
    return _TURN.get()


def _surface(widget: str) -> str:
    try:
        from widgets import runtime
        return str((runtime.get(str(widget).split("::", 1)[0]) or {}).get("surface") or "")
    except Exception:  # noqa: BLE001
        return ""


def opened(widget: str, action: str, *, text: str = "") -> str:
    """The row of this turn's request, opened by its first op. '' when the turn named no request."""
    turn = _TURN.get()
    if turn is None and text:
        begin(text)
        turn = _TURN.get()
    if not turn:
        return ""
    if turn.get("uid"):
        return turn["uid"]
    from nucleo import tasks as _tasks
    _ts = _tasks.store()
    from nucleo.runtime_ids import boot_id
    uid = f"{boot_id()}-i{next(_SEQ)}"
    now = int(time.time())
    title = turn["text"][:80]
    try:
        _ts.task_put({"id": uid, "title": title, "goal": turn["text"], "kind": KIND, "mode": "now",
                      "state": "running", "visible": True, "origin": turn.get("origin") or "voz",
                      "surface": _surface(widget) or str(widget).split("::", 1)[0],
                      "sheet": str(widget) if "::" in str(widget) else "", "trace_id": turn.get("trace") or "",
                      "parent_id": turn.get("parent") or "", "outcome": f"{widget}:{action}",
                      "created_at": now, "started_at": now})
    except Exception as e:  # noqa: BLE001 — a request that could not be recorded still runs
        logger.debug(f"request_row: could not open ({e})")
        return ""
    turn["uid"] = uid
    return uid


def settle(uid: str, verdict: str, outcome: str = "") -> None:
    """The request's ending, as the circuit judged it: `met | undeclared | unverifiable | unmet`."""
    if not uid:
        return
    from nucleo import tasks as _tasks
    _ts = _tasks.store()
    row = _ts.task_get(uid)
    if row is None:
        return
    prev = str(row.get("verdict") or "")
    if prev and _RANK.get(prev, 0) >= _RANK.get(verdict, 0) and prev != verdict:
        return                                   # a failed op in this request is not undone by a later good one
    state = "failed" if verdict == "unmet" else "done"
    _ts.task_patch(uid, state=state, verdict=verdict, finished_at=int(time.time()),
                   outcome=(outcome or str(row.get("outcome") or ""))[:300])


def verdict_of_attest(out) -> str:
    """`spec.attest`'s answer as a verdict: True met · False unmet (not yet final) · None unverifiable."""
    return {True: "met", False: "unmet"}.get(out, "unverifiable")

