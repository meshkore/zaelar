"""nucleo/workers/session.py — `WorkerSession`: a live Brain Worker session (V2-038).

Wraps a `WorkerBackend` and drives its lifecycle: starts the engine, PUMPS its normalized events
(`WorkerEvent`) → updates the IN-MEMORY RECORD (source of truth, §v2·C) + publishes on the bus (`worker.*`) + emits
the activity chip + DELIVERS the result through voice+UI. Manages the **injection queue** (↓, §v3·H: pending→
delivered, no double delivery) and **courteous shutdown** (group kill, §v2·D).

The session does NOT speak to the user directly or resolve `ask`/`act` (that is the worker_api request/response
plane + supervisor loop): here we only pump the backend stream (spawned/phase/result/error/done) and keep the record
consistent. Design: initiatives/V2-038-brain-workers-interactivos.md.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field

from loguru import logger

from . import progress as _progress
from .session_notes import _PLACE, SessionNotes  # noqa: F401 — V2-778 F1: the session's notes; _PLACE re-exported
from . import stall as _stall
from .base import WorkerBackend, WorkerSpec
from nucleo import errand_kind as _errand_kind
from .goal import check_and_relay as _harness
from .relay import _say
from .relay import relay_out_of_fuel as _relay_out_of_fuel
from .relay import restart_stalled as _restart_stalled


# CONTEXT BUDGET (incident 2026-08-18). Not the model's real ceiling — deliberately well below it, because the
# provider rejects a call once input PLUS the requested output reservation exceeds its window, and we do not know
# what reservation the CLI asks for. The worker that died reached 138,492 with a ~200k-window model, so the ceiling
# in practice sits somewhere around 140k: warning at 110k leaves room to deliver rather than to be cut off.
# `0` disables the watchdog (the crash path in `_finish` still catches it).
_CTX_BUDGET = int(os.getenv("ZAELAR_WORKER_CTX_BUDGET", "110000"))


from nucleo.workers.stall import denied_fragment  # noqa: F401 — moved to stall.py (V2-645), re-export


#: How many AUTOMATIC relaunches an errand gets before we stop and SAY so. Two, because there are two independent
#: causes (blown context, provider out of quota) and each was written to fire once; what was missing was a bound on
#: the CHAIN. A cap is not a cure — a relay that keeps failing identically is a symptom, not a hiccup — but an
#: unbounded retry on a NON-retryable error spends the operator's money in silence, which is how six workers ran
#: one car search on 2026-08-17.
_RELAY_CAP_DEFAULT = 2


from nucleo.workers import session_events as _sev, session_finish as _sfin  # noqa: E402


class WorkerSession(SessionNotes):
    def __init__(self, backend: "WorkerBackend", spec: "WorkerSpec", record: "SessionRecord"):
        self._b = backend
        self._spec = spec
        self._rec = record
        self._stopped = False
        self._model = spec.model or ""     # V2-048: worker model (observability chip) — refined by `spawned`
        self._usage: dict = {}             # `result` tokens (input/output) → size chip in the final row
        self._usage_partial: dict = {}     # tokens ACCUMULATED message by message: all we have if we kill it
        self._cost = None                  # USD cost of `result` → final-row text (informational, NOT used for
                                            # used for Energy — see energy_meter.report_worker_usage docstring)
        self._base_url = ""                # actual endpoint of the tier serving the session (energy_meter, 2026-08-05)
        self._started_at = time.time()     # to measure the worker's FIRST output (its TTFT) — see _emit_note
        self._first_output_at = 0.0
        # V2-241 — permission correction ran ONCE per session (V2-211), and the measured worker hit the gate THREE times.
        # From the second hit onward nobody told it anything and it died silently, exactly what the network
        # intended to prevent. Now every hit is corrected up to a cap, and the LAST one changes its message.
        self._perm_hits = 0
        self._spin: dict = {}              # identical consecutive steps (stall.spin_count)
        self._spin_dead = False
        self._ctx_warned = False           # the wrap-up turn is injected ONCE (incident 2026-08-18): repeating it
                                            # every message past the budget would spend the little room that is left

    @property
    def alive(self) -> bool:
        return self._b.alive and not self._stopped

    # ── complete session lifecycle ──────────────────────────────────────────────────────────────────────────
    async def run(self, prompt: str) -> None:
        rec = self._rec
        rec.status = "running"
        rec.backend = self._b.name
        rec.phase = _progress.say("starting", "starting")
        try:    # V2-776 D1 — the durable row says it too, or the store reads «pending» for the whole run
            from nucleo import tasks as _tasks
            _tasks.started(rec)
        except Exception:  # noqa: BLE001
            pass
        self._touch()
        self._emit_chip("start", rec.label or _default_label(rec.kind))
        self._bus("worker.spawned", {"id": rec.task_id, "kind": rec.kind, "goal": rec.goal[:120]})
        try:
            await self._b.start(prompt, spec=self._spec)
            it = self._b.events().__aiter__()
            while True:
                # V2-645 — a hung provider stream must not hold this loop forever (nucleo/workers/stall.py).
                kind, ev = await _stall.bounded_next(it)
                if kind == "end":
                    break
                if kind == "stalled":
                    if not self._b.alive:
                        break                     # the process already died; _finish() reads the record
                    _stall.mark_stalled(rec, self._emit_chip)
                    try:
                        await self._b.stop(grace=2.0)
                    except Exception:  # noqa: BLE001
                        pass
                    break
                self._touch()
                self._on_event(ev)
                if self._spin_dead:
                    _stall.mark_spinning(rec, self._emit_chip, self._spin.get("n", 0))
                    try:
                        await self._b.stop(grace=2.0)
                    except Exception:  # noqa: BLE001
                        pass
                    break
                if ev.type == "done":
                    break
        except asyncio.CancelledError:
            logger.info(f"worker[{rec.task_id}]: run CANCELADO")
            rec.status = "cancelled"
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"worker[{rec.task_id}]: run failed: {e}")
            rec.status = "error"
            rec.ok = False
            rec.result_summary = rec.result_summary or "No pude completar la tarea."
        finally:
            await self._finish()

    _on_event = _sev._on_event

    _RELAY_CAP = _RELAY_CAP_DEFAULT

    _finish = _sfin._finish

    # ── injection (↓) ───────────────────────────────────────────────────────────────────────────────────────
    async def inject(self, text: str) -> None:
        """Queues an instruction for the worker (§v3·H). PRIMARY delivery = piggyback (worker_api serves it on the
        bridge's next contact); SECONDARY = backend stdin (conversational engines)."""
        text = (text or "").strip()
        if not text:
            return
        self._rec.injects.append(Inject(text=text, ts=time.time()))
        try:
            await self._b.send(text)     # secondary path; if the backend queues until the turn ends, nothing happens
        except Exception:
            pass

    def take_pending_injects(self) -> list[str]:
        """Returns pending injections and marks them `delivered` (idempotent, no double delivery). Called by
        worker_api when responding to a bridge (piggyback)."""
        out = []
        for inj in self._rec.injects:
            if inj.state == "pending":
                inj.state = "delivered"
                out.append(inj.text)
        return out

    # ── courteous shutdown ─────────────────────────────────────────────────────────────────────────────────
    async def stop(self, *, grace: float = 3.0, reason: str = "operator") -> None:
        if self._stopped:
            return
        self._stopped = True
        self._rec.status = "cancelled"
        try:
            await self._b.stop(grace=grace)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"worker[{self._rec.task_id}]: backend stop failed: {e}")
        self._bus("worker.cancelled", {"id": self._rec.task_id, "reason": reason})

    # ── V2-065: pause ≠ stop (see workers/base.py) — freezes without setting `status="cancelled"` ───────────
    def pause(self) -> bool:
        if self._stopped or not self._b.pause():
            return False
        self._rec.paused = True
        self._bus("worker.paused", {"id": self._rec.task_id})
        return True

    def resume(self) -> bool:
        if self._stopped or not self._b.resume():
            return False
        self._rec.paused = False
        self._bus("worker.resumed", {"id": self._rec.task_id})
        return True

    # ── helpers ────────────────────────────────────────────────────────────────────────────────────────────
    def _touch(self) -> None:
        self._rec.last_event_at = time.time()

    def _bus(self, topic: str, payload: dict) -> None:
        try:
            import bus
            bus.emit_sync(topic, payload)
        except Exception:
            pass


    _maybe_warn_context = _sev._maybe_warn_context

    # V2-211 — THE GATE IS OURS, and the worker dies there without saying so. Three cases measured on the same day,
    # three different commands, the same pattern: `cd … was blocked`, `requires approval: curl -s …`, `requires
    # approval: cd /Users/…`. In headless mode nobody approves, so the approval request is a dead end; the worker
    # reads it as a no and stops, while the turn continues to count as progress.
    #
    # `dispatch_prompts` attacks it upstream (the drawer rules, like the interpreter on 2026-08-02); this is the
    # NET: if it still hits the gate, it is told IMMEDIATELY what happened and how to rewrite it. The same form as
    # the early delivery above —one injected turn, ONCE— because the session is still alive and its own reasoning
    # is the shortest route back.
    _DENIED_NEEDLES = ("requires approval", "was blocked", "permission to use", "requested permissions",
                       "may only change directories")

    _maybe_hand_web = _sev._maybe_hand_web

    _PERM_MAX = 3          # the number the harness measured in one worker before it died silently

    _maybe_unstick_permission = _sev._maybe_unstick_permission


    _relay_search = _sev._relay_search


def _default_label(kind: str) -> str:
    return _errand_kind.default_label(kind)


# V2-276 — the two text builders (`operator_safe_summary`, `context_handoff`) have lived in
# `handoff.py` since 2026-08-24 (architectural ratchet). Pure, operating only on the record; this
# file governs a session's LIFECYCLE, it does not compose text. They are re-exported because tests and
# `providers.py` refer to them from here.
from nucleo.workers.handoff import (  # noqa: F401,E402 — re-export
    context_handoff, operator_safe_summary,
)

from nucleo.workers.session_record import (  # noqa: E402,F401
    Inject, SessionRecord)
from nucleo.workers.session_finish import (  # noqa: E402,F401
    _deliver)
