"""nucleo/workers/spawned.py — the sessions this engine opened for its workers (2026-10-14).

Every worker backend starts its CLI with `start_new_session=True`, so the worker's pid IS the id of a new
process session, and everything the worker runs (each Bash tool, a `curl`, a backgrounded `( … & )`) inherits
that session id even after its parent died and it was handed to launchd/init. Ancestry alone loses such an
orphan; the session id does not.

`server/peer_process.py` reads this set to tell a request sent by a worker from one sent by the operator's own
browser or tools. It is remembered for the life of the process, alive or dead: an orphan outlives its worker.
"""
from __future__ import annotations

import threading

_CAP = 2048
_LOCK = threading.Lock()
_SIDS: dict[int, None] = {}          # insertion-ordered: the oldest is dropped first past the cap


def remember(pid: int | None) -> None:
    """Note a worker session leader. Never raises: a spawn must not fail over its own bookkeeping."""
    if not isinstance(pid, int) or pid <= 0:
        return
    with _LOCK:
        _SIDS[pid] = None
        while len(_SIDS) > _CAP:
            _SIDS.pop(next(iter(_SIDS)))


def sessions() -> frozenset[int]:
    with _LOCK:
        return frozenset(_SIDS)


def forget_all() -> None:
    """Tests only."""
    with _LOCK:
        _SIDS.clear()
