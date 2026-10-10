"""widgets/late_report.py — a card that learns, AFTER the reply, that what the agent just started did not happen.

Measured in `build-a-video-playlist-from-links` (ES, 2026-10-10): «Ponla ya» → `youtube:play` returned ok, the turn
said «Voy con ella.», and 1.2 s later the embedded player reported `player_error` 150 twice (embedding refused) —
the list ended `blocked_notice: exhausted`, nothing could play, and the conversation never heard it. The reply was
honest when it was said; the fact that made it false arrived through the UI route (`POST /widgets/{id}/action`,
the card's own JS), which only answers the browser.

The mechanism: a widget's result for a UI-origin action may carry `tell` — one operator-facing sentence, already in
the agent's language — when that action UNDOES what an order of the agent's was promising. It is delivered as a
proactive message (`voice.proactive.notify`: spoken with a live session, a note for the next turn otherwise) only
when an AGENT order touched that card within `WINDOW_S`: a failure on something the operator started with his own
hands is already in front of him, and nobody promised it. Nothing here reads the widget's vocabulary.
"""
from __future__ import annotations

import time

#: How long after an agent order a late failure is still «what you just told him would happen».
WINDOW_S = 30.0

_last_agent_order: dict[str, float] = {}
_pending: set = set()


def _base(wid: str) -> str:
    return str(wid or "").split("::", 1)[0].strip().lower()


def note_agent_order(wid: str, *, now: float | None = None) -> None:
    """The brain (or a worker) just ran a data-op on this card."""
    _last_agent_order[_base(wid)] = time.time() if now is None else float(now)


def agent_ordered_recently(wid: str, *, now: float | None = None) -> bool:
    t = _last_agent_order.get(_base(wid))
    return t is not None and ((time.time() if now is None else now) - t) <= WINDOW_S


def deliver(wid: str, res) -> bool:
    """Say the result's `tell` when it falsifies a recent agent order. True when it was handed over.

    Scheduled, never awaited: `notify` may wait for a quiet moment, and the caller is the browser's HTTP request."""
    try:
        said = str((res or {}).get("tell") or "").strip() if isinstance(res, dict) else ""
        if not said or not agent_ordered_recently(wid):
            return False
        import asyncio

        from voice import proactive
        from voice.observer import emit
        emit("widget", "🩹 lo que el agente acababa de empezar no ocurrió — se dice", text=said[:160],
             extra={"id": _base(wid), "is_error": True})
        task = asyncio.get_running_loop().create_task(proactive.notify(_base(wid), said, speak=True, kind="notify"))
        _pending.add(task)                       # a bare task can be collected before it runs
        task.add_done_callback(_pending.discard)
        return True
    except Exception:  # noqa: BLE001
        return False
