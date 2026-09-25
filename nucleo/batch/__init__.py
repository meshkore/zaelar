"""A message that hands over SEVERAL tasks becomes a LIST (V2-771).

The one door every channel uses: `intake(text, origin)`. It answers «is this a list?» (`detect`) and, when it
is, starts the list in the background and hands back the ONE line the operator hears on receipt. `None` means
«not a list» — the caller runs today's single turn, bit for bit, which is also what every doubt in here falls
back to.

The receipt goes out as soon as the verdict is in (~1-2 s), BEFORE the split (~5 s): he hears that it is a
list and that work started, not a count and never the list read back. Splitting, storing and running happen in
the list's own task (`start` → `split` → `runner`). If the split comes back empty the whole message becomes a
list of ONE step — today's single turn, run from here — so a list that was acknowledged is never dropped.

Before this module a 4 000-char setup message was one turn, and six per-turn limits each dropped part of it
without a word (the input clamp kept its last 1 600 chars, the memory distiller read its first 600, five
widget writes, three workers…). None of those limits was wrong for a turn; the message was not a turn.

Design, measurements and what is deliberately out of scope: `.meshkore/docs/modules/zaelar-task-lists.md`.
"""
from __future__ import annotations

import asyncio

from loguru import logger

#: Strong references to the list tasks we start — an asyncio task nobody holds can be collected mid-run.
_TASKS: set = set()


def ack() -> str:
    """What he hears on receipt: that it is a list and that work has started. Never the list."""
    from i18n import langs
    return langs.current_language().list_started


async def start(text: str, *, origin: str = "voz", run: bool = True) -> str:
    """Split, store and (by default) run a message already known to be a list. Returns the list's uid."""
    from . import runner, split
    steps, how = await asyncio.to_thread(split.split, text)
    if len(steps) < 2:
        runner._emit("📋 lista: no se pudo partir — un solo paso", text=text[:200], how=how)
        steps, how = [{"title": text[:48], "kind": "other", "say": text}], "whole"
    uid = runner.create(text, steps, origin=origin, how=how)
    runner._emit("📋 lista creada", text=f"{len(steps)} pasos ({how})", uid=uid, n=len(steps), how=how)
    if run:
        await runner.run(uid)
    return uid


def _spawn(coro) -> None:
    task = asyncio.get_running_loop().create_task(coro)
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


async def intake(text: str, *, origin: str = "voz") -> dict | None:
    """{ack} when `text` is a list and it was started; None otherwise (run today's turn)."""
    from . import detect, runner
    try:
        if not detect.could_be_a_list(text):
            return None
        is_list, why = await detect.is_a_list(text)
        runner._emit("📋 lista: ¿es una lista?", text=text[:200], verdict=why, is_list=is_list)
        if not is_list:
            return None
    except Exception as e:  # noqa: BLE001 — the door never breaks a turn; today's path is the fallback
        logger.warning(f"lista: intake failed, running the message as one turn: {e!r}")
        return None
    _spawn(start(text, origin=origin))
    return {"ack": ack()}


def run_later(uid: str) -> None:
    """Start an already stored list in the background."""
    from . import runner
    _spawn(runner.run(uid))


def status(uid: str) -> dict:
    """{list, steps, summary} as stored, or {} — the read the HTTP route and the harness use."""
    from . import runner
    row = runner._store().task_get(uid)
    if not row:
        return {}
    return {"list": row, "steps": runner.steps_of(uid),
            "summary": {k: (len(v) if isinstance(v, list) else v) for k, v in runner.summary(uid).items()}}


def resume() -> list[str]:
    """Restart the lists a restart interrupted. Called once from the engine's startup."""
    from . import runner
    return runner.resume()
