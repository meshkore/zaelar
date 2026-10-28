"""zaelar server (package). FastAPI app: the frontend + the voice control plane.

Voice engine: LiveKit Agents, run EMBEDDED in this process (AgentServer, job_executor_type=THREAD) so
the voice job shares the bus/observer-SSE queue, the central memory, the orchestrator loop and the brain_notes
mailbox with the «Colmena» brain (nucleo/) and everything else. Gated by ZAELAR_ENGINE (default 'livekit'; set
'off' to skip the worker, e.g. for CI import checks). Session state lives in server/state.py.
"""
import mimetypes
import os

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
from .screens_api import router as screens_router  # V2-792: one agent, many screens (typed door, registry)
from .notices_api import router as notices_router  # V2-796: the notice ledger + Web Push subscriptions
from rules.api import router as rules_router        # V2-806: ⚙ Settings → Rules over the rules table
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
from server.memory_viewer_api import router as memory_viewer_router  # V2-808: every store, counted and paged
from memory.vault_api import router as vault_router    # operator encrypted-secrets vault (V2-060)
from update.api import router as update_router      # V2-553: the update channel (build number + «reload?»)
from observability.api import router as obs_router    # flows/sessions/identity (correlation id, 2026-08-09)
from nucleo.cron_api import router as cron_router  # «Colmena» brain's own proactivity (V2-005/009; ⏰ panel)
from .wizard_api import router as wizard_router  # first-run wizard: local/cloud profiles + detector (V2-040)
from .spotify_api import router as spotify_router  # Spotify music connector (OAuth PKCE + state), V2-041
from .config_api import router as config_router  # full-screen configuration area + API balances (V2-043)
from .i18n_api import router as i18n_router  # multilingual UI: state + preset/generated bundles (V2-089)
from .feedback_api import router as feedback_router  # send a suggestion to the developers (V2-100)
from .daemon_api import router as daemon_router  # V2-575 P1: status + folder permissions of the LOCAL DAEMON
from .lifespan import lifespan  # what starts, in which order, and what stops (refactor2710-13 T-03)


def create_app() -> FastAPI:
    from config.settings import load_into_env   # apply ⚙-panel overrides to env BEFORE the pipeline reads them
    load_into_env()
    app = FastAPI(title="zaelar", lifespan=lifespan)

    # REQUEST ADMISSION (2026-08-13, replaces the fail-OPEN session-routing middleware): when this
    # process shares one public hostname with other processes holding other people's data, a request
    # is served only once this process has established that the request's session belongs to it —
    # everything else is refused rather than answered locally. Contract, allowlist and the reason the
    # previous version was a live data-exposure surface: server/ingress.py. A no-op at request time on
    # a single-process install.
    from . import ingress as _ingress
    _ingress.install(app)
    # A WORKER'S REQUEST IS NEVER HIS CLICK (2026-10-14): a mutation is admitted for his screen (UI cookie) or a
    # process the engine did not spawn, never for a worker's curl. Contract: server/operator_gate.py.
    from . import operator_gate as _operator_gate
    _operator_gate.install(app)
    # WHO MAY CALL /api/* (V2-778 F4-35): on a self-hosted engine, only this machine and never a page from another
    # site (CSRF, DNS rebinding); on a cloud account, a mutation only from the account's own site. Added after
    # ingress, so it is the OUTER middleware and refuses before any session lookup. Contract: server/api_guard.py.
    from . import api_guard as _api_guard
    _api_guard.install(app)

    # meshkore_router is NATIVE (a channel like voice/chat), so it is always mounted regardless of BRAIN.
    # messaging_router is the UI-managed connect/disconnect API for the messaging connectors (WhatsApp/Telegram):
    # the whole point is that a user connects them from the widget, never by editing .env.
    # cron_router = the «Colmena» brain's OWN proactivity (nucleo/cron_api.py over nucleo/scheduler.py) — replaces
    # Hermes' old /api/cron; the same frontend ⏰ panel consumes it.
    routers = [pages_router, voice_router, canvas_router, widgets_router, meshkore_router, messaging_router,
               files_router, memory_viewer_router,
               vault_router, wizard_router, spotify_router, config_router, i18n_router,
               obs_router, feedback_router, update_router, cloudfiles_router, photos_router, contacts_router,
               videoacct_router, calendar_router, torrent_router, library_router, daemon_router,
               tasks_router, screens_router, notices_router, rules_router]
    # LiveKit control plane (token + connect config + session.js swap), the default engine.
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
        from nucleo.cli.api import router as flash_probe_router
        routers.append(flash_probe_router)
        from nucleo.agent_api import router as agent_report_router   # V2-036: CC→FlashBrain reporting channel
        routers.append(agent_report_router)
        from nucleo.cli.worker_api import router as worker_router          # V2-038: request/response worker plane
        routers.append(worker_router)
        from search.api import router as search_router                 # V2-782: the search service's HTTP face
        routers.append(search_router)
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
