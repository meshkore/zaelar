"""A task MATTER goes to its task — the row and the out-of-turn mouth — never as a note in the next turn's prompt
(V2-851 F4, §8: «the notes mailbox for task matters» dies here; `brain_notes` itself stays until F5).

`told(matter, task_id=… | key=…)`:
  · the ROW, when the matter has one: a question for him makes it WAIT for his answer with the question
    (`ask=True` → `ledger.waiting(…, user_answer, ask=…)`), a wait for something else names it (`waiting_for`);
  · the FLOW: one `task` event (literal label) with the matter, its task or key — what observability and the battery
    read, and what Flash reads back from the row when he asks how it is going (§2b);
  · the MOUTH, unless `speak=False`: one line composed in his language from the matter (`spoken_delivery.line`, the
    composer the delivery already uses) through `pulse/notices.notify` with the task's identity, or the notice `key`
    when the matter belongs to no row (a connector's send result, a widget build, a browser task).
The matter is the FACT, in plain words; how it is said is the composer's, in the session's language.
"""
from __future__ import annotations

import asyncio
import collections
import threading

from loguru import logger

#: The matters told in this process, newest last (bounded) — what a test or a debugging session reads back.
_TOLD: collections.deque = collections.deque(maxlen=64)


def drain() -> list[str]:
    """The matters told since the last drain, oldest first (and forget them)."""
    out = list(_TOLD)
    _TOLD.clear()
    return out


def _clean(matter: str) -> str:
    t = " ".join(str(matter or "").split())
    return t.removeprefix("[SISTEMA]").strip()


def _row(task_id: str, matter: str, ask: bool, waiting_for: str) -> None:
    if not task_id:
        return
    try:
        from nucleo.circuit import ledger
        if ledger.store().task_get(task_id) is None:
            return
        if ask:
            ledger.waiting(task_id, ledger.USER_ANSWER, ask=matter[:600])
        elif waiting_for:
            ledger.waiting(task_id, waiting_for)
    except Exception as e:  # noqa: BLE001 — the matter is still told
        logger.debug(f"task_event: row {task_id} not written — {e!r}")


async def _say(matter: str, task_id: str, key: str, goal: str, ok: bool) -> None:
    try:
        from nucleo.pulse import notices
        from nucleo.workers import spoken_delivery as _sd
        line = await _sd.line(goal or matter[:80], matter, ok=ok) or _sd.clipped(matter)
        await notices.notify("zaelar", line, task_id=task_id, key="" if task_id else key, kind="info")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"task_event: not said — {type(e).__name__}: {e}")


def _soon(coro) -> None:
    try:
        asyncio.get_running_loop().create_task(coro)
    except RuntimeError:                         # no loop here (a connector thread): its own, in a thread
        threading.Thread(target=asyncio.run, args=(coro,), daemon=True, name="task-event").start()


def told(matter: str, *, task_id: str = "", key: str = "", goal: str = "", ok: bool = True, ask: bool = False,
         waiting_for: str = "", speak: bool = True) -> None:
    """A task matter: on its row, in the flow, and said once out of turn. Never raises."""
    m = _clean(matter)
    if not m:
        return
    task_id = str(task_id or "")
    _TOLD.append(m)
    _row(task_id, m, ask, waiting_for)
    try:
        from voice.observer import emit
        emit("task", "📌 a task matter, on its task", role="system", text=m[:300],
             extra={"cat": "events", "task_id": task_id, "key": key, "ask": bool(ask), "waiting_for": waiting_for,
                    "ok": bool(ok), "spoken": bool(speak)})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"task_event: not recorded — {e!r}")
    if speak:
        _soon(_say(m, task_id, key or f"matter:{abs(hash(m)) % 10**10}", goal, ok))
