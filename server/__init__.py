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
from .tasks_api import router as tasks_router      # V2-728: the task board, extracted from voice_api
from .voice_api import router as voice_router
from .canvas_api import router as canvas_router  # V2-778 F1: the canvas routes, extracted from voice_api
from widgets.server_api import router as widgets_router  # isolated widget layer (does not touch the voice core)
from connectors.meshkore.server_api import router as meshkore_router  # native cluster I/O channel (always on)
from connectors.messaging.server_api import router as messaging_router  # UI-managed connect/disconnect of connectors
from connectors.files.server_api import router as cloudfiles_router  # V2-557: OAuth + state for Drive/OneDrive (/api/cloudfiles/*; NOT /api/files/*, taken by memory_routes)
from connectors.photos.server_api import router as photos_router  # V2-564: Google Photos Picker (/api/photos/*)
from connectors.contacts.server_api import router as contacts_router  # V2-699: Google Contacts import (/api/contacts/*)
from connectors.video.server_api import router as videoacct_router  # V2-597: YouTube account OAuth (/api/video/*)
from connectors.calendar.server_api import router as calendar_router  # V2-679: Google Calendar OAuth + sync (/api/calendar/*)
from connectors.torrent.server_api import router as torrent_router  # V2-637: embedded torrent client + Range stream (/api/torrent/*)
from library.server_api import router as library_router  # V2-638: the agent's own filesystem (/api/library/*)
from server.memory_routes import router as files_router  # paste/drop uploads → EPISODIC memory (V2-003; absorbs files/)
from memory.vault_api import router as vault_router    # operator encrypted-secrets vault (V2-060)
from update.api import router as update_router      # V2-553: the update channel (build number + «reload?»)
from bus.sse import publish as _sse_publish   # ONLY gate into the observer topic: stamps install+session
from observability.api import router as obs_router    # flows/sessions/identity (correlation id, 2026-08-09)
from nucleo.cron_api import router as cron_router  # «Colmena» brain's own proactivity (V2-005/009; ⏰ panel)
from .wizard_api import router as wizard_router  # first-run wizard: local/cloud profiles + detector (V2-040)
from .spotify_api import router as spotify_router  # Spotify music connector (OAuth PKCE + state), V2-041
from .config_api import router as config_router  # full-screen configuration area + API balances (V2-043)
from .i18n_api import router as i18n_router  # multilingual UI: state + preset/generated bundles (V2-089)
from .feedback_api import router as feedback_router  # send a suggestion to the developers (V2-100)
from .daemon_api import router as daemon_router  # V2-575 P1: status + folder permissions of the LOCAL DAEMON


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
    # V2-778 F1 — the engine's start (identity, bus, memory, loop, workers, widgets, connectors) lives in
    # `server/boot.py`.
    _blk = await _boot.start_the_engine(
        app=app,
    )
    if '_bus_log' in _blk:
        _bus_log = _blk['_bus_log']
    if '_lk' in _blk:
        _lk = _blk['_lk']
    if '_loop_on' in _blk:
        _loop_on = _blk['_loop_on']
    if '_mem_sse_sub' in _blk:
        _mem_sse_sub = _blk['_mem_sse_sub']
    if '_mem_sse_task' in _blk:
        _mem_sse_task = _blk['_mem_sse_task']
    if '_memory_on' in _blk:
        _memory_on = _blk['_memory_on']
    if '_pulse_sse_sub' in _blk:
        _pulse_sse_sub = _blk['_pulse_sse_sub']
    if '_pulse_sse_task' in _blk:
        _pulse_sse_task = _blk['_pulse_sse_task']
    if '_slow_on' in _blk:
        _slow_on = _blk['_slow_on']
    if '_susurro_on' in _blk:
        _susurro_on = _blk['_susurro_on']
    if 'browser_search' in _blk:
        browser_search = _blk['browser_search']
    if 'bus' in _blk:
        bus = _blk['bus']
    if 'homeostasis' in _blk:
        homeostasis = _blk['homeostasis']
    if 'memapi' in _blk:
        memapi = _blk['memapi']
    if 'meshkore' in _blk:
        meshkore = _blk['meshkore']
    if 'nucleo_dispatch' in _blk:
        nucleo_dispatch = _blk['nucleo_dispatch']
    if 'nucleo_loop' in _blk:
        nucleo_loop = _blk['nucleo_loop']
    if 'nucleo_susurro' in _blk:
        nucleo_susurro = _blk['nucleo_susurro']
    if 'supervisor' in _blk:
        supervisor = _blk['supervisor']
    if 'widget_background' in _blk:
        widget_background = _blk['widget_background']
    if 'widget_supervisor' in _blk:
        widget_supervisor = _blk['widget_supervisor']
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
    # WHO MAY CALL /api/* (V2-778 F4-35): on a self-hosted engine, only this machine and never a page from another
    # site (CSRF, DNS rebinding); on a cloud account, a mutation only from the account's own site. Added after
    # ingress, so it is the OUTER middleware and refuses before any session lookup. Contract: server/api_guard.py.
    from . import api_guard as _api_guard
    _api_guard.install(app)

    # meshkore_router is NATIVE (a channel like voice/chat), so it is always mounted regardless of BRAIN.
    # messaging_router is the UI-managed connect/disconnect API for the messaging connectors (WhatsApp/Telegram):
    # the whole point of INI-015 is that a user connects them from the widget, never by editing .env.
    # cron_router = the «Colmena» brain's OWN proactivity (nucleo/cron_api.py over nucleo/scheduler.py) — replaces
    # Hermes' old /api/cron; the same frontend ⏰ panel consumes it.
    routers = [pages_router, voice_router, canvas_router, widgets_router, meshkore_router, messaging_router,
               files_router,
               vault_router, wizard_router, spotify_router, config_router, i18n_router,
               obs_router, feedback_router, update_router, cloudfiles_router, photos_router, contacts_router,
               videoacct_router, calendar_router, torrent_router, library_router, daemon_router,
               tasks_router]
    # LiveKit control plane (token + connect config + session.js swap) — the default engine (INI-012).
    if os.getenv("ZAELAR_ENGINE", "livekit").lower() == "livekit":
        from .livekit_api import router as livekit_router
        routers.append(livekit_router)
    # FlashBrain headless TEST channel (V2-032, 3rd testing mode): POST /api/flash/say injects text and returns the
    # response + action + latencies, without voice or a room. Only with the «Colmena» brain (BRAIN=nucleo).
    #
    # ⚠️ NO broad except around the mounts (V2-554 → V2-601 T-08). This block used to be one try/except that
    # turned a FATAL misconfig (e.g. `config/models.default.json` missing from the image — it happened) into ONE
    # warning line: the app booted "green", /healthz answered 200, the release smoke passed — and the product had
    # no probe, no worker plane and no browser bridge. The two cases V2-554 told apart get opposite treatment:
    #   · brain deliberately NOT nucleo → skip quietly (a baseline profile is a choice, not a fault);
    #   · brain IS nucleo and a mount fails → RAISE, so the boot dies where the smoke can see it.
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
        # /api/cron mounts ONLY with the brain whose loop fires the jobs (V2-601 T-13). Ungated, a cron was
        # accepted, persisted and never fired — the silent-alarm class V2-121 already paid for. A 404 on a
        # baseline profile is honest; a 200 over a scheduler nobody runs is not.
        routers.append(cron_router)
    for r in routers:
        app.include_router(r)

    # Static (browser VAD: onnx + wasm + worklet). Explicit MIME for .wasm/.mjs.
    mimetypes.add_type("application/wasm", ".wasm")
    mimetypes.add_type("text/javascript", ".mjs")
    # The interface lives under frontend/; serve its assets (ES modules under app/, vendored VAD under vad/).
    app.mount("/static", RevalidatingStatics(directory=os.path.join(common.ZAELAR_DIR, "frontend")), name="static")
    return app


app = create_app()

# V2-778 F1 — the start half of the lifespan; imported at the end (it reads this module back).
from server import boot as _boot  # noqa: E402
