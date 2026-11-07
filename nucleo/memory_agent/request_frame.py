"""V2-858 T547 — the commitment net's request, anchored to the day it was said (no model to rephrase it)."""
from __future__ import annotations


def today_iso() -> str:
    """The day the turn was said, from the memory clock (simulations move it; the wall clock would not)."""
    import datetime as _dt
    try:
        from memory import api as _memapi
        now = _memapi.now()
    except Exception:  # noqa: BLE001
        import time as _time
        now = _time.time()
    return _dt.datetime.fromtimestamp(now).date().isoformat()


def dated(t: str) -> str:
    """A raw order kept by the commitment net, anchored to the day it was said. Language-neutral on purpose: the
    net has no model to rephrase it, and an ISO date is read the same in every language."""
    return f"[{today_iso()}] {(t or '').strip()}"
