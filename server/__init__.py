"""zaelar server (package). FastAPI app: the frontend + the voice control plane.

Voice engine: LiveKit Agents (INI-012), run EMBEDDED in this process (AgentServer, job_executor_type=THREAD) so
the voice job shares the bus/observer-SSE queue, the central memory, the orchestrator loop and the brain_notes
mailbox with the «Colmena» brain (nucleo/) and everything else. Gated by ZAELAR_ENGINE (default 'livekit'; set
'off' to skip the worker, e.g. for CI import checks). Session state lives in server/state.py.
"""
import mimetypes
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loguru import logger


class RevalidatingStatics(StaticFiles):
    """StaticFiles that sends `Cache-Control: no-cache` on the frontend assets. Without this the browser caches
    the ES modules (app/*.js) heuristically and a plain reload keeps running the OLD code even after we edit it —
    so a fix looks like it "didn't apply" until an explicit hard-refresh. `no-cache` = revalidate every load: the
    etag makes unchanged files a cheap 304, changed files are re-fetched immediately. No hard-refresh needed."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"
        return resp

from . import common  # noqa: F401  (loads .env + sys.path before the rest)
from .pages import router as pages_router
from .voice_api import router as voice_router
from widgets.server_api import router as widgets_router  # isolated widget layer (does not touch the voice core)
from connectors.meshkore.server_api import router as meshkore_router  # native cluster I/O channel (always on)
from connectors.messaging.server_api import router as messaging_router  # UI-managed connect/disconnect of connectors
from server.memory_routes import router as files_router  # paste/drop uploads → EPISODIC memory (V2-003; absorbs files/)
from memory.vault_api import router as vault_router    # operator encrypted-secrets vault (V2-060)
from bus.sse import publish as _sse_publish   # ONLY gate into the observer topic: stamps install+session
from observability.api import router as obs_router    # flows/sessions/identity (correlation id, 2026-08-09)
from nucleo.cron_api import router as cron_router  # «Colmena» brain's own proactivity (V2-005/009; ⏰ panel)
from .wizard_api import router as wizard_router  # first-run wizard: local/cloud profiles + detector (V2-040)
from .spotify_api import router as spotify_router  # Spotify music connector (OAuth PKCE + state), V2-041
from .config_api import router as config_router  # full-screen configuration area + API balances (V2-043)
from .i18n_api import router as i18n_router  # multilingual UI: state + preset/generated bundles (V2-089)
from .feedback_api import router as feedback_router  # send a suggestion to the developers (V2-100)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # TWO listeners share this SAME app (43917 HTTP + 44317 HTTPS, "public domains → local engine" decision) —
    # each `uvicorn.Server` fires the ASGI lifespan independently, so this body runs TWICE per process. Most
    # pieces are already idempotent (for example the orchestrator loop checks `self._task is not None`), but the
    # bus→SSE bridges below (memory, heartbeat) had no guard: each entry created a NEW subscription to the same
    # topic → duplicated events in /events (2026-07-22 testing-marathon finding, confirmed on a clean boot:
    # "Bridge … mounted" appeared 2×). This flag on `app.state` (which persists between lifespan entries because
    # it is the SAME app) makes only the FIRST entry mount those bridges; the second skips them without touching
    # anything else in this body.
    _first_lifespan_entry = not getattr(app.state, "_bridges_mounted", False)
    app.state._bridges_mounted = True
    # LOCAL install identity (observability/identity.py) — explicit INIT, not lazy-on-first-event (operator
    # ask, 2026-08-16): a fresh self-hosted install used to get its UUID4 the first time ANY code happened to
    # call user_id() (an event emit, a session report…) — it worked, but the id stayed invisible until
    # something incidental triggered it. Calling it here, once, guarantees config/identity.json exists and is
    # logged the moment the server comes up, matching the explicitness a cloud Machine already gets for free
    # (its ZAELAR_USER_ID arrives pre-set by the provisioner). On a cloud Machine this just confirms the
    # override (cloud_account.my_user_id()) resolves — user_id() already prefers it over the local file.
    if _first_lifespan_entry:
        try:
            from observability import identity as _identity
            logger.info(f"Installation identity — user_id={_identity.user_id()}")
        except Exception as e:
            logger.warning(f"identity init failed (non-fatal): {e}")
    # v2 «Colmena» — Sistema Nervioso (bus/, V2-001). Mount the durable event log's LIFECYCLE here (attach at
    # boot, detach+close at shutdown). The bus pub/sub itself is in-memory and needs no "start"; voice/observer
    # already fans out through it (bus/sse.py) with NO new subscribers wired here — the voice hot path is
    # unchanged. The durable log (bus/log.py) had been OFF by default since V2-001 for two concrete reasons: it
    # was a SYNCHRONOUS sink (one INSERT per event on the publishing thread, sometimes the voice thread) and it
    # made zaelar.db grow without bounds. **Both are fixed** (2026-08-09): the sink only ENQUEUES and drains from a
    # dedicated thread, and retention has both an age limit and a row cap. So it is ON by default — without it,
    # flow/session observability (observability/) queries a table nobody feeds, which is exactly the bug that
    # exposed this. `ZAELAR_BUS_LOG=0` still disables it. It never breaks voice/chat.
    _bus_log = None
    try:
        if os.getenv("ZAELAR_BUS_LOG", "1") == "1":
            from bus import log as _bus_log
            _bus_log.attach()
            logger.info("Sistema Nervioso (bus/) montado — log durable de eventos ACTIVO (zaelar.db)")
        else:
            logger.info("Sistema Nervioso (bus/) montado — log durable en standby (ZAELAR_BUS_LOG=0)")
    except Exception as e:
        logger.warning(f"bus mount failed (voice/chat unaffected): {e}")
        _bus_log = None
    # Central memory v2 (memory/, V2-002/003). Starts the SINGLE write-queue consumer on THIS loop (all async writes
    # — write/reinforce/pin/link — are applied here, one writer → zero collisions) and folds the old files/uploads/
    # inbox into the episodic layer with a LAZY, idempotent, NON-destructive migration (the source is not deleted).
    # Best-effort: a failure here does not touch voice. No brain consumes it yet (that is V2-004); this only leaves
    # it ALIVE and populated. Disabled by flag for clones that do not want it yet.
    _memory_on = os.getenv("ZAELAR_MEMORY", "1") == "1"
    if _memory_on:
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
            _memory_on = False
    # V2-014 — memory→SSE bridge for the MEMORY VIEWER (🧠). Forwards the bus `memory.updated` signal (emitted by
    # every mutation in memory/api.py::_emit) to the `observer` topic — the one consumed by `GET /events` — as a
    # {kind:"memory"} event, so the frontend memory map refreshes IN REAL TIME without polling. Fine-grained,
    # decoupled bridge (memory/ does not know the frontend) that does NOT go through the /debug ring (zero
    # observability noise). The subscription lives in the uvicorn loop; the bus handles cross-loop delivery.
    _mem_sse_sub = None
    _mem_sse_task = None
    _pulse_sse_sub = None
    _pulse_sse_task = None
    if _memory_on and _first_lifespan_entry:
        try:
            import asyncio
            import bus
            _mem_sse_sub = bus.subscribe("memory.updated")

            # COALESCE (2026-07-12): memory emits `memory.updated` for EVERY mutation — and a single voice turn
            # triggers several (conversation buffer + HEART pills + reinforce + state). Forwarding them one by one
            # flooded SSE (→ the operator's "events" counter spiked while "nothing" seemed to happen). The viewer
            # only needs to know THAT something changed (it refetches with debounce), so we merge burst signals into
            # ONE signal per short window, preserving the UNION of affected ids (for live tinting). write/state/
            # reinforce collapse; a `query` (blue tint) is allowed through separately so read highlighting is not
            # lost. This cuts SSE traffic by roughly one order of magnitude without losing map reactivity.
            import os as _os
            _COALESCE_MS = float(_os.getenv("ZAELAR_MEM_SSE_COALESCE_MS", "400")) / 1000.0

            async def _mem_sse_forward(sub=_mem_sse_sub):
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

            _mem_sse_task = asyncio.create_task(_mem_sse_forward())
            logger.info("Puente memoria→SSE montado (memory.updated → /events; visor de memoria en vivo)")
        except Exception as e:
            logger.warning(f"memory→SSE bridge failed (voice/chat unaffected): {e}")
    # MeshKore connector: wire the bridge with the FlashBrain engine off the voice pipeline (untrusted profile;
    # keeps the connector brain-agnostic) and start the collaboration heartbeat — both SYNC and instant. Reconnecting the
    # clusters zaelar was subscribed to IS network I/O (a WS handshake per cluster, unbounded latency if a
    # cluster is slow/unreachable) — this used to `await` INLINE, so a slow/dead cluster held the ENTIRE lifespan
    # hostage: the app doesn't reach `yield` (start serving ANY request — including the page load and the voice
    # token endpoint) until this function returns. Voice/FlashBrain must be usable FIRST; WS reconnects are
    # deferred to their OWN background task (V2-065, operator request 2026-07-23 — see
    # `.meshkore/docs/ops/zaelar-observability.md §Boot` for the full detail).
    from connectors import meshkore
    from connectors.meshkore import store
    from connectors.meshkore.brain import make_brain
    try:
        meshkore.init(make_brain())
        meshkore.get_bridge().start_heartbeat()
        if os.getenv("MESHKORE_AUTORECONNECT", "1") == "1":
            import asyncio

            async def _meshkore_autoreconnect():
                for name, cfg in store.load_clusters().items():
                    try:
                        # `vis` (V2-086): a PUBLIC cluster reconnects without a token — if this is not propagated
                        # here, the open cluster drops on every restart and only private clusters survive.
                        await meshkore.get_manager().connect(name, cfg["cluster_id"], cfg["token"],
                                                             cfg.get("handle"), vis=cfg.get("vis", ""))
                        meshkore.get_bridge().note_objective(name)   # standing objective → peer arrival wakes the brain
                    except Exception as e:
                        logger.warning(f"MeshKore autoreconnect '{name}' failed: {e}")
            app.state.meshkore_reconnect_task = asyncio.create_task(_meshkore_autoreconnect())
    except Exception as e:
        logger.warning(f"MeshKore connector init failed (voice/chat unaffected): {e}")
    from config.v2 import active_brain
    # v2 «Colmena» — orchestrator loop (nucleo/loop.py, V2-005): the v2 brain's OWN heartbeat (scheduled tasks +
    # 🔥 sparks + memory consolidation) — completely replaces Hermes' old native cron. ONLY with BRAIN=nucleo. Same
    # loop as voice; never blocks the hot path (heavy work goes to a thread). Disabled by flag for clones that do
    # not want it.
    _loop_on = active_brain() == "nucleo" and os.getenv("ZAELAR_LOOP", "1") == "1"
    if _loop_on:
        try:
            from nucleo import loop as nucleo_loop
            nucleo_loop.start()
            logger.info("Loop orquestador v2 montado (nucleo/loop.py)")
        except Exception as e:
            logger.warning(f"orchestrator loop start failed (voice/chat unaffected): {e}")
        # Orb ECG (V2-039) — HEARTBEAT→SSE bridge. Forwards the bus `loop.tick` event (the orchestrator loop's own
        # ~1 Hz heartbeat, nucleo/loop.py:127) to the `observer` topic — the one consumed by GET /events — as
        # {kind:"pulse"}. At REST the frontend ECG beats at this REAL server rhythm (only checking crons + running
        # processes that have generated events); FlashBrain turns and live tasks already speed it up client-side.
        # Same fine-grained, decoupled pattern as the memory bridge: it goes DIRECTLY to the observer topic
        # (bus.emit_sync) → NOT through the /debug ring (zero observability noise). nucleo/ does not know the
        # frontend; the bus handles cross-loop delivery (job-thread↔uvicorn).
        if _first_lifespan_entry:
            try:
                import asyncio
                import bus
                _pulse_sse_sub = bus.subscribe("loop.tick")

                async def _pulse_sse_forward(sub=_pulse_sse_sub):
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

                _pulse_sse_task = asyncio.create_task(_pulse_sse_forward())
                logger.info("Puente latido→SSE montado (loop.tick → /events; ECG del orbe en vivo)")
            except Exception as e:
                logger.warning(f"pulse→SSE bridge failed (voice/chat unaffected): {e}")
    # v2 «Colmena» — SlowBrain dispatcher (nucleo/dispatch.py, V2-007): consumes FlashBrain escalations (bus
    # `escalate.requested`), dispatches them to async work agents (web/code/generic), and delivers the result by
    # voice+UI+[SYSTEM]. ONLY with BRAIN=nucleo (the listener only reacts to a topic emitted by the nucleo provider;
    # duo/hermes never touch it). Disabled by flag for clones that do not want it.
    _slow_on = active_brain() == "nucleo" and os.getenv("ZAELAR_SLOWBRAIN", "1") == "1"
    if _slow_on:
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
        if _first_lifespan_entry:
            try:
                from nucleo import rehydrate as nucleo_rehydrate
                _reh = nucleo_rehydrate.at_boot()
                if _reh.get("found"):
                    logger.info("Rehidratación: {} en vuelo al morir → {} reanudada(s), {} registrada(s)"
                                .format(_reh["found"], len(_reh.get("resume") or []), len(_reh.get("buried") or [])))
            except Exception as e:
                logger.warning(f"rehydrate at_boot failed (voice/chat unaffected): {e}")
    # «Susurro» (V2-053): off-hot-path conversational auditor. It plugs in ONLY through the bus (turn.completed +
    # friction signals) — zero coupling with the voice provider. First-class kill switch: config §susurro.enabled
    # (UI) + ZAELAR_SUSURRO. Fail-open: its failure never touches voice.
    _susurro_on = active_brain() == "nucleo" and os.getenv("ZAELAR_SUSURRO", "1") == "1"
    if _susurro_on:
        try:
            from nucleo import susurro as nucleo_susurro
            nucleo_susurro.start()
        except Exception as e:
            logger.warning(f"susurro start failed (voice/chat unaffected): {e}")
    # Action map (V2-539): the WATCH half — measures what the map is missing (turns the model resolved with a
    # single canvas action). Same plug as Susurro: bus only (`turn.completed`), so it covers voice and probe
    # from one place, and its failure never touches the turn.
    try:
        from nucleo.actionmap import watch as _amap_watch
        _amap_watch.start()
    except Exception as e:
        logger.warning(f"actionmap watch start failed (voice/chat unaffected): {e}")
    # Widget layer: a restart mid-generation kills the headless agent — resume what the journal says was in
    # flight (relaunch creates, report interrupted modifies). Strong ref on app.state so the GC can't drop it.
    try:
        import asyncio
        from widgets.server_api import resume_interrupted_generations
        app.state.widget_resume_task = asyncio.create_task(resume_interrupted_generations())
    except Exception as e:
        logger.warning(f"widget generation resume failed (voice/chat unaffected): {e}")
    # Backed widgets (kind:"backed", zaelar-modules.md §Widget-apps): widget-apps with a live backend (the
    # browser's headless Chromium). The supervisor discovers them in the catalog and runs each owner under a
    # supervised task in THIS loop (mailbox drain + restart-with-backoff + disable-on-repeated-failure). Owners
    # start cheap (heavy backend launches lazily on first command), so an unused backed widget costs nothing.
    try:
        from widgets import supervisor as widget_supervisor
        widget_supervisor.start()
    except Exception as e:
        logger.warning(f"backed-widget supervisor start failed (voice/chat unaffected): {e}")
    # Background widgets (V2-034): widgets that declare a `background` cycle keep working OFF-SCREEN on their
    # period (a passive widget's data.py:tick() run in a thread, or a `tick` enqueued to a backed owner) —
    # polling/refreshing and writing fresh data to memory so a voice query answers with current data even if the
    # card was never opened. Off the hot path; a failing tick is isolated (never touches voice or other widgets).
    try:
        from widgets import background as widget_background
        widget_background.start()
    except Exception as e:
        logger.warning(f"background-widget scheduler start failed (voice/chat unaffected): {e}")
    # LiveKit engine (INI-012): run the AgentServer EMBEDDED in this process (job_executor_type=THREAD), so the
    # voice job shares the bus/observer-SSE queue, the central memory, the orchestrator loop and brain_notes with
    # the «Colmena» brain (nucleo/). Gated by ZAELAR_ENGINE=livekit.
    if os.getenv("ZAELAR_ENGINE", "livekit").lower() == "livekit":
        try:
            import asyncio
            from voice.engine.pipeline.agent import make_server
            _lk = make_server()
            app.state.lk_server = _lk
            _devmode = os.getenv("ZAELAR_ENV", "dev").lower() != "prod"
            app.state.lk_task = asyncio.create_task(_lk.run(devmode=_devmode))
            logger.info("LiveKit agent worker started EMBEDDED (job_executor_type=THREAD)")
        except Exception as e:
            logger.warning(f"LiveKit embedded worker start failed: {e}")
    # Hot-path prewarm (V2-024): the FIRST FlashBrain call (AIMLAPI/Grok behind Cloudflare) sets up TLS + handshake
    # + model startup → 6-8s cold-start on the FIRST real turn. Absorb that HERE, at boot (while the frontend paints
    # the brain-mesh loader), with a minimal fire-and-forget query; also warm the search Chromium (free Google).
    # Binds the server loop for the search sync bridge. Never blocks boot; ONLY with BRAIN=nucleo.
    if active_brain() == "nucleo":
        try:
            import asyncio
            from nucleo import browser_search, energy_meter
            from nucleo.flash import prewarm as flash_prewarm
            _running_loop = asyncio.get_running_loop()
            browser_search.set_loop(_running_loop)
            # V2-102: same cross-thread bridge, for `energy_meter._fire_and_forget` — without it, every
            # `nucleo/memllm.chat_sync` caller running inside `asyncio.to_thread` (i18n bundle generation,
            # nightly REM synthesis, the new turn-completeness judge) silently lost its usage report.
            energy_meter.set_loop(_running_loop)
            app.state.prewarm_task = asyncio.create_task(flash_prewarm.run())
        except Exception as e:
            logger.warning(f"prewarm skipped (voice/chat unaffected): {e}")
    # ENERGY LEASE (ADR-0005) — request it at boot, alongside the rest of the warm-up and BEFORE the user can speak,
    # which is when they are already waiting anyway. Instant no-op on self-host. It is a TASK, not an `await`: if the
    # control plane is slow, boot does not hang — without a lease `allowed()` already says no, so waiting here would
    # not buy any safety.
    try:
        import asyncio
        from nucleo import energy_lease
        if energy_lease.enabled():
            app.state.energy_lease_task = asyncio.create_task(energy_lease.ensure(reason="boot"))
    except Exception as e:
        logger.warning(f"energy lease at boot skipped: {e}")
    # Messaging (INI-014 WhatsApp + INI-015 Telegram) — MANAGED FROM THE UI, not .env. The supervisor (a) re-starts
    # whatever the user left connected in config/connectors.json after a restart, and (b) drains the connect/
    # disconnect orders the widget enqueues (the widget can't fetch → it posts via ctx.action → store → supervisor).
    # Both connectors triage LOCALLY and write the UNIFIED store (widgets/_data/mensajeria.json); the single
    # `mensajeria` widget reads it. Off the WebRTC/voice loop — a failure here leaves voice/chat untouched.
    try:
        from connectors.messaging import supervisor
        supervisor.start()
    except Exception as e:
        logger.warning(f"messaging supervisor start failed (voice/chat unaffected): {e}")
    # HOMEOSTASIS (V2-070): the AUTONOMOUS HEARTBEAT — keeps the MACHINE healthy (recycles the degraded LiveKit
    # engine when safe, rotates logs, evicts dead capsules). Sibling of the brain, never part of it; deterministic,
    # no LLM; fail-open (a failure here never touches voice/chat). Needs `app` to recycle the embedded LiveKit worker.
    try:
        from nucleo import homeostasis
        homeostasis.start(app)
    except Exception as e:
        logger.warning(f"homeostasis start failed (voice/chat unaffected): {e}")
    try:
        yield
    finally:
        try:
            from widgets import supervisor as widget_supervisor
            await widget_supervisor.stop()
        except Exception:
            pass
        try:
            from widgets import background as widget_background
            await widget_background.stop()
        except Exception:
            pass
        try:
            from connectors.messaging import supervisor
            await supervisor.stop()
        except Exception:
            pass
        try:
            from nucleo import homeostasis
            await homeostasis.stop()
        except Exception:
            pass
        try:
            from connectors.whatsapp import service as wa_service
            await wa_service.stop()
        except Exception:
            pass
        try:
            from connectors.telegram import service as tg_service
            await tg_service.stop()
        except Exception:
            pass
        try:
            from connectors.email import service as em_service
            await em_service.stop()
        except Exception:
            pass
        try:
            _lk = getattr(app.state, "lk_server", None)
            if _lk is not None:
                await _lk.aclose()
        except Exception:
            pass
        # V2-038 §v3·L: ORDERLY shutdown — KILL Brain Workers (dispatch.stop → stop_all_async, killpg) BEFORE
        # bringing down the supervisor loop, so subprocesses are not orphaned when the loop dies.
        try:
            if _slow_on:
                from nucleo import dispatch as nucleo_dispatch
                await nucleo_dispatch.stop()
        except Exception:
            pass
        try:
            if _loop_on:
                from nucleo import loop as nucleo_loop
                await nucleo_loop.stop()
        except Exception:
            pass
        try:
            if _susurro_on:
                from nucleo import susurro as nucleo_susurro
                await nucleo_susurro.stop()
        except Exception:
            pass
        try:
            from nucleo import browser_search
            await browser_search.stop()
        except Exception:
            pass
        try:
            from connectors import meshkore
            await meshkore.shutdown()
        except Exception:
            pass
        try:
            if _mem_sse_task is not None:
                _mem_sse_task.cancel()
            if _mem_sse_sub is not None:
                import bus
                bus.unsubscribe(_mem_sse_sub)
        except Exception:
            pass
        try:
            if _pulse_sse_task is not None:
                _pulse_sse_task.cancel()
            if _pulse_sse_sub is not None:
                import bus
                bus.unsubscribe(_pulse_sse_sub)
        except Exception:
            pass
        try:
            if _memory_on:
                from memory import api as memapi
                await memapi.stop(drain=True)
        except Exception:
            pass
        try:
            if _bus_log is not None:
                _bus_log.detach()
                _bus_log.close()
        except Exception:
            pass


def create_app() -> FastAPI:
    from config.settings import load_into_env   # apply ⚙-panel overrides to env BEFORE the pipeline reads them
    load_into_env()
    app = FastAPI(title="zaelar", lifespan=_lifespan)

    # REQUEST ADMISSION (2026-08-13, replaces the fail-OPEN session-routing middleware): when this
    # process shares one public hostname with other processes holding other people's data, a request
    # is served only once this process has established that the request's session belongs to it —
    # everything else is refused rather than answered locally. Contract, allowlist and the reason the
    # previous version was a live data-exposure surface: server/ingress.py. A no-op at request time on
    # a single-process install.
    from . import ingress as _ingress
    _ingress.install(app)

    # meshkore_router is NATIVE (a channel like voice/chat), so it is always mounted regardless of BRAIN.
    # messaging_router is the UI-managed connect/disconnect API for the messaging connectors (WhatsApp/Telegram):
    # the whole point of INI-015 is that a user connects them from the widget, never by editing .env.
    # cron_router = the «Colmena» brain's OWN proactivity (nucleo/cron_api.py over nucleo/scheduler.py) — replaces
    # Hermes' old /api/cron; the same frontend ⏰ panel consumes it.
    routers = [pages_router, voice_router, widgets_router, meshkore_router, messaging_router, files_router,
               vault_router, cron_router, wizard_router, spotify_router, config_router, i18n_router,
               obs_router, feedback_router]
    # LiveKit control plane (token + connect config + session.js swap) — the default engine (INI-012).
    if os.getenv("ZAELAR_ENGINE", "livekit").lower() == "livekit":
        from .livekit_api import router as livekit_router
        routers.append(livekit_router)
    # FlashBrain headless TEST channel (V2-032, 3rd testing mode): POST /api/flash/say injects text and returns the
    # response + action + latencies, without voice or a room. Only with the «Colmena» brain (BRAIN=nucleo).
    try:
        from config.v2 import active_brain
        if active_brain() == "nucleo":
            from nucleo.flash.probe_api import router as flash_probe_router
            routers.append(flash_probe_router)
            from nucleo.agent_api import router as agent_report_router   # V2-036: CC→FlashBrain reporting channel
            routers.append(agent_report_router)
            from nucleo.worker_api import router as worker_router          # V2-038: request/response worker plane
            routers.append(worker_router)
            from widgets.navegador.act_api import router as navegador_act_router   # V2-036 F3: browser bridge
            routers.append(navegador_act_router)
    except Exception as _e:
        logger.warning(f"flash probe router not mounted: {_e!r}")
    for r in routers:
        app.include_router(r)

    # Static (browser VAD: onnx + wasm + worklet). Explicit MIME for .wasm/.mjs.
    mimetypes.add_type("application/wasm", ".wasm")
    mimetypes.add_type("text/javascript", ".mjs")
    # The interface lives under frontend/; serve its assets (ES modules under app/, vendored VAD under vad/).
    app.mount("/static", RevalidatingStatics(directory=os.path.join(common.ZAELAR_DIR, "frontend")), name="static")
    return app


app = create_app()
