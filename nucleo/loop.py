"""nucleo/loop.py — Orchestrator loop (~1 Hz), the v2 brain's "thread of time" (V2-005 · T70).

An async loop at ~1 Hz that runs in the server process (the SAME loop as voice, alongside the widget
supervisor). It is zaelar's own heartbeat — it replaces **Hermes' native cron**, which dies with it. On each tick:

  - **scheduled tasks** — fires overdue tasks from its own scheduler (`nucleo/scheduler.py`, backed by
    `memory.journal`) and delivers their prompt through the proactive rails (voice + UI).
  - 🔥 **sparks** — spontaneous thought, with a dual gate (frequency + utility, `nucleo/sparks.py`).
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

from . import scheduler as _scheduler
from . import sparks as _sparks

# V2-227 scope B2: how many seconds between heartbeats for a live task. Few, because the failure it fixes is the
# SILENCE —seven minutes of a motionless screen— and no less, because a PERSON reads the rail: one heartbeat per
# second is not information, it is timestamped noise. Adjustable through the environment so it can be measured.
_BEAT_SECS = float(os.getenv("ZAELAR_TASK_BEAT_SECS", "15") or 15)


def _emit(topic: str, payload: dict | None = None) -> None:
    """Publish a loop signal through the Nervous System (best-effort, loop-agnostic)."""
    try:
        import bus
        bus.emit_sync(topic, payload or {})
    except Exception:
        pass


#: Key for the RETRACTABLE notice «it has been N minutes, should I stop it?» — one per task (V2-353).
_TIMEOUT_KEY = "worker-timeout:"


async def _default_deliver(title: str, text: str, key: str = "") -> None:
    """Deliver through the existing proactive rails (voice + UI). Best-effort.

    `key` (V2-353) travels to the brain's mailbox so a note asserting something about LIVE state can be
    RETRACTED if it stops being true before delivery — see `voice.brain_notes.push`.
    """
    try:
        from voice import proactive
        await proactive.notify(title or "zaelar", text, key=key)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"loop deliver failed: {e}")


class OrchestratorLoop:
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
        # live diagnosis: the operator saw "6 active" in the master for a conversation abandoned a while ago).
        # "The ball is in the people's court" applies only while SOMEONE IS working on it — a live Brain Worker
        # (`dispatch.has_live_trace`) is NEVER touched here, no matter how much time passes; this is only for the
        # turn that already answered and was left waiting for the operator to resume the topic.
        # DECOUPLED check from the 1 Hz tick (a real SQL query, not bookkeeping in RAM) — checked every
        # `_stale_flow_check_every_s`, not on every pulse.
        self._stale_flow_secs = float(os.getenv("ZAELAR_STALE_FLOW_SECS", "900"))       # 15 min by default
        self._stale_flow_check_every_s = float(os.getenv("ZAELAR_STALE_FLOW_CHECK_SECS", "60"))
        self._last_stale_flow_check = 0.0

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
        await self._supervise_stale_flows(now)
        await self._fire_due(now)
        await self._maybe_spark(now)
        await self._maybe_consolidate(now)
        self._close_idle_session()
        _emit("loop.tick", {"ts": now, "n": self._ticks})

    def _close_idle_session(self) -> None:
        """Closes the observability session when nothing real has happened in it for a while
        (`observability/identity.py::close_if_idle` owns the decision and the clock; this only offers the
        pulse). Until 2026-08-31 the idle ceiling could only fire when activity came BACK, so a session the
        operator simply walked away from stayed open forever and read "EN CURSO" in the master with nothing
        happening in it. Pure RAM arithmetic, and it never OPENS a session or extends the clock — a pulse must
        be able to end an idle stretch without ever being mistaken for work."""
        try:
            from observability import identity
            identity.close_if_idle()
        except Exception:
            pass

    async def _supervise_workers(self, now: float) -> None:
        """V2-038 (§8): PROJECTS the RAM registry into STATE (~1 Hz, §v2·C), RELAYS a waiting worker's question
        (one at a time, with attribution, §v3·B/M), and warns of STUCK/TIMEOUT (never kills blindly §v3·Q7).
        Best-effort; a failure here never brings down the loop."""
        try:
            from nucleo import dispatch, worker_api
        except Exception:
            return
        # (1) coalesced projection RAM → STATE (source of truth = RAM; not per-event).
        try:
            dispatch.sync_state()
        except Exception:
            pass
        try:
            sessions = dispatch.active_sessions()
        except Exception:
            sessions = []
        live_ids = {s["id"] for s in sessions}
        # clear marks for sessions that no longer exist (to avoid unbounded growth)
        self._stuck_informed &= live_ids
        self._last_beat = {k: v for k, v in self._last_beat.items() if k in live_ids}
        self._timeout_informed &= live_ids
        self._budget_nudged &= live_ids
        # (2) relay the ACTIVE (oldest) ask ONCE, with attribution + open the attention window (§v3·D/N).
        try:
            a = worker_api.active_ask()
        except Exception:
            a = None
        if a and a["corr_id"] not in self._ask_relayed:
            self._ask_relayed.add(a["corr_id"])
            goal = ""
            for s in sessions:
                if s["id"] == a["task_id"]:
                    goal = s.get("goal") or ""
                    break
            try:
                from voice import attention
                attention.note_directed()          # the operator's immediate response is DIRECTED (§v3·D)
            except Exception:
                pass
            await self._deliver("zaelar", self._say(
                "worker_ask_named" if goal else "worker_ask_generic",
                goal=goal[:40], question=a["question"]))
        # purge resolved corr_ids from the relayed set (to avoid growth)
        try:
            pend = {p["corr_id"] for p in worker_api.pending_asks()}
            self._ask_relayed &= pend
        except Exception:
            pass
        # (3) stuck + timeout (warns, offers to stop; does NOT kill alone) + HARD BUDGET (2 phases).
        for s in sessions:
            tid, age = s["id"], int(s.get("age_s") or 0)
            if s.get("waiting_on") == "user":
                continue                            # not stuck: waiting for the operator
            budget = self._budget_for(s.get("kind") or "")
            if budget > 0 and age >= budget + self._budget_grace:
                # PHASE 2: budget + grace expired without closing → KILLED with partial delivery (the card
                # retains what was extracted via _finalize_web). No more workers wandering indefinitely.
                try:
                    dispatch.cancel_session(tid, reason="budget")
                except Exception:
                    continue
                _emit("worker.budget_kill", {"id": tid, "age_s": age})
                try:    # V2-353: the question «should I stop it or let it continue?» has just become meaningless
                    from voice import brain_notes as _bn
                    _bn.retract(_TIMEOUT_KEY + str(tid))
                except Exception:  # noqa: BLE001
                    pass
                goal = (s.get("goal") or self._lang().generic_task)[:60]
                await self._deliver("zaelar", self._say("worker_budget_killed", goal=goal))
                continue
            if budget > 0 and age >= budget and tid not in self._budget_nudged:
                # PHASE 1: urge it to DELIVER NOW (piggyback/stdin) — the worker closes with what it has.
                self._budget_nudged.add(tid)
                _emit("worker.budget_nudge", {"id": tid, "age_s": age})
                try:
                    rec = dispatch.get_record(tid)
                    if rec is not None and rec.session is not None:
                        await rec.session.inject(
                            "SE TE ACABA EL TIEMPO: deja de explorar, extrae lo que tengas y ENTREGA AHORA tu "
                            "conclusión final con lo encontrado hasta este momento.")
                except Exception:
                    pass
                continue
            # V2-227 scope B2 — the HEARTBEAT. Deliberately comes before stuck and timeout warnings: it is not
            # an alarm, it is the ordinary signal that the task remains alive. A phase lasting ninety seconds
            # is normal in a web task; what cannot be normal is for the card to go silent.
            if (now - self._last_beat.get(tid, 0.0)) >= _BEAT_SECS:
                self._last_beat[tid] = now
                try:
                    dispatch.session_alive(tid)
                except Exception:
                    pass
            if age >= self._max_secs and tid not in self._timeout_informed:
                self._timeout_informed.add(tid)
                goal = (s.get("goal") or self._lang().generic_task)[:40]
                # V2-353: RETRACTABLE. This question waits for the operator's next turn, and in that gap
                # the budget may kill the task (measured: question at 15 min, death at 20). Without a
                # key, both notes reached the SAME prompt: one asking whether to stop it and another saying
                # that it had already stopped.
                await self._deliver_keyed("zaelar", self._say("worker_timeout_running", goal=goal,
                                                              minutes=age // 60), _TIMEOUT_KEY + str(tid))
            elif int(s.get("silent_s", age)) >= self._stuck_secs and tid not in self._stuck_informed:
                # STUCK = SILENT, not «it has been a while». Until 2026-08-02 this looked at `age` (task age),
                # with its own note «approximated by age» — so ANY worker older than 3 min was
                # declared «stuck (no events)» even while emitting every 5 s. The Whisper believed it,
                # re-escalated, and TWO and THREE workers appeared doing the same work (seen live: 3 workers and
                # ~3× the cost for one search). `last_event_at` was already maintained on every event; it only needed
                # to be checked. Fall back to `age` if the snapshot is old and lacks the field.
                self._stuck_informed.add(tid)
                _emit("worker.stuck", {"id": tid, "age_s": age, "silent_s": int(s.get("silent_s", age))})

    async def _supervise_confirms(self, now: float) -> None:
        """A pending irreversible-action confirmation the operator never answered must not die in silence
        (2026-08-16, operator request after a diagnosed real incident: two turns asked the same "delete all my
        agenda data" confirmation on the same widget — split by the segmenter — and both sat stuck with no way
        to answer either one, and no signal that anything had gone wrong). `widgets/confirm.py` already closes
        the orphaned/expired confirmation's flow synchronously (so the master stops showing it "EN CURSO"
        forever); this is the other half — telling the operator, over the SAME proactive rails (voice+chat) a
        stuck/timed-out worker already uses just above, so the task doesn't just quietly stay undone."""
        try:
            from widgets import confirm
            expired = confirm.drain_expired_notices()
        except Exception:
            return
        for e in expired:
            q = (e.get("question") or "").strip() or self._lang().generic_task
            await self._deliver("zaelar", self._say("confirm_expired", question=q))

    async def _supervise_stale_flows(self, now: float) -> None:
        """Closes a CONVERSATIONAL flow the operator started and then walked away from (2026-08-16, operator
        request after a diagnosed real incident — the master kept showing several "en curso" flows from a
        session the operator had abandoned minutes earlier). `_maybe_close_flow` (the per-turn path in
        `voice/engine/llm/providers/nucleo.py`) only ever gets ONE chance to close a flow, right when its own
        turn finishes; if that turn correctly deferred (an accumulator chain, a pending confirmation, a live
        worker), nothing EVER revisits the decision once those conditions clear on their own. This is that
        revisit — on a slow, deliberately-throttled timer, never the 1Hz tick itself (a real SQL query, not
        RAM bookkeeping).

        Invariant demanded by the operator, verbatim: "if it is an active search that keeps a Brain Worker
        running, it must NEVER be closed until it finishes — the ball is in the people's court." `dispatch.has_live_trace` is checked FIRST and is the one condition that can NEVER be
        overridden by staleness, no matter how long it runs."""
        if now - self._last_stale_flow_check < self._stale_flow_check_every_s:
            return
        self._last_stale_flow_check = now
        try:
            from observability import identity, flows as _obs_flows
            from nucleo import dispatch as _disp_stale
            from widgets import confirm as _confirm_stale
            from voice import trace as _trace_stale
            from voice.observer import emit as _emit_stale

            sid = identity.session_info().get("session_id")
            if not sid:
                return
            confirm_trace_ids = {v.get("trace_id") for v in _confirm_stale.pending().values()}
            for f in _obs_flows.flows(limit=200, session_id=sid):
                corr_id = str(f.get("corr_id") or "")
                if not corr_id or f.get("ended_events"):
                    continue                                       # no trace, or already explicitly closed
                last_ms = float(f.get("last_ms") or 0)
                age = now - last_ms / 1000.0
                if age < self._stale_flow_secs:
                    continue                                       # still within the grace window
                if _disp_stale.has_live_trace(corr_id):
                    continue                                       # a live worker is NEVER closed due to time
                if corr_id in confirm_trace_ids:
                    continue                                       # waiting for the operator's yes/no
                with _trace_stale.scope(corr_id):
                    _emit_stale("flow", "end", role="system",
                                extra={"ok": True, "reason": "stale_no_input", "idle_s": int(age)})
        except Exception as e:  # noqa: BLE001 — a failure here never brings down the loop
            logger.warning(f"loop: supervise_stale_flows failed (ignored): {e}")

    @staticmethod
    def _lang():
        """The active language catalog (`voice.engine.core.langs`) — falls back to Spanish if the import fails."""
        try:
            from voice.engine.core import langs
            return langs.current_language()
        except Exception:
            class _Fallback:
                worker_ask_named = "Oye, el proceso «{goal}» pregunta: {question}"
                worker_ask_generic = "Oye, uno de los procesos en marcha pregunta: {question}"
                worker_budget_killed = ("He parado «{goal}»: agotó su tiempo. Te dejo en la tarjeta lo que ha "
                                       "encontrado hasta ahora.")
                worker_timeout_running = "El proceso «{goal}» lleva ya {minutes} minutos. ¿Quieres que lo pare o que siga?"
                confirm_expired = ("Dejé de esperar tu confirmación sobre: {question} Dímelo otra vez si quieres "
                                   "que lo haga.")
                generic_task = "la tarea"
            return _Fallback()

    async def _deliver_keyed(self, title: str, text: str, key: str) -> None:
        """Deliver with a retractable KEY (V2-353), allowing a two-argument injected `deliver`.

        The test double is injected as `async def deliver(title, text)`, and only two notices in the loop need
        this key: fall back to the old signature instead of requiring every caller to change.
        """
        try:
            await self._deliver(title, text, key=key)
        except TypeError:
            await self._deliver(title, text)

    def _say(self, template: str, **kw) -> str:
        """SPOKEN phrase initiated proactively (worker questions, timeouts…) in the ACTIVE language — never a
        fixed f-string (V2 fix 2026-07-23: `voice.proactive.notify`/`_deliver` speak exactly what they receive,
        without passing through an LLM turn that could re-localize it)."""
        return getattr(self._lang(), template).format(**kw)

    def _budget_for(self, kind: str) -> float:
        """Wall-clock budget by kind (WORKER_BUDGET_<KIND>_SECS takes precedence; then global; 0 = unlimited)."""
        try:
            v = os.getenv(f"WORKER_BUDGET_{(kind or '').upper()}_SECS")
            if v:
                return float(v)
        except Exception:
            pass
        return self._kind_budget_default.get(kind or "", self._budget_secs)

    async def _fire_due(self, now: float) -> None:
        # V2-092: when the agent is STOPPED (⏻), a cron does not fire. Exit BEFORE `mark_fired`, so the job remains
        # OVERDUE and fires as soon as the operator starts — stopping does not lose the reminder, it postpones it. A cron that
        # spoke over a stopped agent would be exactly the failure ⏻ exists to prevent.
        try:
            from nucleo import runstate
            if runstate.stopped():
                return
        except Exception:
            pass
        try:
            jobs = _scheduler.due(now)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"scheduler.due failed: {e}")
            return
        for job in jobs:
            d = job.get("detail") or {}
            prompt = (d.get("prompt") or job.get("title") or "").strip()
            name = (d.get("name") or job.get("title") or "zaelar").strip()
            try:
                _scheduler.mark_fired(job, now)   # advances/closes BEFORE delivery (idempotent on voice failure)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"scheduler.mark_fired failed: {e}")
            # TRACEABILITY (V2-044): each cron firing starts with its trace — delivery (voice+UI) and anything derived
            # remain chained to the job, like an operator's phrase. BOUNDED: the loop is a long-lived task
            # → the ctxvar must be cleared when the job ends (otherwise subsequent ticks would inherit the trace).
            try:
                from voice import trace as _trace
                _trace.begin(f"{name}: {prompt}"[:200], origin="cron")
            except Exception:
                _trace = None
            try:
                _emit("loop.scheduled_fired", {"id": job.get("id"), "name": name, "prompt": prompt})
                if prompt:
                    await self._deliver(name, prompt)
            finally:
                if _trace is not None:
                    _trace.adopt("")

    async def _maybe_spark(self, now: float) -> None:
        if not self._gate.allow(now):
            return
        text = _sparks.propose(now)
        if not text:
            return                                # utility gate: adds nothing → discard
        self._gate.record(now)
        try:
            from voice import trace as _trace
            _trace.begin(text[:200], origin="proactivo")   # V2-044: the spark chains its delivery (bounded below)
        except Exception:
            _trace = None
        try:
            _emit("loop.spark", {"text": text})
            await self._deliver("zaelar", text)
        finally:
            if _trace is not None:
                _trace.adopt("")

    async def _maybe_consolidate(self, now: float) -> None:
        if (now - self._last_consolidate) < self.consolidate_every_s:
            return
        self._last_consolidate = now
        try:
            from memory import api as memory
            # Brain Worker ledger cleanup is INJECTED (audit 2026-08-23): it is CORE hygiene
            # CORE hygiene that uses the same sleep sweep, not a memory task — until now memory reached it by
            # importing `nucleo.workers`, thereby ceasing to be autonomous because of this. Same pattern and
            # same caller as the `rem.run(...)` hooks a few lines below.
            from nucleo.workers import ledger as _wledger
            rep = await asyncio.to_thread(                       # synchronous sqlite → outside the hot path
                lambda: memory.consolidate(prune_workers_fn=_wledger.prune))
            _emit("loop.consolidated", {k: rep.get(k) for k in ("deduped", "evicted", "promoted")})
            logger.info(f"consolidación (sueño): {rep}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"consolidate failed: {e}")
        # DEEP SLEEP «REM phase» (V2-056, memory/rem.py): after light sleep, when due by cadence (daily,
        # persistent sys_kv marker → survives restarts) runs the deep cycle — repair vectors + SEMANTIC dedup
        # + INSIGHT synthesis (nucleo/memllm LLM hook; memory does not import brains) + hygiene.
        # If hygiene alerts (HEART writing heuristically >50% of the day), emit an observable ALERT.
        try:
            from memory import rem as _rem
            if await asyncio.to_thread(_rem.due):
                from . import memllm as _memllm
                rep = await asyncio.to_thread(_rem.run, _memllm.synthesize_concept_groups,
                                              _memllm.verify_insight_grounded,
                                              _memllm.generate_paraphrases)
                _emit("loop.rem", {k: rep.get(k) for k in
                                   ("repaired", "paraphrased", "sem_deduped", "insights", "ms")})
                hyg = rep.get("hygiene") or {}
                if hyg.get("alert"):
                    try:
                        from voice.observer import emit as _oemit
                        _oemit("alert", "memoria: escritura degradada (sueño REM)", role="system",
                               text=f"el {hyg.get('heuristic_pct')}% de lo escrito en 24h fue por heurística "
                                    f"({hyg.get('heuristic_24h')}/{hyg.get('written_24h')}) — ¿CORAZÓN caído?",
                               extra={"module": "memory", **hyg})
                    except Exception:
                        pass
                logger.info(f"sueño REM: {rep}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"rem failed: {e}")


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
