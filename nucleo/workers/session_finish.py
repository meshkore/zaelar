"""How a worker session ENDS: relay, restart, the harness verdict, the delivery through voice and UI, and the
result pill through `writer.result` (only a delivered verdict). Part of nucleo.workers.session (names through _s)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nucleo.workers.session import SessionRecord

from loguru import logger

from nucleo.circuit import breadth as _breadth   # module level: imported lazily inside a worker's ending it hung
from nucleo.workers import session as _s


def parked(rec) -> bool:
    """Did this session end because it ASKED (V2-851 §3)? Its task waits on its row for his answer and resumes this
    session by id — so nothing of an ending runs: no relay, no harness verdict, no delivery."""
    return bool(getattr(rec, "parked", False)) and getattr(rec, "status", "") != "cancelled"


def died(rec) -> bool:
    """Did the process end WITHOUT finishing — no result, nothing of ours stopped it (cancel, stall, spin, relay, the
    permission gate) — while it had a resumable session (V2-851 §3)? Then it is resumed, not failed."""
    return (not getattr(rec, "result_seen", False) and getattr(rec, "status", "") == "running"
            and bool(getattr(rec, "native_sid", "")) and not getattr(rec, "error_class", "")
            and not getattr(rec, "provider_down", None) and not getattr(rec, "context_full", None)
            and not getattr(rec, "handoff", "") and not getattr(rec, "perm_denied", ""))


def _left_its_place(rec) -> bool:
    """A died worker's row waits for the pulse to resume it by id, its phase and what it produced kept. False when
    it already died once (`attempts`): the ending fails it, saying why."""
    from nucleo.circuit import ledger
    try:
        if ledger.worker_died(rec):
            rec.waiting_on, rec.parked = ledger.WORKER, True
            ledger.kept_result(rec)                   # what it produced so far stays on its task
            return True
    except Exception as e:  # noqa: BLE001 — a row that could not wait ends as before
        logger.warning(f"worker[{rec.task_id}]: died, its row could not wait — {e!r}")
    rec.ok, rec.error_class = False, "died"
    rec.result_summary = rec.result_summary or _s._say().worker_died_twice
    return False


async def _finish(self) -> None:
    rec = self._rec
    if parked(rec):
        rec.phase = "waiting"
        self._bus("worker.parked", {"id": rec.task_id, "ask_id": str(getattr(rec, "ask_corr", "") or "")})
    elif died(rec) and _left_its_place(rec):
        self._bus("worker.died", {"id": rec.task_id, "uid": str(getattr(rec, "uid", "") or "")})
    else:
        await _ending(self, rec)
    await _closing(self, rec)


async def _ending(self, rec) -> None:
    # A SESSION THAT RAN OUT OF FUEL PASSES THE BATON — context blown, provider without quota,
    # or the chain capped. `workers/relay.py` owns the three rules and the incidents behind them.
    _s._relay_out_of_fuel(rec, self._RELAY_CAP)
    # V2-776 D2 — …and one that went SILENT gets one fresh start (the count lives in the durable row).
    _s._restart_stalled(rec)

    # V2-241 — A SILENT ENDING AFTER HITTING THE GATE (three measured cases): no delivery, no handoff, but our gate
    # was hit → THAT is what the operator hears; the route is closed here, not a task failure.
    if (not rec.ok and not rec.handoff and rec.perm_denied and rec.status != "cancelled"
            and not rec.result_summary.strip()):
        rec.result_summary = _s._say().worker_command_denied.format(cmd=rec.perm_denied)

    # V2-840 H2 — did it LOOK enough against its brief's own target? One model question, read by the harness below.
    await _breadth.judge(rec)
    # V2-707 F2 — THE HARNESS: a task does not end because the worker SAYS it ended.
    # `workers/goal.py` carries the rule, the incident and the relay.
    _s._harness(rec, self._RELAY_CAP)

    if rec.status not in ("cancelled",):
        rec.status = "done" if rec.ok else ("relevada" if rec.handoff else "error")
    if rec.ok:
        rec.phase = "terminado"
    else:
        rec.phase = "relevada" if rec.handoff else "sin completar"
    # DELIVERY through voice+UI + [SYSTEM] + memory, except on cancellation (the operator already knows they stopped it).
    if rec.status != "cancelled" and rec.result_summary.strip():
        await _s._deliver(rec)
    self._bus("worker.done", {"id": rec.task_id, "ok": rec.ok, "status": rec.status})


async def _closing(self, rec) -> None:
    # TOKENS ARE ALWAYS CHARGED, even when CANCELLED (2026-08-13): inside the UI-only `cancelled` `if`, a worker
    # killed by budget was metered at ZERO (704 s, 256 steps, ~$0.20 → 0 Energy). Two concerns, separated.
    u = self._usage or self._usage_partial or {}
    pt, ct = u.get("input_tokens"), u.get("output_tokens")
    # CACHED input is a SEPARATE billable line, not `input_tokens`. Measured against Grok's CLI cost, ignoring it
    # left 29% of the bill out (211k cached vs 74k input). The meter prices it at its own rate.
    cached = u.get("cache_read_input_tokens")
    if pt or ct or cached:
        from nucleo.energy import meter as _energy
        # THE MODEL THAT ACTUALLY RAN (incident 2026-08-18): `claude-opus-4-8[1m]` was `glm-4.7`, billed at Opus
        # prices since tariffs look up BY NAME. The alias prices only when the provider never said.
        _energy.report_worker_usage(
            base_url=self._base_url, model=(rec.real_model or self._model),
            prompt_tokens=pt, completion_tokens=ct, cached_tokens=cached,
        )
    # a CANCELLED session has already emitted its end chip (ok=False) from dispatch.cancel_session — re-emitting
    # here produced TWO contradictory ends (ok=False and ok=True one second later, seen in the 2026-07-14 demo).
    if rec.status != "cancelled":
        # V2-048: the final row carries TOKENS (size chip) + COST + the model — what the task cost.
        extra = {}
        if pt is not None:
            extra["prompt_tokens"] = pt
        if ct is not None:
            extra["completion_tokens"] = ct
        if self._model or rec.real_model:
            # The panel showed the alias, so it LIED about which model ran. The real one wins; the alias is
            # kept beside it, because "what we asked for" is what a routing/config bug is diagnosed from.
            extra["model"] = rec.real_model or self._model
            if rec.real_model and self._model and rec.real_model != self._model:
                extra["model_requested"] = self._model
        if rec.ctx_tokens:
            extra["ctx_tokens"] = rec.ctx_tokens
        lbl = ""
        try:
            if self._cost:
                lbl = f"${float(self._cost):.4f}"
        except (TypeError, ValueError):
            pass
        # AN ENDING SAYS WHY (V2-237, 2026-08-21): a DEAD worker left `text:""` (harness, `best-plumber-same-day`:
        # the four dead workers said nothing). The RAW text is intentional: this row is the record; what is read
        # aloud goes through `operator_safe_summary`.
        extra["status"] = "waiting" if parked(rec) else str(rec.status or "")
        if parked(rec):
            lbl = f"{lbl} · " + ("died, resumed by id" if rec.waiting_on == "worker" else "waiting for his answer")
            lbl = lbl.strip(" ·")
        elif rec.handoff:
            # V2-238 — a PASSED BATON says so by name; otherwise a handoff's (deliberately empty) ending reads
            # like a dead worker's.
            extra["handoff"] = rec.handoff
            lbl = f"{lbl} · relevada: {rec.handoff}".strip(" ·")
        elif not rec.ok:
            why = " ".join(str(rec.result_summary or "").split())[:200]
            lbl = f"{lbl} · {why}".strip(" ·") if why else (lbl or str(rec.status or "sin completar"))
        self._emit_chip("end", label=lbl, ok=rec.ok or parked(rec), extra=extra)
    # LEAK FIX (marathon 2026-07-22/23): `run()` exits on the first `result`, but `claude --print` stays alive and
    # `_SESSIONS.pop(key)` dropped the only reference (14 zombies after ~2 h). Not closed by `stop()` → close here.
    if not self._stopped:
        try:
            await self._b.stop()
        except Exception:
            pass


async def _deliver(rec: "SessionRecord") -> None:
    """Delivers the result: ONE line of the out-of-turn mouth on the task's row (voice when he is there, his phone
    when not, once) + memory (sole writer). V2-851 F2: the brain note beside it said the same news twice."""
    summary = _s.operator_safe_summary(rec.result_summary)
    if not summary:
        return
    # MEMORY: only SUCCESS is remembered (2026-07-14 audit: FAILED tasks wrote noise pills like «I could not complete
    # the task»). Provenance in `meta.source`. A RESULT pill goes through the one door: the circuit's `met` verdict.
    if rec.ok:
        try:
            from nucleo.memory_agent import writer as _mw
            await _mw.result(f"[tarea {rec.kind}] {rec.goal} → {summary[:600]}", task_id=rec.task_id,
                             verdict=str(getattr(rec, "verdict", "") or ""))
        except Exception:
            pass
    try:
        from nucleo.pulse import notices as _notices     # V2-796: voice when he is there, his phone when not, once
        from nucleo.workers import named_top as _top, spoken_delivery as _sd
        _line = await _sd.line(rec.goal, summary, ok=rec.ok, verdict=str(getattr(rec, "verdict", "") or "")) or summary
        # V2-782: «the top 3» he asked for (or the three a comparison needs) are named, not one of them
        await _notices.notify("zaelar", _top.complete(_line, rec), kind="done", key=f"notice:{rec.task_id}",
                              task_id=str(rec.task_id))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"worker[{rec.task_id}]: entrega proactiva falló: {e}")
