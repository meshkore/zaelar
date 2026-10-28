"""Boot phase 2 — the «Colmena» brain's own processes: the orchestrator loop and its pulse, the Brain Worker
dispatcher and what a restart left behind, Susurro, the action-map and context-pack watchers (from the lifespan of
`server/__init__.py`, V2-778 F1 → refactor2710-13 T-03; same code, same order). Everything here is ONLY with
BRAIN=nucleo and each piece has its own flag."""
from __future__ import annotations

import asyncio
import os

from loguru import logger

from bus.sse import publish as _sse_publish   # ONLY gate into the observer topic: stamps install+session


def orchestrator_loop(active_brain) -> bool:
    # v2 «Colmena» — orchestrator loop (nucleo/pulse/loop.py, V2-005): the v2 brain's OWN heartbeat (scheduled tasks +
    # 🔥 sparks + memory consolidation) — completely replaces Hermes' old native cron. ONLY with BRAIN=nucleo. Same
    # loop as voice; never blocks the hot path (heavy work goes to a thread). Disabled by flag for clones that do
    # not want it.
    loop_on = active_brain() == "nucleo" and os.getenv("ZAELAR_LOOP", "1") == "1"
    if loop_on:
        try:
            from nucleo.pulse import loop as nucleo_loop
            nucleo_loop.start()
            logger.info("Loop orquestador v2 montado (nucleo/pulse/loop.py)")
        except Exception as e:
            logger.warning(f"orchestrator loop start failed (voice/chat unaffected): {e}")
    return loop_on


def pulse_sse_bridge(first_lifespan_entry: bool, loop_on: bool) -> tuple:
    """(subscription, task) of the heartbeat→SSE bridge, or (None, None)."""
    # Orb ECG (V2-039) — HEARTBEAT→SSE bridge. Forwards the bus `loop.tick` event (the orchestrator loop's own
    # ~1 Hz heartbeat, nucleo/pulse/loop.py:127) to the `observer` topic — the one consumed by GET /events — as
    # {kind:"pulse"}. At REST the frontend ECG beats at this REAL server rhythm (only checking crons + running
    # processes that have generated events); FlashBrain turns and live tasks already speed it up client-side.
    # Same fine-grained, decoupled pattern as the memory bridge: it goes DIRECTLY to the observer topic
    # (bus.emit_sync) → NOT through the /debug ring (zero observability noise). nucleo/ does not know the
    # frontend; the bus handles cross-loop delivery (job-thread↔uvicorn).
    if not (loop_on and first_lifespan_entry):
        return None, None
    try:
        import bus
        sub = bus.subscribe("loop.tick")

        async def _pulse_sse_forward(sub=sub):
            async for ev in sub:
                try:
                    ev = ev or {}
                    # cat:"pulse" (V2-043) → the viewer groups it under its own chip (OFF by default): the
                    # ~1 Hz heartbeat keeps feeding the orb ECG (sse.js), but does NOT pollute the live log
                    # unless the operator enables the «Pulse» chip. That leaves REAL memory in/out calls
                    # visible.
                    _sse_publish({"kind": "pulse", "label": "tick", "cat": "pulse",
                                  "n": ev.get("n"), "ts": ev.get("ts")})
                except Exception:
                    pass

        task = asyncio.create_task(_pulse_sse_forward())
        logger.info("Puente latido→SSE montado (loop.tick → /events; ECG del orbe en vivo)")
        return sub, task
    except Exception as e:
        logger.warning(f"pulse→SSE bridge failed (voice/chat unaffected): {e}")
        return None, None


