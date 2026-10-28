"""The pulse's worker supervision: project the registry, relay a question, beat, ask for a report, budget."""
from __future__ import annotations

from nucleo.request import title as _errand_title
from nucleo.pulse.signals import (_BEAT_SECS, _REPORT_SECS, _REPORTING_BACKENDS, _STUCK_KEY, _TIMEOUT_KEY,
                                  REPORT_DEMAND, _emit, _observe)


class WorkersPulse:
    async def _supervise_workers(self, now: float) -> None:
        """V2-038 (§8): PROJECTS the RAM registry into STATE (~1 Hz, §v2·C), RELAYS a waiting worker's question
        (one at a time, with attribution, §v3·B/M), and warns of STUCK/TIMEOUT (never kills blindly §v3·Q7).
        Best-effort; a failure here never brings down the loop."""
        try:
            import nucleo.dispatch as dispatch, nucleo.cli.worker_api as worker_api
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
        # (1b) V2-776 D1 — the store must not say «alive» about work nobody is doing. Any exit path that
        # skipped closing its row is settled here, whatever that path was.
        if now - self._last_reconcile >= self._reconcile_every_s:
            self._last_reconcile = now
            try:
                from nucleo.circuit import ledger as _tasks
                n = _tasks.reconciled(dispatch.unclosed_uids(), now=now)
                if n:
                    _emit("task.reconciled", {"n": n})
                    _observe("🧹 tareas huérfanas cerradas", f"{n} fila(s) sin worker vivo → failed", n=n)
            except Exception:  # noqa: BLE001
                pass
        # clear marks for sessions that no longer exist (to avoid unbounded growth)
        self._stuck_informed &= live_ids
        self._last_beat = {k: v for k, v in self._last_beat.items() if k in live_ids}
        self._timeout_informed &= live_ids
        self._budget_nudged &= live_ids
        self._report_asked = {k: v for k, v in self._report_asked.items() if k in live_ids}
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
                    # V2-530 — the errand's NAME, not its brief. `goal[:40]` of a raw turn is what made the
                    # voice say «el proceso "Me parece bien. Oye, una cosita, estabas" pregunta: …»: the cut
                    # landed before the errand was even mentioned. `title` falls back to the brief, so this
                    # is never worse than it was.
                    goal = s.get("title") or s.get("goal") or ""
                    break
            # V2-655 — the window is no longer opened HERE. `note_directed()` before the delivery anchored the
            # silence clock at the FIRST word, so a 10-20 s relayed question could consume its own window and
            # leave the answer ambient — the same defect, one size smaller, that the 90-second delivery of
            # session 85eec898 made unmissable. `proactive.notify` now ARMS the window and `note_bot_speech`'s
            # falling edge anchors it at the LAST word, which is what «§v3·D: his immediate response is
            # DIRECTED» meant all along.
            await self._deliver("zaelar", self._say(
                "worker_ask_named" if goal else "worker_ask_generic",
                # Clipped on a word boundary (V2-530): the old `[:40]` cut mid-word, and a name read aloud
                # with its last word amputated is worse than a slightly longer one.
                goal=_errand_title.provisional(goal, 48), question=a["question"]))
        # purge resolved corr_ids from the relayed set (to avoid growth)
        try:
            pend = {p["corr_id"] for p in worker_api.pending_asks()}
            self._ask_relayed &= pend
        except Exception:
            pass
        # (3) stuck + timeout (warns, offers to stop; does NOT kill alone) + HARD BUDGET (2 phases).
        for s in sessions:
            tid, age = s["id"], int(s.get("age_s") or 0)
            if s.get("waiting_on") == "user" or s.get("status") == "queued":
                continue                            # not stuck: waiting for the operator, or for a free slot (2026-10-22)
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
                # V2-776 L3 — beside the clock, the END STATE: what he asked about is whether it got done.
                note = ""
                try:
                    from nucleo import circuit as _circuit
                    _rec = dispatch.get_record(tid)
                    _v, _missing = _circuit.ending_note(_rec) if _rec is not None else ("", "")
                    from nucleo.circuit import verdict as _verdict
                    _line = getattr(_verdict.of(_v), "ending_note_key", "")      # each verdict declares its line
                    if _line:
                        note = " " + self._say(_line, missing=_missing[:160])
                except Exception:  # noqa: BLE001
                    note = ""
                await self._deliver("zaelar", self._say("worker_budget_killed", goal=goal) + note)
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
                try:    # V2-776 D1 — the same beat makes the worker's state durable (pulse, FlashBrain, observability)
                    from nucleo.circuit import ledger as _tasks
                    _tasks.status_written(s, now=now)
                except Exception:  # noqa: BLE001
                    pass
            # V2-776 D2 — THE REPORT OBLIGATION. Silent about where it is for `_REPORT_SECS` → told to say so,
            # again every `_REPORT_SECS` while it stays silent. Not an alarm and not a kill: stuck and budget
            # below still judge the worker; this only makes its state readable in the durable row.
            if (s.get("backend") in _REPORTING_BACKENDS and not s.get("paused")
                    and int(s.get("unreported_s") or 0) >= _REPORT_SECS
                    and now - self._report_asked.get(tid, 0.0) >= _REPORT_SECS):
                self._report_asked[tid] = now
                try:
                    rec = dispatch.get_record(tid)
                    if rec is not None and rec.session is not None:
                        await rec.session.inject(REPORT_DEMAND)
                        _emit("worker.report_demanded", {"id": tid, "unreported_s": s.get("unreported_s")})
                        _observe("📋 informe de estado exigido", s.get("title") or s.get("goal") or "",
                                 id=tid, unreported_s=s.get("unreported_s"))
                except Exception:  # noqa: BLE001
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
                _observe("🥶 worker sin señales", s.get("title") or s.get("goal") or "",
                         id=tid, silent_s=int(s.get("silent_s", age)))
                # V2-776 D2 — and SAID. It used to be only an event: the operator waited on a worker that had
                # gone quiet and nobody told him until the watchdog killed it and the death note arrived.
                goal = _errand_title.provisional(s.get("title") or s.get("goal") or self._lang().generic_task, 48)
                await self._deliver_keyed("zaelar", self._say(
                    "worker_stuck", goal=goal, minutes=max(1, int(s.get("silent_s", age)) // 60)),
                    _STUCK_KEY + str(tid))
