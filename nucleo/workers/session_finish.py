"""How a worker session ENDS: relay, restart, the harness verdict, the delivery through voice and UI, and the
result pill through `writer.result` (only a delivered verdict). Part of nucleo.workers.session (names through _s)."""
from __future__ import annotations

from loguru import logger

from nucleo.workers import session as _s


async def _finish(self) -> None:
    rec = self._rec
    # A SESSION THAT RAN OUT OF FUEL PASSES THE BATON — context blown, provider without quota,
    # or the chain capped. `workers/relay.py` owns the three rules and the incidents behind them.
    _s._relay_out_of_fuel(rec, self._RELAY_CAP)
    # V2-776 D2 — …and one that went SILENT gets one fresh start (the count lives in the durable row).
    _s._restart_stalled(rec)

    # V2-241 — A SILENT ENDING AFTER HITTING THE GATE. The three measured cases died without saying anything,
    # and the cause appeared only by cross-checking the engine log. If the session ends without delivery or
    # handoff but hit our own gate, THAT is what happened, and it is what the operator must hear: it is not a
    # task failure; the route they chose is closed here.
    if (not rec.ok and not rec.handoff and rec.perm_denied and rec.status != "cancelled"
            and not rec.result_summary.strip()):
        rec.result_summary = _s._say().worker_command_denied.format(cmd=rec.perm_denied)

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
    # TOKENS ARE ALWAYS CHARGED, even if the session was CANCELLED (2026-08-13). This lived inside the
    # `if rec.status != "cancelled"` below, which exists for an INTERFACE reason (do not paint two contradictory
    # `end` rows) and swept away an unrelated METERING concern: a worker killed by budget had consumed REAL tokens
    # and was metered at ZERO (e.g. 704 s, 256 steps, ~$0.20 of provider tokens → 0 Energy).
    # Two distinct concerns in one `if`; they are separated.
    u = self._usage or self._usage_partial or {}
    pt, ct = u.get("input_tokens"), u.get("output_tokens")
    # CACHED input is a SEPARATELY BILLABLE LINE and does not belong in `input_tokens` (Anthropic-shaped usage
    # has the three counters separated). In a long agent session the same prompt prefix is reread each turn,
    # so cache tokens end up being SEVERAL TIMES the fresh-input tokens: measured against the cost reported by
    # Grok's own CLI, ignoring them left 29% of the bill out (211k cached versus 74k input). It is passed to the
    # meter, which tariffs it at its own price.
    cached = u.get("cache_read_input_tokens")
    if pt or ct or cached:
        from nucleo import energy_meter as _energy
        # THE MODEL THAT ACTUALLY RAN, not the alias we asked for (incident 2026-08-18): the run recorded as
        # `claude-opus-4-8[1m]` was performed by `glm-4.7`, and the tariff table looks the model up BY NAME —
        # so the bill was computed at Opus prices for a GLM run. The alias only decides pricing when the
        # provider never said what it served.
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
        # AN ENDING SAYS WHY (V2-237, 2026-08-21). The ending row showed cost and nothing else, so a DEAD worker
        # left `text:""` and the reason had to be found by cross-checking the engine log through `span=worker:N`.
        # Measured by the harness in `best-plumber-same-day`: the only error events in the round were from the
        # worker that did NOT die, and the four that did die said nothing. An ending without a cause
        # reads the same as a normal ending.
        #
        # The RAW text is intentional: this row belongs to the record, not the operator's mouth. Ensuring a provider error
        # being read aloud is handled by `operator_safe_summary` during delivery, and its own docstring says
        # the full text remains in the log —which is exactly this.
        extra["status"] = str(rec.status or "")
        if rec.handoff:
            # V2-238 — if the BATON WAS PASSED, the row says so by name. A handoff delivered here the same
            # empty ending as a dead worker (`result_summary` is deliberately emptied so the operator does not
            # see two deliveries), so both read the same in the record.
            extra["handoff"] = rec.handoff
            lbl = f"{lbl} · relevada: {rec.handoff}".strip(" ·")
        elif not rec.ok:
            why = " ".join(str(rec.result_summary or "").split())[:200]
            lbl = f"{lbl} · {why}".strip(" ·") if why else (lbl or str(rec.status or "sin completar"))
        self._emit_chip("end", label=lbl, ok=rec.ok, extra=extra)
    # LEAK FIX (marathon 2026-07-22/23): `run()` sale del bucle en el PRIMER "done" (= primer `result` de
    # stream-json), but the `claude --print` process remains alive (multi-turn mode, waiting for more stdin).
    # dispatch performs `_SESSIONS.pop(key)` immediately after `run()` → the ONLY reference to the backend is
    # lost without killing the process: it remained orphaned forever (observed: 14 zombie processes after ~2h).
    # If the session was not already closed by `stop()` (explicit cancellation), close the backend here before releasing it.
    if not self._stopped:
        try:
            await self._b.stop()
        except Exception:
            pass


async def _deliver(rec: "SessionRecord") -> None:
    """Delivers the result through the usual rails: proactive (voice+UI) + [SYSTEM] note + memory (sole
    writer). Replica of the former dispatch._deliver, now per session."""
    summary = _s.operator_safe_summary(rec.result_summary)
    if not summary:
        return
    try:
        from voice import brain_notes
        head = "Tarea completada" if rec.ok else "Tarea sin completar"
        brain_notes.push(f"[SISTEMA] Brain worker · {head}: {summary[:400]}", key=f"delivery:{rec.task_id}")
    except Exception:
        pass
    # MEMORY: only SUCCESS is remembered as a durable result (2026-07-14 audit — the P2 refactor lost the one-shot
    # `ok` gate and FAILED tasks wrote mid-sized pills such as «I could not complete the task», creating noise that
    # also competed in recall). Failure already reaches the operator through voice + [SYSTEM] note. Provenance is
    # stamped (`meta.source`) so it can be audited/cleaned by origin.
    # The pill is a RESULT, so it goes through the one door that writes one: only the circuit's `met` verdict.
    if rec.ok:
        try:
            from nucleo.memory_agent import writer as _mw
            await _mw.result(f"[tarea {rec.kind}] {rec.goal} → {summary[:600]}", task_id=rec.task_id,
                             verdict=str(getattr(rec, "verdict", "") or ""))
        except Exception:
            pass
    try:
        from nucleo import notices as _notices     # V2-796: voice when he is there, his phone when not, once
        from nucleo.workers import named_top as _top, spoken_delivery as _sd
        _line = await _sd.line(rec.goal, summary, ok=rec.ok, verdict=str(getattr(rec, "verdict", "") or "")) or summary
        # V2-782: «the top 3» he asked for (or the three a comparison needs) are named, not one of them
        _res = await _notices.notify("zaelar", _top.complete(_line, rec), kind="done", key=f"notice:{rec.task_id}")
        if "voice" in str(_res.get("channel") or ""):
            # SPOKEN: he has heard it, and it sits in the conversation as our own words. The note above would
            # hand it to the next turn as news «to add after answering», and the demo pass (2026-09-28) heard the
            # same three monitors three times — the delivery, then two replies that «by the way» repeated it.
            from voice import brain_notes as _bn
            if _bn.retract(f"delivery:{rec.task_id}"):
                from voice.observer import emit as _emit_d
                _emit_d("task", "🔔 entrega dicha en voz — su aviso al cerebro se retira", role="system",
                        text=summary[:120], extra={"id": rec.task_id})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"worker[{rec.task_id}]: entrega proactiva falló: {e}")
