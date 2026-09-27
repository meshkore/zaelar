"""nucleo/workers/relay.py — a session that ran out of FUEL passes the baton (moved out of `_finish`).

Three rules, each written against a measured incident and moved here byte for byte under the architecture
ratchet, beside `goal.py` because they are the same family: **what happens when a worker session ends for a
reason that is not the task's answer.** None of them is a task failure and none may be delivered as one.

  · CONTEXT BLOWN (2026-08-18) — nothing to relay to (the next tier blows up identically) and nothing to
    report (the operator asked for a guitar, not for an API error), so it relaunches ONCE carrying what was
    learned, and puts nobody on cooldown.
  · PROVIDER WITHOUT QUOTA — the task did not fail, it ran out of fuel: relaunch ONCE onto the next tier
    rather than hand the operator the provider's raw error as though it were the result.
  · THE CHAIN CAPPED (V2-185/V2-238) — then the TRUTH is told. A reassuring sentence that lies is worse than
    the raw error, because the operator waits for something nobody is doing.

`relay_gen` travels in the escalation context on purpose: it lives on the RECORD, every relay builds a fresh
one, and without carrying it the cap could not count — measured on the operator's own engine (2026-08-17):
SIX workers for one car search, four of them born seconds apart and dying in ~17 s with the same error.
"""
from __future__ import annotations

from loguru import logger

from .handoff import context_handoff

def _say():
    """The language table (V2-682). These endings are SPOKEN, and they were Spanish literals inline — a
    worker that dies in a language the operator does not speak is a fault he cannot even read. It lives
    here because five of its six uses are the relay endings below; `session.py` imports it from here."""
    from i18n import langs as _lg
    return _lg.current_language()


def relay_out_of_fuel(rec, relay_cap: int) -> None:
    """Hand the baton on, or tell the truth about why nobody can. Mutates `rec`; never raises."""
    # COMPACT AND CONTINUE (incident 2026-08-18). The context blew up, which is neither a task failure nor a
    # provider failure, so neither of the two existing paths fits: there is nothing to relay to (the next tier
    # would blow up identically) and nothing to report (the operator asked for a guitar, not for an API error).
    # It is relaunched ONCE carrying what was learned, so the fresh worker does not start from zero.
    if (rec.context_full and not rec.context_retried and not rec.provider_down
            and rec.status != "cancelled" and rec.relay_gen < relay_cap):
        rec.context_retried = True
        try:
            from nucleo.flash import escalate as _esc
            _esc.escalate_to_slowbrain(context_handoff(rec), context={
                "src": "context_handoff", "kind": rec.kind, "trace": rec.trace_id,
                "sheet": str(getattr(rec, "sheet", "") or ""),   # the sheet belongs to the ERRAND, not the session
                # V2-698 — and so does the SURFACE. Without it the relaunch was born with the default one
                # and opened a results sheet over a «voz» errand (measured 2026-09-15, provider relay ×2).
                "surface": str(getattr(rec, "surface", "") or ""),
                # V2-728 — and so does the TASK. A relay continues the SAME commission; without this
                # the operator sees one errand that changed provider twice as three things he asked for.
                "task_uid": str(getattr(rec, "uid", "") or ""),
                "depth": int(rec.depth or 0), "relay_gen": int(rec.relay_gen or 0) + 1})
            rec.result_summary = ""       # sin entrega: la retoma el worker nuevo, sin ruido
            rec.ok = False
            rec.handoff = "contexto agotado → sesión nueva con lo aprendido"
            logger.warning(f"worker[{rec.task_id}]: contexto agotado "
                           f"({rec.context_full.get('tokens')} tok) → retomada con lo aprendido")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"worker[{rec.task_id}]: no pude retomar tras agotar el contexto: {e}")
            rec.ok = False                    # V2-238: ver la nota de abajo — esto NO se entrega como logro
            rec.result_summary = _say().worker_context_lost
    # PROVIDER HANDOFF: the task did not fail; it ran out of fuel. Relaunch ONCE —the exhausted tier is already
    # on cooldown, so the new spawn takes the next one— instead of delivering the operator the provider's raw
    # error as though it were the result of what they requested.
    if (rec.provider_down and not rec.provider_retried and rec.status != "cancelled"
            and rec.relay_gen < relay_cap):
        rec.provider_retried = True
        nxt = rec.provider_down.get("next") or ""
        if nxt:
            try:
                from nucleo.flash import escalate as _esc
                _esc.escalate_to_slowbrain(rec.goal, context={
                    "src": "provider_failover", "kind": rec.kind, "trace": rec.trace_id,
                    "sheet": str(getattr(rec, "sheet", "") or ""),   # the sheet belongs to the ERRAND, not the session
                # V2-698 — and so does the SURFACE. Without it the relaunch was born with the default one
                # and opened a results sheet over a «voz» errand (measured 2026-09-15, provider relay ×2).
                "surface": str(getattr(rec, "surface", "") or ""),
                # V2-728 — and so does the TASK. A relay continues the SAME commission; without this
                # the operator sees one errand that changed provider twice as three things he asked for.
                "task_uid": str(getattr(rec, "uid", "") or ""),
                    "depth": int(rec.depth or 0), "relay_gen": int(rec.relay_gen or 0) + 1})
                rec.result_summary = ""          # sin entrega: la retoma el worker de relevo, sin ruido
                rec.ok = False
                rec.handoff = f"proveedor sin cuota → relevo a «{nxt}»"
                logger.warning(f"worker[{rec.task_id}]: proveedor sin cuota → relanzada con «{nxt}»")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"worker[{rec.task_id}]: relevo de proveedor falló: {e}")
                rec.ok = False
                rec.result_summary = _say().worker_relay_failed
        else:
            # V2-238 — THE THREE PATHS THAT ARE NOT A HANDOFF CLOSE `ok`. The three branches above write a
            # `result_summary` that ANNOUNCES a failure, and none touched `ok`, which starts as True. If the
            # backend had not already closed it, that sentence was delivered as «Task completed: I ran out of quota…»
            # —the exact defect targeted by V2-092/V2-236: an ending that says the opposite of what happened.
            rec.ok = False
            rec.result_summary = _say().worker_no_relay
    # THE CHAIN STOPPED: it must be said, and the TRUTH must be told. Without this, a capped ending retained the
    # provider's raw error in `result_summary`, and `operator_safe_summary` translated it as «I ran out of context…
    # I'LL RESUME it with what I had» —a retry promise that will no longer happen. A reassuring sentence that
    # lies is worse than the raw error: the operator waits for something nobody is doing, the V2-185 defect at
    # another gate.
    if (rec.relay_gen >= relay_cap and not rec.handoff and rec.status != "cancelled"
            and (rec.context_full or rec.provider_down)):
        rec.ok = False
        _veces = int(rec.relay_gen or 0) + 1
        if rec.context_full:
            rec.result_summary = _say().worker_gave_up_context.format(times=_veces)
        else:
            rec.result_summary = _say().worker_gave_up_provider.format(times=_veces)


