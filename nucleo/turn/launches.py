"""Work a turn has LAUNCHED and that is not anybody's errand yet (V2-784 F1, 2026-10-21).

A listing fast pass runs in a thread for up to tens of seconds before it delivers (`workers/ended` records it) or
escalates (`escalate._tasks` records it). In between it was nowhere — and the operator's 19:23 demo pass fell in
exactly that gap: his fragment launched a hunt, his full sentence arrived 8 s later, found no open flow, and opened
a second hunt and a second sheet. A launch is a flow from the moment it starts: registered here BEFORE it runs,
dropped when it finishes (by then its delivery or its escalation carries it).

Read through `named_errand.starting` → `named_errand.known()`, so every association door sees it with no new reader.
"""
from __future__ import annotations

import itertools
import threading
import time

#: A launch older than this is no longer «in flight»: the fast pass budget is seconds, its network tail ~40 s.
LIVE_S = 120.0

_LIVE: dict[str, dict] = {}
_LOCK = threading.Lock()
_SEQ = itertools.count(1)


def opened(request: str, sheet: str, kind: str = "listing") -> str:
    """Register a launch; returns its id. Never raises."""
    lid = f"pass{next(_SEQ)}"
    with _LOCK:
        _LIVE[lid] = {"id": lid, "request": str(request or "").strip(), "sheet": str(sheet or ""),
                      "kind": kind, "at": time.time()}
    return lid


def closed(lid: str) -> None:
    with _LOCK:
        _LIVE.pop(str(lid), None)


def live(now: float | None = None) -> list[dict]:
    """Launches still in flight, newest first (copies)."""
    now = time.time() if now is None else now
    with _LOCK:
        rows = [dict(v) for v in _LIVE.values() if now - float(v["at"]) <= LIVE_S]
    return sorted(rows, key=lambda r: -r["at"])


def reset() -> None:
    with _LOCK:
        _LIVE.clear()
