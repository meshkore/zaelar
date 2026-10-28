"""The pulse's due work: scheduled jobs, owed notices, sparks and consolidation."""
from __future__ import annotations

import asyncio

from loguru import logger

from nucleo.pulse import scheduler as _scheduler, sparks as _sparks
from nucleo.pulse.signals import _default_deliver, _emit


class DuePulse:
    async def _fire_due(self, now: float) -> None:
        # V2-092: when the agent is STOPPED (⏻), a cron does not SPEAK. Exit BEFORE `mark_fired`, so the job remains
        # OVERDUE and fires as soon as the operator starts — stopping does not lose the reminder, it postpones it. A cron that
        # spoke over a stopped agent would be exactly the failure ⏻ exists to prevent.
        # V2-796: …but ⏻ silences the VOICE, not his lock screen. With a device subscribed to Web Push, a plain
        # notice still goes out there (`notices.notify` never speaks while stopped); an errand relaunch still waits.
        stopped = False
        try:
            from nucleo import runstate
            stopped = runstate.stopped()
        except Exception:
            pass
        if stopped and not self._can_push():
            return
        try:
            jobs = _scheduler.due(now)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"scheduler.due failed: {e}")
            return
        for job in jobs:
            d = job.get("detail") or {}
            prompt = (d.get("prompt") or job.get("title") or "").strip()
            name = (d.get("name") or job.get("title") or "zaelar").strip()
            from nucleo.workers import quota_wait as _qwait
            if stopped and (_qwait.takes(d) or not prompt):
                continue                          # work, not a notice: it waits for ⏻ like before
            fired_for = (d.get("schedule") or {}).get("next_run")
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
                if _qwait.takes(d):                 # an errand parked for the quota's reset: relaunch it, not a speech
                    await _qwait.fire(d, self._deliver)
                elif prompt:
                    await self._deliver_notice(job, name, prompt, fired_for)
            finally:
                if _trace is not None:
                    _trace.adopt("")
        await self._retry_owed(now)

    async def _report_wake(self, now: float) -> None:
        """V2-796 — tell a deployment that stops idle machines when the next notice is due (`nucleo/wake.py`)."""
        try:
            from nucleo import wake
            await wake.flush(now)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"loop: wake report failed: {e!r}")

    def _can_push(self) -> bool:
        if self._deliver is not _default_deliver:
            return False                          # a test double: the old contract, nothing pushes
        try:
            from nucleo import notices
            return bool(notices.devices())
        except Exception as e:  # noqa: BLE001 — unreadable: behave as before (postpone while stopped)
            logger.debug(f"loop: push devices unreadable: {e!r}")
            return False

    async def _deliver_notice(self, job: dict, name: str, prompt: str, fired_for) -> None:
        """A due job's text, through the ONE notice door (V2-796): voice when he is there, his devices when not,
        owed until something takes it — and never a second time for the same firing. A test that injected its own
        `deliver` keeps the old contract."""
        if self._deliver is not _default_deliver:
            await self._deliver(name, prompt)
            return
        d = job.get("detail") or {}
        covered = ""
        if d.get("origin") == "agenda":
            try:
                from widgets.agenda import reminders as _rem
                covered = _rem.covered_by(job.get("id"))
            except Exception as e:  # noqa: BLE001 — unknown means ours: a notice too many beats a lost one
                logger.debug(f"loop: covered_by failed: {e!r}")
        try:
            from nucleo import notices
            await notices.notify(name.removeprefix("aviso: ") or "zaelar", prompt, kind="reminder",
                                 key=f"job:{job.get('id')}:{fired_for}", covered_by=covered,
                                 detail={"job": job.get("id"), "origin": d.get("origin") or "cron"})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"loop: notice delivery failed, falling back to voice: {e!r}")
            await self._deliver(name, prompt)

    async def _retry_owed(self, now: float) -> None:
        if self._deliver is not _default_deliver:
            return
        try:
            from nucleo import notices
            await notices.retry_owed(now)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"loop: retry_owed failed: {e!r}")

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
            # Finished-task cleanup is INJECTED (audit 2026-08-23): it is CORE hygiene that uses the same
            # sleep sweep, not a memory task — memory used to reach it by importing `nucleo.workers`, and so
            # stopped being autonomous. Same pattern and same caller as the `rem.run(...)` hooks below.
            # V2-728: the target is the `tasks` table, not the retired `sys_kv` worker ledger.
            from nucleo.circuit import ledger as _tasks
            rep = await asyncio.to_thread(                       # synchronous sqlite → outside the hot path
                lambda: memory.consolidate(prune_workers_fn=_tasks.pruned))
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
                from nucleo.memory_agent.processor import llm_tasks as _tasks
                rep = await asyncio.to_thread(_rem.run, _tasks.synthesize_concept_groups,
                                              _tasks.verify_insight_grounded,
                                              _tasks.generate_paraphrases)
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
        # PER-CHAT DIGEST (V2-628 F3, connectors/messaging/digest.py): the idle HEART pass over the
        # communications archive — one living state per settled chat with new messages. LLM hook injected
        # here (same seam and same reason as rem.run above: the domain module does not import brains).
        # Self-gating: due-by-movement per chat, bounded per cycle, kill-switch ZAELAR_CHAT_DIGEST=0.
        try:
            from connectors.messaging import digest as _digest
            if _digest.enabled():
                from nucleo.memory_agent.processor import llm as _llm
                rep = await asyncio.to_thread(
                    _digest.refresh_due,
                    lambda system, user: _llm.chat_sync("rem", system, user, max_tokens=700))
                if rep.get("digested") or rep.get("failed"):
                    _emit("loop.chat_digest", rep)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"chat digest failed: {e}")
