"""nucleo/flash/procs.py — puente FlashBrain → supervisor de procesos de widgets (V2-004 · T63).

The reflection layer can drive independent processes (`backed` widgets such as the browser) without blocking the
voice turn. This module is a **THIN BRIDGE** to `widgets/supervisor.py` — it does NOT duplicate supervision (the
mailbox, backoff, isolation, and deactivation after N failures remain in the host, started in the server lifespan,
on the SAME loop as voice). It only enqueues an order for a widget owner and queries its state.
Enqueuing (rather than executing inline) preserves the `backed` invariant: the owner is the ONLY writer of its store.
"""
from __future__ import annotations


def is_backed(widget_id: str) -> bool:
    """Is `widget_id` a backed widget (with its own supervised process)?"""
    try:
        from widgets import supervisor
        return supervisor.is_backed(widget_id)
    except Exception:
        return False


def dispatch(widget_id: str, action: str, payload: dict | None = None) -> bool:
    """Put an order in the widget owner's MAILBOX (does not block the turn). Return True if it was queued
    (backed and live widget), False otherwise (passive/not started/disabled). Best-effort: never raises."""
    try:
        from widgets import supervisor
        return supervisor.enqueue(widget_id, (action or "").strip(), payload or {})
    except Exception:
        return False


def status(widget_id: str) -> dict:
    """State of the widget's supervised process: {backed, running, disabled, fails}."""
    try:
        from widgets import supervisor
        return supervisor.info(widget_id)
    except Exception:
        return {"backed": False, "running": False, "disabled": False, "fails": 0}


def running() -> list[str]:
    """IDs of backed widgets with a live owner."""
    try:
        from widgets import supervisor
        return supervisor.running()
    except Exception:
        return []
