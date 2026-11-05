"""The pulse's worker supervision: project the registry, relay a question, beat, ask for a report.

No clock ends a task (V2-852 R2): it runs until its `done_when` is met, he stops it, or it fails hard with its reason
(the stall watchdog's dead provider, a died worker). Age is never a cause, and nothing here asks «stop or keep going?»."""
from __future__ import annotations

from nucleo.request import title as _errand_title
from nucleo.workers import relay as _relay
from nucleo.pulse.signals import (_BEAT_SECS, _REPORT_SECS, _REPORTING_BACKENDS, _STUCK_KEY, REPORT_DEMAND, _emit,
                                  _observe)


def _row_beat(s: dict, now: float) -> None:
    try:
        from nucleo.circuit import ledger as _tasks
        _tasks.status_written(s, now=now)
    except Exception:  # noqa: BLE001 — the beat never breaks the pulse
        pass


#: How long after this process's first beat the questions a previous process left open go back on screen.
RESHOW_AFTER_BOOT_S = 20.0


class WorkersPulse:
    def _beat_due(self, tid, now: float) -> bool:
        """One beat per `_BEAT_SECS` per session — the clock both the working and the waiting beat share."""
        if now - self._last_beat.get(tid, 0.0) < _BEAT_SECS:
            return False
        self._last_beat[tid] = now
        return True

    async def _close_expired_waits(self, now: float) -> None:
        """V2-851 §11.1 — a task that waited for his answer past the rule's period is closed (`settle` → cancelled) and
        said, ONE line by the out-of-turn mouth, keyed per task so a restart never says it twice. The other wait the
        pulse ends is a died worker's pause (`_resume_died_workers`)."""
        self._resume_died_workers(now)
        try:
            from nucleo.circuit import ledger as _tasks
            from nucleo.pulse import notices
            for row in _tasks.expired_waits(now):
                goal = _errand_title.provisional(row.get("title") or row.get("goal") or self._lang().generic_task, 48)
                await notices.notify("zaelar", self._say("task_wait_expired", goal=goal, days=f"{row['days']:g}"),
                                     key=f"task:{row['id']}:expired", kind="info")
        except Exception as e:  # noqa: BLE001 — the pulse never breaks on a sweep; it says it
            _emit("task.expired_waits_failed", {"error": repr(e)[:160]})

    def _next_relay(self, worker_api, now: float):
        """The oldest open question nobody has SAID yet — an inline door's was said by the turn's own mouth (V2-851)
        and is never relayed again; after a restart every open question goes back on SCREEN once, never by voice."""
        self._reshow_after_boot(worker_api, now)
        try:
            return next((p for p in worker_api.pending_asks() if not p.get("said")), None)
        except Exception as e:  # noqa: BLE001 — nothing to relay this beat; said
            _emit("task.relay_unreadable", {"error": repr(e)[:160]})
            return None

    def _resume_died_workers(self, now: float) -> None:
        """V2-851 §3 — a worker whose process died before finishing waits on its row; once its pause is over it is
        resumed BY ID, re-briefed from the row (the same path as an answer). Its row counts the deaths."""
        try:
            from nucleo.circuit import ledger as _tasks
            from nucleo.cli import worker_api_resume as _res
            for row in _tasks.worker_resumes_due(now):
                tid = _res.resume_soon(row["id"], {}, src="worker_died")
                _observe("♻️ a died worker resumed by id", row["id"], task_id=row["id"], dispatch=tid)
        except Exception as e:  # noqa: BLE001 — the pulse never breaks on a sweep; it says it
            _emit("task.resume_died_failed", {"error": repr(e)[:160]})

    def _reshow_after_boot(self, worker_api, now: float) -> None:
        """The questions still open when this process was born go back on screen ONCE, `RESHOW_AFTER_BOOT_S` after the
        boot: the screen that showed them before belonged to the process that died, and the new one has to have had
        the time to attach. Never by voice — the pulse's relay and the turn's mouth own that."""
        if getattr(self, "_reshown", False):
            return
        born = getattr(self, "_born_at", None)
        if born is None:
            self._born_at = born = now
        if now - born < RESHOW_AFTER_BOOT_S:
            return
        self._reshown = True
        try:
            from nucleo.circuit import asker
            n = asker.reshow([a for a in worker_api.open_asks() if a.get("since", 0) < born])
            if n:
                _observe("❓ open questions back on screen after the boot", f"{n}", n=n)
        except Exception as e:  # noqa: BLE001 — the pulse never breaks on a re-show; it says it
            _emit("task.reshow_failed", {"error": repr(e)[:160]})

    def _supervise_memory(self, now: float) -> None:
        """Every few seconds, the host's measured memory against the declared envelope (`workers/envelope.relieve`)."""
        if now - getattr(self, "_mem_at", 0.0) < 5.0:
            return
        self._mem_at = now
        try:
            import nucleo.dispatch as dispatch
            from nucleo.workers import envelope
            did = envelope.relieve(list(dispatch._SESSIONS.values()))
            if did:
                _observe("🧯 memoria del host: " + did, did, kind_diag="envelope")
        except Exception as e:  # noqa: BLE001 — the pulse never breaks on a probe; it says it
            _emit("envelope.unreadable", {"error": repr(e)[:160]})

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
            await self._close_expired_waits(now)     # …and a died worker's row is resumed by id after its pause
        # clear marks for sessions that no longer exist (to avoid unbounded growth)
        self._stuck_informed &= live_ids
        self._last_beat = {k: v for k, v in self._last_beat.items() if k in live_ids}
        self._report_asked = {k: v for k, v in self._report_asked.items() if k in live_ids}
        # (2) relay the ACTIVE (oldest) ask ONCE, with attribution + open the attention window (§v3·D/N).
        a = self._next_relay(worker_api, now)
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
            await self._deliver_keyed("zaelar", self._say(
                "worker_ask_named" if goal else "worker_ask_generic",
                # Clipped on a word boundary (V2-530): the old `[:40]` cut mid-word, and a name read aloud
                # with its last word amputated is worse than a slightly longer one.
                goal=_errand_title.provisional(goal, 48), question=a["question"]),
                f"ask:{a['corr_id']}", str(a.get("task_id") or ""))
        # purge resolved corr_ids from the relayed set (to avoid growth)
        try:
            pend = {p["corr_id"] for p in worker_api.pending_asks()}
            self._ask_relayed &= pend
        except Exception:
            pass
        # (3) beat + report demand + stuck (silence, said). No age-based question and no budget kill (V2-852 R2).
        for s in sessions:
            tid, age = s["id"], int(s.get("age_s") or 0)
            if s.get("waiting_on") == "user" or s.get("status") == "queued":
                if s.get("waiting_on") == "user" and self._beat_due(tid, now):
                    _row_beat(s, now)               # V2-851: the row says it WAITS (and since when) — not a skipped beat
                continue                            # not stuck: waiting for the operator, or for a free slot (2026-10-22)
            # V2-227 scope B2 — the HEARTBEAT. Deliberately comes before the stuck warning: it is not
            # an alarm, it is the ordinary signal that the task remains alive. A phase lasting ninety seconds
            # is normal in a web task; what cannot be normal is for the card to go silent.
            if self._beat_due(tid, now):
                try:
                    dispatch.session_alive(tid)
                except Exception:
                    pass
                _row_beat(s, now)   # V2-776 D1 — the same beat makes the worker's state durable (pulse, FlashBrain, observability)
            # V2-776 D2 — THE REPORT OBLIGATION. Silent about where it is for `_REPORT_SECS` → told to say so,
            # again every `_REPORT_SECS` while it stays silent. Not an alarm and not a kill: stuck below still
            # judges the worker; this only makes its state readable in the durable row.
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
            if int(s.get("silent_s", age)) >= self._stuck_secs and tid not in self._stuck_informed:
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
                await self._deliver_keyed("zaelar", self._say(    # V2-831: says what the supervisor WILL do
                    goal=goal, minutes=max(1, int(s.get("silent_s", age)) // 60), **_relay.stuck_notice(s)),
                    _STUCK_KEY + str(tid), str(tid))