#: How many times a STALLED commission is restarted. One: a worker that goes silent twice on the same errand is
#: not unlucky, and a third try would only spend another five minutes of the operator's wait on the same wall.
STALL_RESTARTS = 1


def restart_stalled(rec) -> None:
    """A worker the watchdog stopped for SILENCE gets ONE fresh start, carrying what it learned (V2-776 D2).

    The operator (2026-09-27): the pulse «se va a encargar de … vigilarlos y de ver cuando uno se cuelga para
    reiniciarlo». Until this a stall was the end: `mark_stalled` wrote an honest death and the errand was over,
    so a provider stream that hung once cost the operator the whole commission. The count lives in the durable
    row (`tasks.attempts`), not on the record: every restart builds a fresh record, and a per-record flag is the
    unbounded-relay bug `relay_gen` exists for (six workers for one car search, 2026-08-17). Mutates `rec`;
    never raises. A second stall ends the errand with `error_class=stalled`, and the ending says so."""
    if (str(getattr(rec, "error_class", "") or "") != "stalled" or rec.status == "cancelled" or rec.handoff):
        return
    uid = str(getattr(rec, "uid", "") or "")
    try:
        from nucleo import tasks as _tasks
        row = _tasks.get(uid) if uid else None
        if row is None or int(row.get("attempts") or 0) >= STALL_RESTARTS:
            return
        _tasks.store().task_patch(uid, attempts=int(row.get("attempts") or 0) + 1)
        from nucleo.flash import escalate as _esc
        _esc.escalate_to_slowbrain(context_handoff(rec), context={
            "src": "stall_restart", "kind": rec.kind, "trace": rec.trace_id,
            "sheet": str(getattr(rec, "sheet", "") or ""),
            "surface": str(getattr(rec, "surface", "") or ""),
            "task_uid": uid,
            "depth": int(rec.depth or 0), "relay_gen": int(rec.relay_gen or 0) + 1})
        rec.result_summary = ""            # no delivery: the fresh worker picks it up
        rec.ok = False
        rec.handoff = "sin señales → reiniciada una vez con lo aprendido"
        logger.warning(f"worker[{rec.task_id}]: stalled → restarted once (task {uid})")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"worker[{rec.task_id}]: stall restart failed: {e}")
