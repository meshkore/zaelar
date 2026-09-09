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


async def bounded_next(it) -> tuple[str, object]:
    """One step of the backend event stream, bounded: ("ev", event) | ("end", None) | ("stalled", None)."""
    try:
        if _STALL_S > 0:
            return "ev", await asyncio.wait_for(it.__anext__(), timeout=_STALL_S)
        return "ev", await it.__anext__()
    except StopAsyncIteration:
        return "end", None
    except asyncio.TimeoutError:
        return "stalled", None


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
    rec.result_summary = (rec.result_summary or
                          f"El proveedor dejó de responder ({mins} min sin un solo evento) y "
                          f"aborté la tarea. Se puede relanzar.")


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
