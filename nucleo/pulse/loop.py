"""nucleo/pulse/loop.py — Orchestrator loop (~1 Hz), the v2 brain's "thread of time" (V2-005 · T70).

An async loop at ~1 Hz that runs in the server process (the SAME loop as voice, alongside the widget
supervisor). It is zaelar's own heartbeat — it replaces **Hermes' native cron**, which dies with it. On each tick:

  - **scheduled tasks** — fires overdue tasks from its own scheduler (`nucleo/pulse/scheduler.py`, backed by
    `memory.journal`) and delivers their prompt through the proactive rails (voice + UI).
  - 🔥 **sparks** — spontaneous thought, with a dual gate (frequency + utility, `nucleo/pulse/sparks.py`).
  - **consolidation** ("sleep") — triggers `memory.consolidate()` on an interval, OUTSIDE the hot path
    (`asyncio.to_thread`: the consolidator is synchronous sqlite and must not block voice).
  - **expired confirmations** and **abandoned conversational flows** (2026-08-16) — revisits, in its own
    slower-than-the-pulse window, closing decisions that a turn could only make ONCE (see
    `_supervise_confirms`/`_supervise_stale_flows`). It never touches a flow with a live Brain Worker on it.
  - **signals** over the bus: `loop.tick`, `loop.scheduled_fired`, `loop.spark` (observable by tests/voice/e2e/agent/judge).

Loop-agnostic: mounted in the server lifespan as a task (strong ref in app.state), like the rest of the
subsystems. It NEVER blocks the voice path — heavy work goes to a thread or (V2-007) a CodeAgent.
It ALWAYS reports through `voice/proactive.notify()` (voice + subtitle + chat, deduplicated) — never a toast.
"""
from __future__ import annotations

import asyncio
import os
import time

from loguru import logger

from nucleo.pulse import due, flows, scheduler as _scheduler, sparks as _sparks, workers
from nucleo.pulse.signals import _BEAT_SECS, _REPORT_SECS, _STUCK_KEY, REPORT_DEMAND, _default_deliver, _emit  # noqa: F401