def dispatcher(active_brain, first_lifespan_entry: bool) -> bool:
    # v2 «Colmena» — SlowBrain dispatcher (nucleo/dispatch.py, V2-007): consumes FlashBrain escalations (bus
    # `escalate.requested`), dispatches them to async work agents (web/code/generic), and delivers the result by
    # voice+UI+[SYSTEM]. ONLY with BRAIN=nucleo (the listener only reacts to a topic emitted by the nucleo provider;
    # duo/hermes never touch it). Disabled by flag for clones that do not want it.
    slow_on = active_brain() == "nucleo" and os.getenv("ZAELAR_SLOWBRAIN", "1") == "1"
    if not slow_on:
        return slow_on
    try:
        from nucleo import dispatch as nucleo_dispatch
        nucleo_dispatch.start()
        logger.info("SlowBrain dispatcher v2 montado (nucleo/dispatch.py)")
    except Exception as e:
        logger.warning(f"slowbrain dispatcher start failed (voice/chat unaffected): {e}")
    # REHYDRATION (2026-08-12) — collects work a restart left halfway: resumable work CONTINUES, the rest is
    # RECORDED as interrupted instead of silently disappearing (a `make restart` killed an operator search
    # without leaving a trace: no event, no ledger, no warning). It goes HERE and not earlier because the
    # escalation listener is already subscribed; re-escalation is deferred anyway. **Silent no-op when nothing
    # was in flight**, which is the normal case for any clean boot. Separate module (`nucleo/rehydrate.py`), one
    # call, no state of its own: circumstance → function → steps aside.
    if first_lifespan_entry:
        try:
            from nucleo import rehydrate as nucleo_rehydrate
            _reh = nucleo_rehydrate.at_boot()
            if _reh.get("found"):
                logger.info("Rehidratación: {} en vuelo al morir → {} reanudada(s), {} registrada(s)"
                            .format(_reh["found"], len(_reh.get("resume") or []), len(_reh.get("buried") or [])))
        except Exception as e:
            logger.warning(f"rehydrate at_boot failed (voice/chat unaffected): {e}")
        # V2-771 — a LIST a restart interrupted resumes from its first unfinished step (`nucleo/batch`).
        try:
            from nucleo import batch as nucleo_batch
            _lists = nucleo_batch.resume()
            if _lists:
                logger.info(f"Listas reanudadas tras el reinicio: {len(_lists)}")
        except Exception as e:
            logger.warning(f"task-list resume failed (voice/chat unaffected): {e}")
    return slow_on


def susurro(active_brain) -> bool:
    susurro_on = active_brain() == "nucleo" and os.getenv("ZAELAR_SUSURRO", "1") == "1"
    if susurro_on:
        try:
            from nucleo import susurro as nucleo_susurro
            nucleo_susurro.start()
        except Exception as e:
            logger.warning(f"susurro start failed (voice/chat unaffected): {e}")
    return susurro_on


def watchers() -> None:
    # Action map (V2-539): the WATCH half — measures what the map is missing (turns the model resolved with a
    # single canvas action). Same plug as Susurro: bus only (`turn.completed`), so it covers voice and probe
    # from one place, and its failure never touches the turn.
    try:
        from nucleo.actionmap import watch as _amap_watch
        _amap_watch.start()
    except Exception as e:
        logger.warning(f"actionmap watch start failed (voice/chat unaffected): {e}")
    # CONTEXT PACKS (V2-675): the introduction phase watches the same topic, for the opposite reason — to
    # notice when it is OVER and archive itself. It subscribes to nothing once the phase has closed, so on
    # an installation that is past its first conversation this line costs one settings read at boot.
    try:
        from nucleo.context_packs import introduction as _intro_pack
        _intro_pack.start()
    except Exception as e:
        logger.warning(f"context packs start failed (conversation unaffected): {e}")


async def start(app, first_lifespan_entry: bool) -> dict:
    """Runs the phase; returns the handles the shutdown needs."""
    from config.v2 import active_brain
    loop_on = orchestrator_loop(active_brain)
    pulse_sub, pulse_task = pulse_sse_bridge(first_lifespan_entry, loop_on)
    slow_on = dispatcher(active_brain, first_lifespan_entry)
    susurro_on = susurro(active_brain)
    watchers()
    return {"loop_on": loop_on, "pulse_sse_sub": pulse_sub, "pulse_sse_task": pulse_task,
            "slow_on": slow_on, "susurro_on": susurro_on}
