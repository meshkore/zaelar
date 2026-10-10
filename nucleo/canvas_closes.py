"""When did the OPERATOR last close each card? (demo pass 82, 2026-10-03)

I1 «show me a red ferari f40» found no pictures in time and became an errand; I4 «alright close the pictures» closed
the viewer — and two minutes later, in the middle of U1 «play some madonna», that errand's worker ran `show imagenes`
and the viewer sat on screen from U1 to T1. The arbiter is in shadow and its `task-owned` rule allowed it. A card the
operator closed AFTER an errand was commissioned is his decision about his screen, and that errand does not reopen it:
`worker_api` asks `closed_after(card, since)` before a worker's `show`.

Fed from the ONE place every close passes (`voice.observer.emit("widget", "close", …)`), so no caller has to
remember. A close by a worker is not the operator's and is not recorded.
"""
from __future__ import annotations

import time

_CLOSED: dict[str, float] = {}


def _base(card: str) -> str:
    return str(card or "").split("::", 1)[0].strip().lower()


def note(extra: dict | None) -> None:
    """Record one close event. Never raises: only str() and a dict write on whatever arrived."""
    e = extra if isinstance(extra, dict) else {}
    if str(e.get("src") or "").startswith("worker"):
        return
    base = _base(str(e.get("id") or ""))
    if base:
        _CLOSED[base] = time.time()
        _hand_back(base)


def _hand_back(card: str) -> None:
    """A card he closed stops producing and gives the speaker back to what it silenced (V2-781: «close the video
    and keep the music going» left the music paused). Scheduled on the running loop; no loop, nothing to do."""
    try:
        import asyncio
        from widgets import producers
        if producers.spec(card) is None:
            return
        asyncio.get_running_loop().create_task(producers.hand_back(card))
    except Exception as e:  # noqa: BLE001 — a close never fails on bookkeeping (no loop here = nothing to hand back)
        from loguru import logger
        logger.debug(f"canvas_closes: no hand-back for {card}: {e!r}")


def closed_after(card: str, since: float) -> float:
    """The time the operator closed `card` if that was after `since`, else 0."""
    t = _CLOSED.get(_base(card), 0.0)
    return t if since and t > since else 0.0


def _reset_for_tests() -> None:
    _CLOSED.clear()
