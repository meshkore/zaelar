"""nucleo/runtime_ids.py — the ONE owner of process identity: the boot stamp and the sequence counters.

F5 of the 2026-08-23 architecture audit. Three incidents in 48 hours had the SAME shape — a per-instance counter
read as if it were global:

  · `escalate._seq` restarts at 0 in every process, so `task_id`s repeat across restarts; the sheet keyed on
    them, and the first errand after a restart landed on the PREVIOUS session's sheet and wiped it (`32c7dc6`).
  · `context_retried`/`provider_retried` lived on the SessionRecord, and every relay builds a fresh record — so
    "relaunched ONCE" bounded nothing and six workers ran one car search (`0399a1d`).
  · the accumulator's `clear()` was copied into all four act exits, and the watermark had to be stamped in every
    copy (`3b316b4`).

The fixes each landed where they hurt; what none of them closed is the CLASS — nothing stopped the next
module-level `_seq = 0` from being born and read as an identity. This module closes it: anything that must be
unique across a restart, or that several modules count on, lives HERE, and a ratchet test greps the tree so a
counter born elsewhere goes red with a name.

Two primitives, deliberately small:

  · `boot_id()` — a short random stamp for this RUN. Compose it into any id that must not collide with the
    previous run's (`dispatch.sheet_id_for` → `f"{boot_id()}-{task_id}"`). Minted once per process AND rolled
    whenever a counter is rewound (see `reset_seq`): a stamp that survives a rewind does not buy uniqueness,
    it only looks like it does.
  · `next_seq(name)` — a named, thread-safe, monotonic counter. Per PROCESS by design: callers that need
    cross-restart uniqueness compose with `boot_id()` rather than persisting counters — a persisted counter is
    shared mutable state on disk, and the boot stamp buys the same property for free.
"""
from __future__ import annotations

import secrets
import threading

_BOOT = secrets.token_hex(3)
_lock = threading.Lock()
_seqs: dict[str, int] = {}


def boot_id() -> str:
    """This process's stamp. Stable for the whole process lifetime, different every restart."""
    return _BOOT


def next_seq(name: str) -> int:
    """The next value of the named counter, starting at 1. Thread-safe; per-process (see module docstring)."""
    with _lock:
        _seqs[name] = _seqs.get(name, 0) + 1
        return _seqs[name]


def reset_seq(name: str) -> None:
    """Restart one named counter — AND roll the boot stamp with it, because that is what keeps the promise.

    ⚠️ This docstring used to say «for TESTS … production never rewinds a sequence», and that was FALSE the
    day it was written: `escalate.reset()` is called by `nucleo/reset.py::reset_all()`, which is the operator's
    ⏻ «we start from zero» and the harness's reset between cases. So the exact repeated-id class this module
    exists to end was happening in production, through the door its author believed was test-only.

    Measured on the batch of 2026-08-24 03:02: FOUR cases in one lab process, and all four errands got the
    sheet `results--c2567e-1` — the same box, each one striking the previous case's findings with
    `begin_task(fresh=True)`. That is literally the defect the operator asked to remove when he asked for one
    sheet per errand: «con esta regla no cometeremos errores de borrar búsquedas». V2-259's addendum closed
    the PROCESS-restart door with `boot_id()`; this is the same bug through the reset door, and `boot_id` could
    not see it because it only rolls on a new process.

    Rolling the stamp fixes the CLASS and not the instance: any durable id composed with `boot_id()` — present
    or future — stops colliding across a rewind by construction, which is the property the stamp was sold as
    having. The cost is intended: sheets from before the reset become unreachable by id, and they belong to
    the session the operator just said to forget.
    """
    global _BOOT
    with _lock:
        _seqs.pop(name, None)
        _BOOT = secrets.token_hex(3)
