"""The SYNCHRONOUS entries into the worker registry, marshalled to the server loop that owns it (§v3·D/O).

The FlashBrain calls these from its job thread and never awaits them. Moved out of `nucleo/dispatch.py` (refactor2710-01)
when they became consequence doors: `dispatch` re-exports them under their historical names, and every name they read
from the registry is read through it at call time, so a patch on `dispatch` still governs them.
"""
from __future__ import annotations

import asyncio

from nucleo import consequence


def _resolve(which: str, *_a, **_k) -> list[str]:
    from nucleo import dispatch
    return dispatch.resolve_sessions(which)


@consequence.door("worker.inject")
def inject_soon(which: str, message: str) -> None:
    """Fire-and-forget: inject into the session(s) of `which`, on the owning loop. NEVER awaited in the turn."""
    from nucleo import dispatch
    if dispatch._LOOP is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(dispatch.inject(which, message), dispatch._LOOP)
    except Exception:
        pass


@consequence.door("worker.stop", neutral=_resolve)
def cancel_soon(which: str) -> list[str]:
    """Fire-and-forget: resolve `which` and KILL it on the owning loop. Returns the ids it is about to kill (for the
    voice). Closed, it still names them: the turn says what it would have stopped."""
    from nucleo import dispatch
    tids = dispatch.resolve_sessions(which)   # a dict read (cheap); the real cancellation goes to the owning loop
    dispatch._qwait.forget(which)             # a stop he ordered also stops an errand waiting for the quota's reset
    if dispatch._LOOP is not None and tids:
        def _do():
            for t in tids:
                dispatch.cancel_session(t)
        try:
            dispatch._LOOP.call_soon_threadsafe(_do)
        except Exception:
            pass
    return tids