class OrchestratorLoop(workers.WorkersPulse, flows.FlowsPulse, due.DuePulse):
    """The ~1 Hz loop. `start()` creates the task; `stop()` cancels it cleanly."""

    def __init__(self, tick_s: float | None = None, consolidate_every_s: float | None = None,
                 spark_gate: "_sparks.SparkGate | None" = None, deliver=None):
        self.tick_s = float(os.getenv("ZAELAR_LOOP_TICK_SECS", "1.0")) if tick_s is None else tick_s
        self.consolidate_every_s = (
            float(os.getenv("ZAELAR_CONSOLIDATE_SECS", "3600")) if consolidate_every_s is None
            else consolidate_every_s)
        self._gate = spark_gate or _sparks.SparkGate()
        self._deliver = deliver or _default_deliver
        self._task: asyncio.Task | None = None
        self._stop = False
        self._last_consolidate = 0.0
        self._ticks = 0
        # V2-038 · Brain Worker supervisor (§v2·D §8): relay questions, detect stuck workers/timeouts.
        self._ask_relayed: set[str] = set()       # corr_id of asks already relayed by voice (once)
        self._stuck_informed: set[str] = set()    # tids already notified of being stuck
        self._timeout_informed: set[str] = set()  # tids already notified of timeout
        self._budget_nudged: set[str] = set()     # tids already urged to DELIVER (budget phase 1)
        self._report_asked: dict[str, float] = {}  # V2-776 D2 — when each tid was last told to report
        # V2-227 scope B2: when each task last beat. The operator asked for «something every few seconds
        # while it is alive»; without the marker, this loop (~1 Hz) would emit one heartbeat per SECOND and drown
        # the rail that the heartbeat exists to make legible.
        self._last_beat: dict[str, float] = {}
        # ONE definition, in the module that owns the record (V2-131) — the prompt reads the same number,
        # so what the supervisor says out loud and what the brain answers when asked cannot disagree.
        from nucleo import dispatch as _disp_thr
        self._stuck_secs = _disp_thr.STUCK_SECS
        self._max_secs = float(os.getenv("WORKER_MAX_SECS", "900"))
        # HARD BUDGET per worker (demo 2026-07-14: the Wallapop search wandered for 12+ min without delivering; the
        # passive _max_secs notice does not stop it). Two phases: when exhausted, INJECT "deliver now" (the worker
        # closes with what it has); if it remains alive after the grace period, it is KILLED and partial delivery is
        # announced (the card keeps what was extracted). Configurable globally and per kind (WORKER_BUDGET_SECS / WORKER_BUDGET_WEB_SECS…).
        self._budget_secs = float(os.getenv("WORKER_BUDGET_SECS", "600"))
        self._budget_grace = float(os.getenv("WORKER_BUDGET_GRACE_S", "90"))
        # More generous per-kind DEFAULT where the task is legitimately long: a COMBINED web investigation
        # (searching a marketplace + researching each candidate on Google + synthesizing the report) does not fit in 10 min
        # (e2e battery 2026-07-17: the moto found real listings but the citation killed it before the top 3). The env
        # WORKER_BUDGET_WEB_SECS still takes precedence; phase 1 (nudge "deliver now") + partial card delivery are retained.
        self._kind_budget_default = {"web": 1200.0, "research": 1200.0}
        # CLOSING CONVERSATIONAL flows that kept waiting for the operator, who never returned (2026-08-16,
        # live diagnosis: the operator saw "6 active" in the observability viewer for a conversation abandoned a while ago).
        # "The ball is in the people's court" applies only while SOMEONE IS working on it — a live Brain Worker
        # (`dispatch.has_live_trace`) is NEVER touched here, no matter how much time passes; this is only for the
        # turn that already answered and was left waiting for the operator to resume the topic.
        # DECOUPLED check from the 1 Hz tick (a real SQL query, not bookkeeping in RAM) — checked every
        # `_stale_flow_check_every_s`, not on every pulse.
        self._stale_flow_secs = float(os.getenv("ZAELAR_STALE_FLOW_SECS", "900"))       # 15 min by default
        self._stale_flow_check_every_s = float(os.getenv("ZAELAR_STALE_FLOW_CHECK_SECS", "60"))
        self._last_stale_flow_check = 0.0
        # V2-776 D1 — how often the pulse settles task rows no live worker carries (a SQL read, not RAM).
        self._reconcile_every_s = float(os.getenv("ZAELAR_TASK_RECONCILE_SECS", "30"))
        self._last_reconcile = 0.0

    # ── lifecycle ────────────────────────────────────────────────────────────────────────────────────────
    def start(self) -> None:
        # A DONE task (crashed, or cancelled without stop()) must not block a revive: `is_running()` already
        # reports it as dead, and the ⏻ ON gesture relies on this to bring the heartbeat back (V2-516).
        if self._task is not None and not self._task.done():
            return
        self._task = None
        self._stop = False
        self._last_consolidate = time.time()   # do not consolidate at startup
        # Embedding integrity (V2-030): warn (off-hot-path) if the model changed without re-indexing the vectors.
        try:
            from memory import reembed
            reembed.check()
        except Exception:
            pass
        # V2-728 — put the standing reminders on the operator's board. Without this the jobs that existed
        # BEFORE the board did are invisible until they next fire, which for a weekly one is a week of a
        # «Periódicas» tab that lies by being empty. It is also the self-heal for a write-time mirror that
        # failed: the board is rebuilt from the scheduler, which is the side that owns the truth.
        try:
            n = _scheduler.reconcile_board()
            if n:
                logger.info(f"Orchestrator loop: {n} scheduled job(s) put on the task board")
        except Exception:
            pass
        self._task = asyncio.create_task(self._run(), name="nucleo:orchestrator-loop")
        logger.info(f"Orchestrator loop started · tick {self.tick_s:.1f}s · consolidates every "
                    f"{self.consolidate_every_s:.0f}s")

    async def stop(self) -> None:
        self._stop = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
            self._task = None

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _run(self) -> None:
        while not self._stop:
            try:
                await self.tick()
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001 — a tick failure NEVER brings down the loop
                logger.warning(f"loop tick error (ignorado): {e}")
            try:
                await asyncio.sleep(self.tick_s)
            except asyncio.CancelledError:
                break

    # ── one pulse ─────────────────────────────────────────────────────────────────────────────────────────
    async def tick(self) -> None:
        """One loop pulse: scheduler overdue items → sparks → consolidate? → `loop.tick` signal."""
        now = time.time()
        self._ticks += 1
        await self._supervise_workers(now)
        await self._supervise_confirms(now)
        await self._supervise_harness(now)
        await self._supervise_errands(now)
        await self._supervise_stale_flows(now)
        await self._fire_due(now)
        await self._report_wake(now)
        await self._maybe_spark(now)
        await self._maybe_consolidate(now)
        self._close_idle_session()
        self._maybe_idle_stop(now)
        _emit("loop.tick", {"ts": now, "n": self._ticks})

    def _close_idle_session(self) -> None:
        """Closes the observability session when nothing real has happened in it for a while
        (`observability/identity.py::close_if_idle` owns the decision and the clock; this only offers the
        pulse). Until 2026-08-31 the idle ceiling could only fire when activity came BACK, so a session the
        operator simply walked away from stayed open forever and read "EN CURSO" in the observability viewer with nothing
        happening in it. Pure RAM arithmetic, and it never OPENS a session or extends the clock — a pulse must
        be able to end an idle stretch without ever being mistaken for work."""
        try:
            from observability import identity
            identity.close_if_idle()
        except Exception:
            pass

    def _maybe_idle_stop(self, now: float) -> None:
        """Offers the pulse to the idle stop (`nucleo/idle_stop.py`): off unless the deployment sets
        `ZAELAR_IDLE_STOP_MIN`, and when on it only ever asks the server to exit cleanly."""
        try:
            from nucleo import idle_stop
            idle_stop.maybe_stop(now)
        except Exception:
            pass

    async def _supervise_errands(self, now: float) -> None:
        """V2-683 — the beat an errand with a third party moves on: it reads the bus (a message that went
        out, a conversation created, somebody answering), wakes at most one errand, and closes what ran out
        of time. It lives on THIS loop rather than in a task of its own for the reason the whole module
        exists: an errand is not a process, and giving it one would be the thing that dies on a restart.
        Best-effort, like every other supervisor here — it must never be able to stop the pulse."""
        try:
            from nucleo.errands import watch
            await watch.tick(now)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"errands tick skipped: {e}")



# ── process singleton (mounted by the server lifespan) ───────────────────────────────────────────────────
_LOOP: OrchestratorLoop | None = None


def get_loop() -> OrchestratorLoop:
    global _LOOP
    if _LOOP is None:
        _LOOP = OrchestratorLoop()
    return _LOOP


def start() -> None:
    get_loop().start()


async def stop() -> None:
    global _LOOP
    if _LOOP is not None:
        await _LOOP.stop()
        _LOOP = None


def is_running() -> bool:
    return _LOOP is not None and _LOOP.is_running()
