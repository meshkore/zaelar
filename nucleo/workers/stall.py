"""nucleo/workers/stall.py — the stall watchdog (V2-645), and the gate-refusal reader that rode out with it.

STALL WATCHDOG. Measured live (the La Mella session, 2026-09-09): a worker's provider stream died mid-call
(glm-5.3, TCP connections CLOSED, 0% CPU) and the session sat in `async for ev in backend.events()`
FOREVER — no event, no error, no death notice, while the turn kept answering «sigo con ello». Susurro
detected «worker encallado» at +3 min and its audit was in cooldown, so nobody was told. The watchdog
bounds the WAIT for the next backend event: past the limit the caller stops the worker, which then dies
LOUDLY through the existing `_finish()` machinery (death notices, V2-198/V2-237) — what lets the state
line say the truth instead of the model confabulating continuity. Deliberately generous (a deep reasoning
turn can be legitimately quiet for minutes) and deliberately NOT an auto-retry: a blind relaunch can
duplicate side effects — the death notice invites the relaunch instead. `0` disables it.

Extracted from `session.py` (which sat exactly at its architecture-ratchet ceiling) together with
`denied_fragment`, whose only concern is also reading a worker's failure surface.
"""
from __future__ import annotations

import asyncio
import os
import re

from loguru import logger

_STALL_S = float(os.getenv("ZAELAR_WORKER_STALL_S", "300"))

#: How often the wait looks up to ask whether the silence is still the PROVIDER'S. Short enough that a
#: stop/start is noticed well inside the budget, long enough to cost nothing (one `runstate.stopped()`, which
#: is an in-process cache read, every few seconds of an otherwise idle wait).
_TICK_S = 5.0


def _hibernating() -> bool:
    """Is the operator's switch OFF? Then this worker is SIGSTOPped and its silence is OURS (V2-747).

    Measured in his own session, 2026-09-21: he pressed ⏻ at 20:13:20 with one job in flight, `runstate`
    froze it as designed — and at **20:18:20**, five minutes later to the second, this watchdog declared
    «sin respuesta del proveedor en 5 min» and aborted it. Then it pushed him a notification about a task it
    had killed itself. His rule for the switch, verbatim: *«no borrar ni detener, sino sería algo así como
    una hibernación»* — and the freeze is exactly that, so the clock that outlived it turned hibernation
    into a five-minute execution. A frozen process cannot emit; counting that against the provider is
    measuring our own hand.

    Fail-OPEN on purpose: if the switch cannot be read, the wait keeps counting, because a watchdog that
    stops watching on any doubt is the failure this module was built for (V2-645).
    """
    try:
        from nucleo import runstate
        return runstate.stopped()
    except Exception:  # noqa: BLE001
        return False


async def bounded_next(it) -> tuple[str, object]:
    """One step of the backend event stream, bounded: ("ev", event) | ("end", None) | ("stalled", None).

    The bound counts only the time the agent was RUNNING (see `_hibernating`). The read itself is started
    ONCE and waited on in slices — `wait_for` cancels the awaitable it times out on, so re-issuing
    `__anext__()` per slice would drop whatever the provider sent during the slice that expired.
    """
    task = asyncio.ensure_future(it.__anext__())
    try:
        waited = 0.0
        while True:
            slice_s = _TICK_S if _STALL_S > 0 else None
            done, _ = await asyncio.wait({task}, timeout=slice_s)
            if done:
                return "ev", task.result()
            if _hibernating():
                continue                      # frozen time is not provider silence — the clock waits too
            waited += _TICK_S
            if waited >= _STALL_S:
                return "stalled", None
    except StopAsyncIteration:
        return "end", None
    finally:
        if not task.done():
            task.cancel()


def mark_stalled(rec, emit_chip) -> None:
    """Writes the honest death into the record — what dispatch, the sheet and the state line will read."""
    mins = int(_STALL_S // 60) or 1
    logger.warning(f"worker[{rec.task_id}]: STALLED — no backend event in {_STALL_S:.0f}s, stopping")
    try:
        emit_chip("stalled", f"sin respuesta del proveedor en {mins} min — aborto la tarea", ok=False)
    except Exception:  # noqa: BLE001
        pass
    rec.status = "error"
    rec.ok = False
    from i18n import langs as _lg_st          # V2-682 — a spoken ending belongs to the language table
    rec.result_summary = rec.result_summary or _lg_st.current_language().worker_stalled.format(minutes=mins)


# ── the gate's refusal, read (V2-241) ──────────────────────────────────────────────────────────────────────
# WHICH fragment the gate stopped. A correction repeating general rules does not say WHICH command is
# unnecessary; the CLI names it in three different measured forms. Returns "" if the text does not say —
# never invents a fragment, which would ask the worker to rewrite a command it did not write.
_DENIED_RE = (
    re.compile(r"following part requires approval:\s*(.+?)(?:\.\s|$)", re.I | re.S),
    re.compile(r"\bcd in ['\"](.+?)['\"] was blocked", re.I),
    re.compile(r"requires approval:\s*(.+?)(?:\.\s|$)", re.I | re.S),
    re.compile(r"permissions? to use\s+(\S+)", re.I),
)


def denied_fragment(text: str) -> str:
    """The command (or path) named by the gate, trimmed and placed on one line."""
    t = str(text or "")
    for rx in _DENIED_RE:
        m = rx.search(t)
        if m:
            frag = " ".join((m.group(1) or "").split()).strip(" .,:;")
            if frag:
                return frag[:160]
    return ""
