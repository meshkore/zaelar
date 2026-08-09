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
from memory.server_api import router as files_router  # paste/drop uploads → EPISODIC memory (V2-003; absorbs files/)
from memory.vault_api import router as vault_router    # bóveda de secretos cifrados del operador (V2-060)
from nucleo.cron_api import router as cron_router  # proactividad PROPIA del cerebro «Colmena» (V2-005/009; ⏰ panel)
from .wizard_api import router as wizard_router  # wizard de primer arranque: perfiles local/cloud + detector (V2-040)
from .spotify_api import router as spotify_router  # conector de música Spotify (OAuth PKCE + estado), V2-041
from .config_api import router as config_router  # área de configuración full-screen + saldos de APIs (V2-043)
from .i18n_api import router as i18n_router  # UI multilingüe: state + bundles preset/generados (V2-089)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # DOS listeners comparten esta MISMA app (43917 HTTP + 44317 HTTPS, decisión "dominios públicos → motor
    # local") — cada `uvicorn.Server` dispara el lifespan ASGI de forma independiente, así que este cuerpo se
    # ejecuta DOS VECES por proceso. La mayoría de piezas ya son idempotentes (p. ej. el loop orquestador
    # comprueba `self._task is not None`), pero los puentes bus→SSE de aquí abajo (memoria, latido) no tenían
    # guarda: cada entrada creaba una suscripción NUEVA al mismo topic → eventos duplicados en /events (hallazgo
    # maratón de testing 2026-07-22, confirmado con un arranque limpio: "Puente … montado" aparecía 2×). Este
    # flag en `app.state` (persiste entre entradas del lifespan, es la MISMA app) hace que solo la PRIMERA
    # entrada monte esos puentes; la segunda los salta sin tocar nada más de este cuerpo.
    _first_lifespan_entry = not getattr(app.state, "_bridges_mounted", False)
    app.state._bridges_mounted = True
    # v2 «Colmena» — Sistema Nervioso (bus/, V2-001). Mount the durable event log's LIFECYCLE here (attach at
    # boot, detach+close at shutdown). The bus pub/sub itself is in-memory and needs no "start"; voice/observer
    # already fans out through it (bus/sse.py) with NO new subscribers wired here — the voice hot path is
    # unchanged. The durable SQLite log (bus/log.py) is a SYNCHRONOUS sink, so it is OFF by default
    # (ZAELAR_BUS_LOG, default 0) to keep the hot path byte-for-byte as today and avoid unbounded zaelar.db
    # growth from voice-token events; it flips on once the memory subsystem (V2-002/003) defines what deserves
    # durable persistence. Never breaks voice/chat.
    _bus_log = None
    try:
        if os.getenv("ZAELAR_BUS_LOG", "0") == "1":
            from bus import log as _bus_log
            _bus_log.attach()
            logger.info("Sistema Nervioso (bus/) montado — log durable de eventos ACTIVO (zaelar.db)")
        else:
            logger.info("Sistema Nervioso (bus/) montado — log durable en standby (ZAELAR_BUS_LOG=0)")
    except Exception as e:
        logger.warning(f"bus mount failed (voice/chat unaffected): {e}")
        _bus_log = None
    # Memoria central v2 (memory/, V2-002/003). Arranca el consumidor ÚNICO de la cola de escritura en ESTE loop
    # (todas las escrituras async — write/reinforce/pin/link — se aplican aquí, un solo escritor → cero colisiones)
    # y pliega la vieja bandeja files/uploads/ a la capa episódica con una migración PEREZOSA, idempotente y NO
    # destructiva (no borra el origen). Best-effort: un fallo aquí no toca la voz. Ningún cerebro la consume aún
    # (eso es V2-004); esto solo la deja VIVA y poblada. Off por flag para clones que aún no la quieren.
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
    # V2-014 — puente memoria→SSE del VISOR DE MEMORIA (🧠). Reenvía la señal `memory.updated` del bus (que emite
    # cada mutación en memory/api.py::_emit) al topic `observer` — el que consume `GET /events` — como un evento
    # {kind:"memory"}, para que el mapa de memoria del frontend se refresque EN TIEMPO REAL sin polling. Puente
    # fino y desacoplado (el módulo memory/ no conoce el frontend) que NO pasa por el ring de /debug (cero ruido de
    # observabilidad). La suscripción vive en el loop de uvicorn; la entrega cross-loop la resuelve el bus.
    _mem_sse_sub = None
    _mem_sse_task = None
    _pulse_sse_sub = None
    _pulse_sse_task = None
    if _memory_on and _first_lifespan_entry:
        try:
            import asyncio
            import bus
            _mem_sse_sub = bus.subscribe("memory.updated")

            # COALESCE (2026-07-12): la memoria emite `memory.updated` por CADA mutación — y un solo turno de voz
            # dispara varias (buffer conv + píldoras del CORAZÓN + reinforce + state). Reenviar una a una floodeaba
            # el SSE (→ el contador de "eventos" del operador se disparaba sin que pasara "nada"). El visor solo
            # necesita saber QUE algo cambió (re-fetchea con debounce), así que juntamos las señales de una ráfaga
            # en UNA sola por ventana corta, preservando la UNIÓN de ids afectados (para el tintado en vivo). Los
            # write/state/reinforce se colapsan; una `query` (tinte azul) se deja pasar aparte para no perder el
            # resaltado de lectura. Reduce el tráfico SSE ~1 orden de magnitud sin perder la reactividad del mapa.
            import os as _os
            _COALESCE_MS = float(_os.getenv("ZAELAR_MEM_SSE_COALESCE_MS", "400")) / 1000.0

            async def _mem_sse_forward(sub=_mem_sse_sub):
                # Trailing-debounce: la 1ª señal de una ráfaga arma un flush a _COALESCE_MS; las siguientes solo
                # ACUMULAN (unión de ids + último op/layer con señal). Al disparar el timer se emite UNA sola señal.
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
                    bus.emit_sync("observer", out)
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
    # deferred to their OWN background task (V2-065, petición del operador 2026-07-23 — ver
    # `.meshkore/docs/ops/zaelar-observability.md §Arranque` para el detalle completo).
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
                        # `vis` (V2-086): un cluster PÚBLICO se reconecta sin token — si no se propaga aquí, el
                        # cluster abierto se cae en cada reinicio y solo sobreviven los privados.
                        await meshkore.get_manager().connect(name, cfg["cluster_id"], cfg["token"],
                                                             cfg.get("handle"), vis=cfg.get("vis", ""))
                        meshkore.get_bridge().note_objective(name)   # standing objective → peer arrival wakes the brain
                    except Exception as e:
                        logger.warning(f"MeshKore autoreconnect '{name}' failed: {e}")
            app.state.meshkore_reconnect_task = asyncio.create_task(_meshkore_autoreconnect())
    except Exception as e:
        logger.warning(f"MeshKore connector init failed (voice/chat unaffected): {e}")
    from config.v2 import active_brain
    # v2 «Colmena» — Loop orquestador (nucleo/loop.py, V2-005): el latido PROPIO del cerebro v2 (tareas
    # programadas + 🔥 chispas + consolidación de memoria) — sustituye por completo al viejo cron nativo de Hermes.
    # SOLO con BRAIN=nucleo. Mismo loop que la voz; nunca bloquea el hot path (el trabajo pesado va a un hilo).
    # Off por flag para clones que no lo quieran.
    _loop_on = active_brain() == "nucleo" and os.getenv("ZAELAR_LOOP", "1") == "1"
    if _loop_on:
        try:
            from nucleo import loop as nucleo_loop
            nucleo_loop.start()
            logger.info("Loop orquestador v2 montado (nucleo/loop.py)")
        except Exception as e:
            logger.warning(f"orchestrator loop start failed (voice/chat unaffected): {e}")
        # ECG del orbe (V2-039) — puente LATIDO→SSE. Reenvía `loop.tick` del bus (el latido propio ~1 Hz del loop
        # orquestador, nucleo/loop.py:127) al topic `observer` — el que consume GET /events — como {kind:"pulse"}.
        # En REPOSO el electrocardiograma del frontend late a este ritmo REAL del server (solo revisando crons +
        # procesos en marcha que hayan generado eventos); los turnos del FlashBrain y las tareas vivas lo aceleran
        # ya en el cliente. Mismo patrón fino y desacoplado que el puente de memoria: va DIRECTO al topic observer
        # (bus.emit_sync) → NO pasa por el ring de /debug (cero ruido de observabilidad). El módulo nucleo/ no
        # conoce el frontend; la entrega cross-loop (job-thread↔uvicorn) la resuelve el bus.
        if _first_lifespan_entry:
            try:
                import asyncio
                import bus
                _pulse_sse_sub = bus.subscribe("loop.tick")

                async def _pulse_sse_forward(sub=_pulse_sse_sub):
                    async for ev in sub:
                        try:
                            ev = ev or {}
                            # cat:"pulse" (V2-043) → el visor lo agrupa en su propio chip (OFF por defecto): el
                            # latido ~1 Hz sigue alimentando el ECG del orbe (sse.js), pero NO ensucia el log en
                            # vivo salvo que el operador active el chip «Pulse». Así se ven las llamadas REALES
                            # de memoria in/out.
                            bus.emit_sync("observer", {"kind": "pulse", "label": "tick", "cat": "pulse",
                                                       "n": ev.get("n"), "ts": ev.get("ts")})
                        except Exception:
                            pass

                _pulse_sse_task = asyncio.create_task(_pulse_sse_forward())
                logger.info("Puente latido→SSE montado (loop.tick → /events; ECG del orbe en vivo)")
            except Exception as e:
                logger.warning(f"pulse→SSE bridge failed (voice/chat unaffected): {e}")
    # v2 «Colmena» — SlowBrain dispatcher (nucleo/dispatch.py, V2-007): consume las escaladas del FlashBrain
    # (bus `escalate.requested`), las despacha a los agentes de trabajo (web/código/genérico) async y entrega el
    # resultado por voz+UI+[SISTEMA]. SOLO con BRAIN=nucleo (el listener solo reacciona a un topic que emite el
    # provider nucleo; duo/hermes ni lo tocan). Off por flag para clones que no lo quieran.
    _slow_on = active_brain() == "nucleo" and os.getenv("ZAELAR_SLOWBRAIN", "1") == "1"
    if _slow_on:
        try:
            from nucleo import dispatch as nucleo_dispatch
            nucleo_dispatch.start()
            logger.info("SlowBrain dispatcher v2 montado (nucleo/dispatch.py)")
        except Exception as e:
            logger.warning(f"slowbrain dispatcher start failed (voice/chat unaffected): {e}")
    # «Susurro» (V2-053): auditor conversacional off-hot-path. Se enchufa SOLO por el bus (turn.completed +
    # señales de fricción) — cero acoplamiento con el provider de voz. Kill-switch de 1ª clase: config
    # §susurro.enabled (UI) + ZAELAR_SUSURRO. Fail-open: su caída jamás toca la voz.
    _susurro_on = active_brain() == "nucleo" and os.getenv("ZAELAR_SUSURRO", "1") == "1"
    if _susurro_on:
        try:
            from nucleo import susurro as nucleo_susurro
            nucleo_susurro.start()
        except Exception as e:
            logger.warning(f"susurro start failed (voice/chat unaffected): {e}")
    # Widget layer: a restart mid-generation kills the headless agent — resume what the journal says was in
    # flight (relaunch creates, report interrupted modifies). Strong ref on app.state so the GC can't drop it.
    try:
        import asyncio
        from widgets.server_api import resume_interrupted_generations
        app.state.widget_resume_task = asyncio.create_task(resume_interrupted_generations())
    except Exception as e:
        logger.warning(f"widget generation resume failed (voice/chat unaffected): {e}")
    # Backed widgets (kind:"backed", zaelar-modules.md §Widget-apps): widget-apps with a live backend (the
    # navegador's headless Chromium). The supervisor discovers them in the catalog and runs each owner under a
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
    # Prewarm del camino caliente (V2-024): la PRIMERA llamada al FlashBrain (AIMLAPI/Grok tras Cloudflare) monta
    # TLS + handshake + arranque del modelo → 6-8s de cold-start en el PRIMER turno real. La absorbemos AQUÍ, en el
    # arranque (mientras el frontend pinta el loader de la malla cerebral), con una query mínima fire-and-forget; y
    # de paso calentamos el Chromium de búsqueda (google gratis). Enlaza el loop del server para el puente sync de
    # la búsqueda. Nunca bloquea el arranque; SOLO con BRAIN=nucleo.
    if active_brain() == "nucleo":
        try:
            import asyncio
            from nucleo import browser_search
            from nucleo.flash import prewarm as flash_prewarm
            browser_search.set_loop(asyncio.get_running_loop())
            app.state.prewarm_task = asyncio.create_task(flash_prewarm.run())
        except Exception as e:
            logger.warning(f"prewarm skipped (voice/chat unaffected): {e}")
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
    # HOMEOSTASIS (V2-070): el LATIDO AUTÓNOMO — mantiene la MÁQUINA sana (recicla el motor LiveKit degradado cuando
    # es seguro, rota logs, evicta cápsulas muertas). Hermano del cerebro, nunca parte de él; determinista, sin LLM;
    # fail-open (un fallo aquí jamás toca voz/chat). Necesita `app` para reciclar el worker LiveKit embebido.
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
        # V2-038 §v3·L: apagado ORDENADO — MATA los Brain Workers (dispatch.stop → stop_all_async, killpg) ANTES de
        # tumbar el loop supervisor, para que los subprocesos no queden huérfanos cuando el loop muera.
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

    # DEMO SESSION ROUTING (INI-018, 2026-07-24): a no-op on every non-demo machine (self-host,
    # the operator's own cloud account) — my_session_id() is None there and this returns on the
    # first line, zero cost. Only matters on a cloud-demo Fly Machine (ZAELAR_DEMO_SESSION set),
    # where several Machines share one public hostname and Fly's proxy doesn't know which one is
    # "yours" — see nucleo/demo_routing.py for the full why.
    @app.middleware("http")
    async def _demo_session_routing(request, call_next):
        from nucleo import demo_routing as _dr

        if not _dr.is_demo_machine():
            return await call_next(request)

        # Static assets are IDENTICAL on every demo Machine (same image) — a JS/CSS/wasm file never
        # needs the visitor's SPECIFIC machine. Serve them LOCALLY instead of fly-replaying each one
        # to the session's machine. This is the bulk of a page load (dozens of /static/* requests);
        # replaying every one is exactly what produced the intermittent 502 WALL on assets when a
        # replay target hiccuped or was mid-boot (2026-08-04). Only stateful paths below (the HTML
        # that sets the session cookie, /api/*, the SSE stream) actually need the session's machine.
        if request.url.path.startswith("/static/"):
            return await call_next(request)

        wanted = _dr.requested_session_id(
            request.cookies.get(_dr.SESSION_COOKIE), request.query_params.get(_dr.SESSION_QUERY_PARAM)
        )
        mine = _dr.my_session_id()
        # WARM POOL: an unbound pool machine (is_demo_machine() true, but no session yet) BINDS itself
        # to the first visitor it sees carrying ?s=<id>. After this it behaves exactly like a
        # per-session machine — serves this and every later request locally (the boot was already paid
        # before the visitor arrived). Other machines route this session here via Fly metadata, which
        # the Worker stamps when it hands the machine out (see the demo-session Worker's claim step).
        if mine is None and wanted is not None:
            _dr.pin_session(wanted)
            mine = _dr.my_session_id()

        if wanted is None or wanted == mine:
            response = await call_next(request)
            if wanted == mine and not request.cookies.get(_dr.SESSION_COOKIE):
                # first hit landed via ?s=... — pin this visitor to THIS machine's domain-scoped
                # cookie for every request after, no more query param needed.
                response.set_cookie(
                    _dr.SESSION_COOKIE, mine, httponly=True, secure=True, samesite="lax", max_age=3600
                )
            return response

        # this request belongs to a DIFFERENT session than the one this machine was created for —
        # find that machine and hand off via fly-replay instead of silently serving the wrong
        # visitor's turn on the wrong instance.
        api_token = os.getenv("FLY_API_TOKEN", "")
        app_name = os.getenv("FLY_APP_NAME", "")
        if api_token and app_name:
            target = await _dr.find_machine_for_session(wanted, app_name=app_name, api_token=api_token)
            if target:
                from starlette.responses import Response as _Response
                return _Response(status_code=307, headers={"fly-replay": f"instance={target}"})
        # couldn't resolve (session expired, lookup failed, no token configured) — fail-open and
        # serve this request locally rather than dead-end the visitor.
        logger.warning(f"demo_routing: could not resolve machine for session {wanted!r}, serving locally")
        return await call_next(request)

    # ACCOUNT SESSION ROUTING (2026-08-09, unifying demo↔account — Fase 2): the real-account
    # counterpart of the demo routing above. A no-op on every Machine that isn't a real cloud
    # account (self-host, every demo Machine) — is_cloud_account() is False there, zero cost.
    @app.middleware("http")
    async def _account_session_routing(request, call_next):
        from nucleo import account_routing as _ar

        if not _ar.is_account_routing_machine():
            return await call_next(request)
        if request.url.path.startswith("/static/"):
            return await call_next(request)

        token = request.cookies.get(_ar.SESSION_COOKIE)
        if not token:
            # no cloud session cookie at all (shouldn't happen once Fase 2's cookie is set correctly,
            # but fail-open — serve locally rather than dead-end a request) — never touches the
            # network for the common "this IS the right machine" case.
            return await call_next(request)

        control_plane_url = os.getenv("CONTROL_PLANE_URL", "")
        mine = _ar.my_machine_id()
        if not control_plane_url or not mine:
            return await call_next(request)

        target = await _ar.find_machine_for_session(token, control_plane_url=control_plane_url)
        if target is None or target == mine:
            return await call_next(request)

        # wrong Machine for this session's account — hand off via fly-replay, same technique as demo.
        from starlette.responses import Response as _Response
        return _Response(status_code=307, headers={"fly-replay": f"instance={target}"})

    # meshkore_router is NATIVE (a channel like voice/chat), so it is always mounted regardless of BRAIN.
    # messaging_router is the UI-managed connect/disconnect API for the messaging connectors (WhatsApp/Telegram):
    # the whole point of INI-015 is that a user connects them from the widget, never by editing .env.
    # cron_router = proactividad PROPIA del cerebro «Colmena» (nucleo/cron_api.py sobre nucleo/scheduler.py) —
    # sustituye al viejo /api/cron de Hermes; el mismo panel ⏰ del frontend lo consume.
    routers = [pages_router, voice_router, widgets_router, meshkore_router, messaging_router, files_router,
               vault_router, cron_router, wizard_router, spotify_router, config_router, i18n_router]
    # LiveKit control plane (token + connect config + session.js swap) — the default engine (INI-012).
    if os.getenv("ZAELAR_ENGINE", "livekit").lower() == "livekit":
        from .livekit_api import router as livekit_router
        routers.append(livekit_router)
    # Canal de PRUEBA headless del FlashBrain (V2-032, 3ª forma de testing): POST /api/flash/say inyecta texto y
    # devuelve la respuesta + acción + latencias, sin voz ni sala. Solo con el cerebro «Colmena» (BRAIN=nucleo).
    try:
        from config.v2 import active_brain
        if active_brain() == "nucleo":
            from nucleo.flash.probe import router as flash_probe_router
            routers.append(flash_probe_router)
            from nucleo.agent_api import router as agent_report_router   # V2-036: canal de reporte CC→FlashBrain
            routers.append(agent_report_router)
            from nucleo.worker_api import router as worker_router          # V2-038: plano request/response workers
            routers.append(worker_router)
            from widgets.navegador.act_api import router as navegador_act_router   # V2-036 F3: puente de navegador
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
