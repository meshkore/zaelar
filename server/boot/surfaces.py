"""Boot phase 3 — the language top-up, widgets, the embedded voice worker, the hot-path prewarm and its seams, the
energy lease, the messaging connectors and homeostasis (from the lifespan of `server/__init__.py`, V2-778 F1 →
refactor2710-13 T-03; same code, same order)."""
from __future__ import annotations

import asyncio
import os

from loguru import logger


def language_top_up(app, first_lifespan_entry: bool) -> None:
    # LANGUAGE TOP-UP AFTER AN UPDATE (V2-676). `i18n.init.prepare()` is the idempotent entry that fills in
    # whatever manifest keys a language is missing — a brand-new language at onboarding, and equally the NEW
    # KEYS an update ships. Its own docstring has claimed since V2-089 that "the boot sequence and the
    # language-switch path" both call it. Only the second one ever did: `detect.lock()` and a `/api/i18n/ensure`
    # endpoint nobody calls. So a self-hoster running in French who updated the engine kept every new label in
    # English for good, with nothing anywhere saying why — the operator's own report, in his English session,
    # of a product mixing two languages at once.
    #
    # It runs DETACHED and never blocks the boot: a preset language is a dict comparison, and a language that
    # does need generating must not hold the server down while an LLM answers. A failure is logged and the
    # engine comes up with the keys it already had.
    try:
        from i18n import runtime as _i18n_rt

        def _detect_pending() -> bool:
            try:
                from i18n.init import detect as _d
                return bool(_d.should_detect())
            except Exception:  # noqa: BLE001
                return False

        async def _top_up_language() -> None:
            code = _i18n_rt.active_code()
            try:
                from i18n import init as _i18n_init
                r = await _i18n_init.prepare(code)
                if n := sum(int((v or {}).get("generated") or 0) for v in (r.get("packs") or {}).values()):
                    logger.info(f"i18n: '{code}' topped up after an update — {n} new strings translated")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"i18n top-up for '{code}' failed (UI keeps the keys it had): {e!r}")

        if first_lifespan_entry:
            app.state._i18n_topup = asyncio.create_task(_top_up_language())
            # V2-765 — the action map seeds itself on first read, and the first read was the operator's first
            # TURN: after a reset (3100 rows, 3.3 s alone, far more under a live session) his «¿Me oyes?» waited
            # 24 s and the STT errored out. Seeded here, off the loop, before anybody speaks.
            if not _detect_pending():
                from nucleo.actionmap import store as _am_store
                app.state._am_warm = asyncio.create_task(asyncio.to_thread(_am_store.index))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"i18n top-up not scheduled (UI unaffected): {e}")


def widgets(app) -> None:
    # Widget layer: a restart mid-generation kills the headless agent — resume what the journal says was in
    # flight (relaunch creates, report interrupted modifies). Strong ref on app.state so the GC can't drop it.
    try:
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


def voice_worker(app) -> None:
    # LiveKit engine: run the AgentServer EMBEDDED in this process (job_executor_type=THREAD), so the
    # voice job shares the bus/observer-SSE queue, the central memory, the orchestrator loop and brain_notes with
    # the «Colmena» brain (nucleo/). Gated by ZAELAR_ENGINE=livekit.
    if os.getenv("ZAELAR_ENGINE", "livekit").lower() == "livekit":
        try:
            from voice.engine.pipeline.agent import make_server
            _lk = make_server()
            app.state.lk_server = _lk
            _devmode = os.getenv("ZAELAR_ENV", "dev").lower() != "prod"
            app.state.lk_task = asyncio.create_task(_lk.run(devmode=_devmode))
            logger.info("LiveKit agent worker started EMBEDDED (job_executor_type=THREAD)")
        except Exception as e:
            logger.warning(f"LiveKit embedded worker start failed: {e}")


