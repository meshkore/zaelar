"""Boot phase 1 — identity, the bus, central memory and its SSE bridge, the MeshKore connector (from the lifespan
of `server/__init__.py`, V2-778 F1 → refactor2710-13 T-03; same code, same order)."""
from __future__ import annotations

import asyncio
import os

from loguru import logger

from bus.sse import publish as _sse_publish   # ONLY gate into the observer topic: stamps install+session


def identity(first_lifespan_entry: bool) -> None:
    # LOCAL install identity (observability/identity.py) — explicit INIT, not lazy-on-first-event (operator
    # ask, 2026-08-16): a fresh self-hosted install used to get its UUID4 the first time ANY code happened to
    # call user_id() (an event emit, a session report…) — it worked, but the id stayed invisible until
    # something incidental triggered it. Calling it here, once, guarantees config/identity.json exists and is
    # logged the moment the server comes up, matching an instance that runs with ZAELAR_USER_ID pre-set in its
    # environment. There this just confirms the
    # override (cloud_account.my_user_id()) resolves — user_id() already prefers it over the local file.
    if first_lifespan_entry:
        try:
            from observability import identity as _identity
            logger.info(f"Installation identity — user_id={_identity.user_id()}")
        except Exception as e:
            logger.warning(f"identity init failed (non-fatal): {e}")


def bus_log():
    # v2 «Colmena» — Sistema Nervioso (bus/, V2-001). Mount the durable event log's LIFECYCLE here (attach at
    # boot, detach+close at shutdown). The bus pub/sub itself is in-memory and needs no "start"; voice/observer
    # already fans out through it (bus/sse.py) with NO new subscribers wired here — the voice hot path is
    # unchanged. The durable log (bus/log.py) had been OFF by default since V2-001 for two concrete reasons: it
    # was a SYNCHRONOUS sink (one INSERT per event on the publishing thread, sometimes the voice thread) and it
    # made zaelar.db grow without bounds. **Both are fixed** (2026-08-09): the sink only ENQUEUES and drains from a
    # dedicated thread, and retention has both an age limit and a row cap. So it is ON by default — without it,
    # flow/session observability (observability/) queries a table nobody feeds, which is exactly the bug that
    # exposed this. `ZAELAR_BUS_LOG=0` still disables it. It never breaks voice/chat.
    try:
        if os.getenv("ZAELAR_BUS_LOG", "1") == "1":
            from bus import log as _bus_log
            _bus_log.attach()
            logger.info("Sistema Nervioso (bus/) montado — log durable de eventos ACTIVO (zaelar.db)")
            return _bus_log
        logger.info("Sistema Nervioso (bus/) montado — log durable en standby (ZAELAR_BUS_LOG=0)")
    except Exception as e:
        logger.warning(f"bus mount failed (voice/chat unaffected): {e}")
    return None


async def memory() -> bool:
    # Central memory v2 (memory/, V2-002/003). Starts the SINGLE write-queue consumer on THIS loop (all async writes
    # — write/reinforce/pin/link — are applied here, one writer → zero collisions) and folds the old files/uploads/
    # inbox into the episodic layer with a LAZY, idempotent, NON-destructive migration (the source is not deleted).
    # Best-effort: a failure here does not touch voice. No brain consumes it yet (that is V2-004); this only leaves
    # it ALIVE and populated. Disabled by flag for clones that do not want it yet.
    memory_on = os.getenv("ZAELAR_MEMORY", "1") == "1"
    if memory_on:
        try:
            from memory import api as memapi
            await memapi.start()
            rep = memapi.migrate_inbox()
            if rep.get("migrated"):
                logger.info(f"Memoria v2 montada — {len(rep['migrated'])} archivo(s) migrado(s) de files/uploads/ a episódica")
            else:
                logger.info("Memoria v2 montada — cola de escritura arrancada (bandeja files/ ya migrada o vacía)")
        except Exception as e:
            logger.warning(f"memory start failed (voice/chat unaffected): {e}")
            memory_on = False
    return memory_on