def prewarm_and_seams(app, active_brain) -> None:
    # Hot-path prewarm (V2-024): the FIRST FlashBrain call (AIMLAPI/Grok behind Cloudflare) sets up TLS + handshake
    # + model startup → 6-8s cold-start on the FIRST real turn. Absorb that HERE, at boot (while the frontend paints
    # the brain-mesh loader), with a minimal fire-and-forget query; also warm the search Chromium (free Google).
    # Binds the server loop for the search sync bridge. Never blocks boot; ONLY with BRAIN=nucleo.
    if active_brain() != "nucleo":
        return
    try:
        from nucleo.energy import meter as energy_meter
        from nucleo.llm import prewarm as flash_prewarm
        from search import browser as browser_search, hooks as _search_hooks
        _running_loop = asyncio.get_running_loop()
        browser_search.set_loop(_running_loop)
        # V2-782: the search service's seams — the status light and the timeline — wired here, where the engine
        # knows them; standalone the service runs with both unset.
        try:
            from voice import health_state as _hs
            from voice.observer import emit as _emit_obs
            _search_hooks.on_chain_failure = lambda kind, detail: _hs.record("search", kind, detail)
            _search_hooks.emit = _emit_obs
            # …and one probe for the status panel, well after boot and off the loop (a few paid calls, once).
            from search import api as _search_api
            _running_loop.call_later(45.0, lambda: _running_loop.run_in_executor(None, _search_api.prime_cache))
        except Exception as _e:  # noqa: BLE001 — a missing seam leaves the service standalone, never breaks boot
            logger.warning(f"search hooks not wired: {_e}")
        # V2-102: same cross-thread bridge, for `energy_meter._fire_and_forget` — without it, every
        # `nucleo/memllm.chat_sync` caller running inside `asyncio.to_thread` (i18n bundle generation,
        # nightly REM synthesis, the new turn-completeness judge) silently lost its usage report.
        energy_meter.set_loop(_running_loop)
        # V2-562: same bridge again, and here the off-loop case is the NORMAL one — a work session opens
        # lazily from whichever thread emits the first event, so without this its report to the central
        # activity registry was dropped exactly where it mattered and the registry recorded nobody.
        from observability import identity as _identity
        _identity.set_loop(_running_loop)
        # V2-601 T-06: memory ingestion gets a HOME loop — `ingest_utterance` fires from both event loops
        # and its serializing asyncio.Lock cannot span them (a contended cross-loop acquire poisons it and
        # silently loses writes). Every ingest marshals here; see nucleo/memory_agent/ingest.py.
        from nucleo import memory_agent as _mem_agent
        _mem_agent.set_loop(_running_loop)
        app.state.prewarm_task = asyncio.create_task(flash_prewarm.run())
    except Exception as e:
        logger.warning(f"prewarm skipped (voice/chat unaffected): {e}")


def guardians(app, first_lifespan_entry: bool) -> None:
    # V2-750 — THE ONLY PIECE THAT ASKS A PROVIDER HOW IT IS. Everything else here learns by failing (see the
    # note in `voice/health_state.py`), which is right for cost but leaves the light stuck: one bad turn painted
    # the panel red for 600 s and only a successful VOICE turn could repaint it. Measured 2026-09-22 — the panel
    # read «no responde» for six minutes while DeepSeek answered in 1.2 s. Idle and network-free while healthy.
    try:
        from nucleo.flash import titular_watch
        if first_lifespan_entry:
            app.state.titular_watch_task = asyncio.create_task(titular_watch.run())
    except Exception as e:
        logger.warning(f"titular watch skipped (the light may stay stale): {e}")
    # ENERGY LEASE — request it at boot, alongside the rest of the warm-up and BEFORE the user can speak,
    # which is when they are already waiting anyway. Instant no-op on self-host. It is a TASK, not an `await`: if the
    # lease endpoint is slow, boot does not hang — without a lease `allowed()` already says no, so waiting here would
    # not buy any safety. A FRESH lease, always (V2-801): the one the previous process persisted is not the answer,
    # and no stop decision is taken until this request is answered.
    try:
        from nucleo.energy import lease as energy_lease
        if energy_lease.enabled():
            app.state.energy_lease_task = energy_lease.start_at_boot()
    except Exception as e:
        logger.warning(f"energy lease at boot skipped: {e}")
    # Messaging (WhatsApp + Telegram) — MANAGED FROM THE UI, not .env. The supervisor (a) re-starts
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
        from nucleo.pulse import homeostasis
        homeostasis.start(app)
    except Exception as e:
        logger.warning(f"homeostasis start failed (voice/chat unaffected): {e}")
    # V2-831 T-28: a THREAD that sees a frozen loop or a host out of memory — sheds load, then (supervised) exits.
    try:
        from nucleo.pulse import self_watchdog
        self_watchdog.start()
    except Exception as e:
        logger.warning(f"self watchdog start failed (voice/chat unaffected): {e}")


async def start(app, first_lifespan_entry: bool) -> None:
    """Runs the phase. Its handles live on `app.state` (`lk_server`, the tasks)."""
    from config.v2 import active_brain
    language_top_up(app, first_lifespan_entry)
    widgets(app)
    voice_worker(app)
    prewarm_and_seams(app, active_brain)
    guardians(app, first_lifespan_entry)