def memory_sse_bridge(first_lifespan_entry: bool, memory_on: bool) -> tuple:
    """(subscription, task) of the memory→SSE bridge, or (None, None)."""
    # V2-014 — memory→SSE bridge for the MEMORY VIEWER (🧠). Forwards the bus `memory.updated` signal (emitted by
    # every mutation in memory/api.py::_emit) to the `observer` topic — the one consumed by `GET /events` — as a
    # {kind:"memory"} event, so the frontend memory map refreshes IN REAL TIME without polling. Fine-grained,
    # decoupled bridge (memory/ does not know the frontend) that does NOT go through the /debug ring (zero
    # observability noise). The subscription lives in the uvicorn loop; the bus handles cross-loop delivery.
    if not (memory_on and first_lifespan_entry):
        return None, None
    try:
        import bus
        sub = bus.subscribe("memory.updated")

        # COALESCE (2026-07-12): memory emits `memory.updated` for EVERY mutation — and a single voice turn
        # triggers several (conversation buffer + HEART pills + reinforce + state). Forwarding them one by one
        # flooded SSE (→ the operator's "events" counter spiked while "nothing" seemed to happen). The viewer
        # only needs to know THAT something changed (it refetches with debounce), so we merge burst signals into
        # ONE signal per short window, preserving the UNION of affected ids (for live tinting). write/state/
        # reinforce collapse; a `query` (blue tint) is allowed through separately so read highlighting is not
        # lost. This cuts SSE traffic by roughly one order of magnitude without losing map reactivity.
        _COALESCE_MS = float(os.getenv("ZAELAR_MEM_SSE_COALESCE_MS", "400")) / 1000.0

        async def _mem_sse_forward(sub=sub):
            # Trailing debounce: the 1st signal in a burst arms a flush at _COALESCE_MS; following signals only
            # ACCUMULATE (union of ids + latest signaled op/layer). When the timer fires, it emits ONE signal.
            state = {"ids": set(), "op": "", "layer": "", "h": None}
            loop = asyncio.get_event_loop()

            def _flush():
                state["h"] = None
                if not state["op"]:
                    return
                out = {"kind": "memory", "op": state["op"], "label": state["op"]}
                if state["ids"]:
                    out["ids"] = list(state["ids"])
                if state["layer"]:
                    out["layer"] = state["layer"]
                _sse_publish(out)
                state["ids"] = set(); state["op"] = ""; state["layer"] = ""

            async for ev in sub:
                try:
                    ev = ev or {}
                    if ev.get("ids") is not None:
                        state["ids"].update(ev["ids"])
                    if ev.get("id") is not None:
                        state["ids"].add(ev["id"])
                    state["op"] = ev.get("op", "") or state["op"]
                    if ev.get("level"):
                        state["layer"] = ev["level"]
                    if state["h"] is None:
                        state["h"] = loop.call_later(_COALESCE_MS, _flush)
                except Exception:
                    pass

        task = asyncio.create_task(_mem_sse_forward())
        logger.info("Puente memoria→SSE montado (memory.updated → /events; visor de memoria en vivo)")
        return sub, task
    except Exception as e:
        logger.warning(f"memory→SSE bridge failed (voice/chat unaffected): {e}")
        return None, None


def meshkore(app) -> None:
    # MeshKore connector: wire the bridge with the FlashBrain engine off the voice pipeline (untrusted profile;
    # keeps the connector brain-agnostic) and start the collaboration heartbeat — both SYNC and instant. Reconnecting the
    # clusters zaelar was subscribed to IS network I/O (a WS handshake per cluster, unbounded latency if a
    # cluster is slow/unreachable) — this used to `await` INLINE, so a slow/dead cluster held the ENTIRE lifespan
    # hostage: the app doesn't reach `yield` (start serving ANY request — including the page load and the voice
    # token endpoint) until this function returns. Voice/FlashBrain must be usable FIRST; WS reconnects are
    # deferred to their OWN background task (V2-065, operator request 2026-07-23 — see
    # `.meshkore/docs/ops/zaelar-observability.md §Boot` for the full detail).
    from connectors import meshkore as _meshkore
    from connectors.meshkore import store
    from connectors.meshkore.brain import make_brain
    try:
        _meshkore.init(make_brain())
        _meshkore.get_bridge().start_heartbeat()
        if os.getenv("MESHKORE_AUTORECONNECT", "1") == "1":

            async def _meshkore_autoreconnect():
                for name, cfg in store.load_clusters().items():
                    try:
                        # `vis` (V2-086): a PUBLIC cluster reconnects without a token — if this is not propagated
                        # here, the open cluster drops on every restart and only private clusters survive.
                        await _meshkore.get_manager().connect(name, cfg["cluster_id"], cfg["token"],
                                                              cfg.get("handle"), vis=cfg.get("vis", ""))
                        _meshkore.get_bridge().note_objective(name)   # standing objective → peer arrival wakes the brain
                    except Exception as e:
                        logger.warning(f"MeshKore autoreconnect '{name}' failed: {e}")
            app.state.meshkore_reconnect_task = asyncio.create_task(_meshkore_autoreconnect())
    except Exception as e:
        logger.warning(f"MeshKore connector init failed (voice/chat unaffected): {e}")


async def start(app, first_lifespan_entry: bool) -> dict:
    """Runs the phase; returns the handles the shutdown needs."""
    identity(first_lifespan_entry)
    log = bus_log()
    memory_on = await memory()
    mem_sub, mem_task = memory_sse_bridge(first_lifespan_entry, memory_on)
    meshkore(app)
    return {"bus_log": log, "memory_on": memory_on, "mem_sse_sub": mem_sub, "mem_sse_task": mem_task}
