"""Voice HTTP API (LiveKit engine, INI-012).

The WebRTC transport, ICE/TURN negotiation and the audio pipeline are owned by the LiveKit engine now
(voice/engine/ + the embedded worker + server/livekit_api.py). This module keeps only the engine-agnostic
HTTP surface the front still needs: user name, the SSE event stream (observer), debug/status/providers panels,
the ⚙ settings + voice catalog, and client-log ingestion. No Pipecat, no /api/offer, no /api/ice-servers.
"""
import asyncio
import json
import os
import time

from fastapi import APIRouter, Request
from loguru import logger
from fastapi.responses import JSONResponse, StreamingResponse
from voice.observer import (
    clear_log,
    debug_events,
    emit,
    rotate_session,
    session_info,
    subscribe,
    unsubscribe,
)

from . import state as S
from .canvas_api import (  # noqa: E402,F401 — V2-778 F1: moved, imported back under their names
    _live_canvas_instances, _prune_ghost_sheets, _sheet_ids_on_disk, canvas_arrange, canvas_layout, canvas_state)

router = APIRouter()


@router.post("/user")
async def set_user(payload: dict):
    S.STATE["user_name"] = (payload.get("name") or "").strip()[:40]
    return JSONResponse({"name": S.STATE["user_name"]})


@router.get("/api/voices")
async def voices():
    """Voices of the CURRENT TTS provider (cycled by tapping the orb). Provider itself is changed in the ⚙ config."""
    from voice.engine.speech.voices import tts_provider, voices_for
    vs = voices_for()
    cur = S.STATE.get("voice", 0) % len(vs)
    return JSONResponse({"provider": tts_provider(), "voices": [v["label"] for v in vs], "current": cur})


@router.post("/api/test-voice")
async def test_voice(payload: dict):
    """▶ test button in the ⚙ voice picker: WOULD synthesize a short sample for {provider, voice}.
    Not available yet on the LiveKit engine (the old voice/tts/sample.py path is gone). Degrades gracefully
    so the ⚙ picker still works (the voice change applies on reconnect); this is a nice-to-have audition only."""
    # TODO INI-012: audition a voice over the LiveKit TTS plugins (Cartesia/Kokoro) without spinning up a full
    # AgentSession — e.g. call the plugin's synthesize() into an in-memory buffer and return it as audio.
    return JSONResponse(
        {"error": "audición de voz no disponible aún en el motor LiveKit (INI-012)"},
        status_code=501,
    )


@router.post("/config")
async def set_config(payload: dict):
    """Session config from the UI before connecting. voice = index into the CURRENT provider's voices (orb cycles)."""
    from voice.engine.speech.voices import voices_for
    vs = voices_for()
    if "voice" in payload:
        try:
            S.STATE["voice"] = int(payload["voice"]) % len(vs)
        except Exception:
            pass
    cur = S.STATE.get("voice", 0) % len(vs)
    return JSONResponse({"voice": cur, "label": vs[cur]["label"]})


@router.get("/events")
async def events():
    q = subscribe()

    async def gen():
        try:
            yield f"data: {json.dumps({'kind':'session','label':'SSE'})}\n\n"
            while True:
                ev = await q.get()
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/api/debug")
async def debug(kind: str = "", limit: int = 0):
    """Everything that happened this session: voice/turn edges, transcripts, brain prompts/replies, latencies,
    silences, TTS, errors. Filter with ?kind=brain|transcript|error|… and tail with ?limit=N."""
    return JSONResponse({"session": session_info(), "events": debug_events(kind, limit)})


@router.get("/api/debug/stacks")
async def debug_stacks():
    """Every thread's stack + every asyncio task (with await stack) of each registered loop — the question
    «where exactly is this coroutine parked?» answered by the live process itself. Born for the 2026-08-31
    playout wedge (speech synthesized, never played, no exception); see `voice/debug_stacks.py`."""
    from voice import debug_stacks as _stacks
    return JSONResponse(_stacks.collect())


@router.get("/api/providers")
async def providers():
    """The provider CATALOG actually wired in code: per function, the current default + the alternatives we have
    configured (NOT hypothetical). Powers the Modules screen. Policy: prefer free/local by default where it works.
    Voice data (STT/TTS/VAD) now comes from the LiveKit engine (voice/engine)."""
    from voice.engine.core.config import SETTINGS

    def has(*keys):
        return any(os.getenv(k) for k in keys)

    def opt(label, cost, usable, default=False, needs=""):
        return {"label": label, "cost": cost, "usable": bool(usable), "default": default, "needs": needs}

    import importlib.util
    stt_cur = SETTINGS.stt_provider
    tts_cur = SETTINGS.tts_provider
    whisper_ok = importlib.util.find_spec("faster_whisper") is not None
    kokoro_reachable = True  # local Kokoro-FastAPI endpoint (SETTINGS.kokoro_url); assumed present if selected
    functions = [
        # STT · voice → text — engine providers: voxtral (cloud), deepgram (cloud), whisper_local (on-machine).
        {"fn": "STT · voz → texto", "options": [
            opt("Voxtral · Mistral (cloud)", "paid·barato", has("MISTRAL_API_KEY"), stt_cur == "voxtral", "MISTRAL_API_KEY"),
            opt("Deepgram Nova-3 (cloud)", "free·tier", has("DEEPGRAM_API_KEY"), stt_cur == "deepgram", "DEEPGRAM_API_KEY"),
            opt("Whisper local (privado · gratis)", "free·local", whisper_ok, stt_cur == "whisper_local", "faster-whisper")]},
        # TTS · text → voice — engine providers: cartesia (cloud), kokoro_local (on-machine).
        {"fn": "TTS · texto → voz", "options": [
            opt("Cartesia Sonic", "paid", has("CARTESIA_API_KEY"), tts_cur == "cartesia", "CARTESIA_API_KEY"),
            opt("Kokoro local (es/en · privado)", "free·local", kokoro_reachable, tts_cur == "kokoro_local", "Kokoro-FastAPI local")]},
        {"fn": "LLM · modelo (cerebro)", "options": [
            # Non-reasoners only on the voice path (hard rule): a reasoner does not close the turn → zaelar goes mute.
            opt(f"{os.getenv('LLM_MODEL','deepseek/deepseek-v4-flash')} · AIMLAPI", "paid·barato", has("AIMLAPI_KEY", "LLM_API_KEY"), True, "AIMLAPI_KEY"),
            opt("gpt-4.1 · AIMLAPI (validado · más caro)", "paid", has("AIMLAPI_KEY"), False, "AIMLAPI_KEY"),
            opt("Cualquier endpoint OpenAI-compatible", "varía", True, False, "LLM_BASE_URL + LLM_API_KEY")]},
        {"fn": "VAD · turno", "options": [opt("Silero (LiveKit, server-side)", "free·local", True, True)]},
    ]
    return JSONResponse({"functions": functions})


@router.get("/api/status")
async def status():
    """SYSTEM STATUS for the ⓘ panel: is Hermes up, is voice live, are the external APIs (LLM/STT/TTS) healthy or
    out of credit, is the cluster connected. Each item is {key,label,state,detail}; `state` ∈ ok|warn|error|off.
    `overall` is the worst of them (drives the top icon: green/amber/red-blink). Credit/outage errors come from the
    reactive health guard (voice/health_state.py) — we can't poll a balance, so we surface the LAST real failure.
    Voice data (STT/TTS provider) now comes from the LiveKit engine (voice/engine/core/config.py SETTINGS)."""
    from voice import health_state
    from voice.engine.core.config import SETTINGS
    from . import active

    def has(*keys):
        return any(os.getenv(k) for k in keys)

    # V2-778 F1 — the brain, the voice and its providers in the status live in `server/voice_status.py`.
    _blk = await _vstatus.brain_and_voice(
        SETTINGS=SETTINGS,
        active=active,
        has=has,
        health_state=health_state,
    )
    if 'brain' in _blk:
        brain = _blk['brain']
    if 'items' in _blk:
        items = _blk['items']

    # ── Memory · write HEART (V2-066, operator request: no banner, only the status ◉) ─────────────────────────
    # V2-778 F1 — the rest of the status and its overall light live in `server/voice_status.py`.
    _blk = await _vstatus.the_rest_and_the_light(
        SETTINGS=SETTINGS,
        brain=brain,
        has=has,
        health_state=health_state,
        items=items,
    )
    if 'overall' in _blk:
        overall = _blk['overall']
    return JSONResponse({"overall": overall, "items": items})


@router.get("/api/settings")
async def get_settings():
    """The ⚙ config panel: current values + option lists for the swappable knobs (STT/TTS/voice/language/brain)."""
    from config.settings import effective
    return JSONResponse(effective())


@router.post("/api/settings")
async def post_settings(payload: dict):
    """Set knobs BY HAND (no file editing). Persists overrides + applies to env; tells the front what to reconnect."""
    from config.settings import update
    return JSONResponse(update(payload or {}))


@router.get("/api/stt-mode")
async def stt_mode():
    """On the LiveKit engine, STT is ALWAYS server-side (no browser Web Speech path). The front keeps the endpoint
    for compatibility; it now always reports mode=server + the configured language."""
    from voice.engine.core.config import SETTINGS
    lang = SETTINGS.language or os.getenv("ZAELAR_LANGUAGE", "en")
    return JSONResponse({"mode": "server", "lang": lang})


@router.post("/api/client-log")
async def client_log(payload: dict):
    """Browser-side diagnostics into the SAME debug stream (so /debug shows the mic device, muted state and the
    measured browser-side RMS). This is how we tell apart 'mic captures silence in the browser' from server issues."""
    label = str(payload.get("label", "client"))[:80]
    text = str(payload.get("text", ""))[:300]
    return JSONResponse(emit("client", label, text=text, extra={k: payload[k] for k in
                             ("device", "muted", "enabled", "state", "rms", "raw") if k in payload}))


@router.post("/api/mic")
async def mic_switch(payload: dict):
    """V2-654 — THE microphone switch, told to the engine. The browser's `services/mic.js` is the only writer and
    it calls here on every change AND on every (re)connect; the session heartbeat re-asserts the same value every
    ~4s, so a divergence between icon and engine cannot outlive one beat.

    Before this route the mute existed ONLY in the browser and only as an icon signal: four of its six writers
    never touched the audio track, so the engine heard a microphone the operator had closed and had no way to
    know (session 85eec898). Reading it is `voice/mic_input.py`; the gate that uses it is in the turn path."""
    from voice import mic_input
    muted = bool((payload or {}).get("muted"))
    src = str((payload or {}).get("src") or "frontend")[:40]
    return JSONResponse(mic_input.set_muted(muted, source=src))


@router.get("/api/mic")
async def mic_state():
    """The engine's own answer, so the client can VERIFY instead of assuming its write landed."""
    from voice import mic_input
    return JSONResponse(mic_input.snapshot())


@router.post("/api/ui-event")
async def ui_event(payload: dict):
    """V2-039 — AUDIT of what happens in the frontend, on the SAME timeline as FlashBrain and worker orders. Two
    different things enter here and are distinguished by `src`:

    - **`src="user"`** (default): what the operator DOES — taps on orb/TopBar icons (kind="ui") and manual widget
      geometry (move/resize, kind="widget").
    - **`src="frontend"`** (2026-08-10): STATE TRANSITIONS from the client itself — the agent moves to
      `live`/`stalled`, the mic analyzer opens/releases, the bot audio track attaches/detaches, the tab goes to the
      background. They are not activity, they are state: few events and only when something really changes. Without
      them, a DOWN agent painted as live, a zombie speaker, or a mic that is not released leave no line at all (the
      log only had the operator INTENTION, `orb:power`, not reality).

    Best-effort: this can never break the frontend reporting it."""
    kind = str((payload or {}).get("kind") or "ui")
    if kind not in ("ui", "widget"):
        kind = "ui"
    label = str((payload or {}).get("action") or (payload or {}).get("label") or "")[:60]
    src = str((payload or {}).get("src") or "user")
    extra = {"src": src if src in ("user", "frontend") else "user"}
    wid = (payload or {}).get("id")
    if wid:
        extra["id"] = str(wid).split("::", 1)[0].strip().lower()
    # `prev`/`reason`/`cause` make a transition READABLE: which state it came from and why it moved. Without them,
    # `agent:state stalled` does not say whether we came from `live` (it fell) or from `starting` (it never came up).
    for k in ("where", "state", "detail", "prev", "reason", "cause"):
        v = (payload or {}).get(k)
        if v is not None:
            extra[k] = str(v)[:120]
    return JSONResponse(emit(kind, label, extra=extra))


def open_instances() -> list[str]:
    """The OPEN cards with their FULL id (`results::t7`), exactly as reported by the canvas.

    V2-259 F3 — `memory.state()["open_widgets"]` stores the NORMALIZED set (base ids), which is correct for
    its purpose: the brain's state talks about PIECES. But “close the results” with two sheets open is a
    question about CARDS, and normalization erases exactly the data needed there — the same collapse that
    V2-047 F9 documented and that had only been instrumented until now.

    This is PROCESS state, not persisted, and that is fine: the canvas is authoritative and reports on every change,
    so this is the freshest information available on the server side. After a restart it remains empty until the
    first report, and an empty list means “I don't know” — the caller then falls back to the usual behavior instead
    of inventing an ambiguity.
    """
    return list(getattr(canvas_state, "_last_inst", None) or [])


@router.get("/api/energy")
async def energy():
    """The account Energy balance, for the top-bar BATTERY. Read-only, no-cache.

    Returns FACTS (balance, starting amount, whether this installation has a cloud account) and NOT the drawing
    scale: how many slots the battery has, how much each tick is worth, and which color it uses are PRESENTATION
    decisions that live in the frontend (`EnergyGauge.js`). That way the server does not need to know about colors
    and the scale can change without touching Python.

    On self-host it returns `cloud:false` and the frontend renders nothing: there is no balance to spend."""
    try:
        from nucleo import energy_lease, energy_meter
        # The LEASE travels alongside the balance because they are the same question seen at two distances: the
        # balance is what the ACCOUNT has left, while the lease is what THIS machine may spend before asking again.
        # With the link down, only the second one is a locally verifiable fact.
        return JSONResponse({**energy_meter.snapshot(), "lease": energy_lease.snapshot()},
                            headers={"Cache-Control": "no-cache"})
    except Exception:
        return JSONResponse({"cloud": False, "known": False}, headers={"Cache-Control": "no-cache"})


@router.post("/api/workers/pause")
async def workers_pause():
    """V2-065 (operator ⏻ button): freezes live Brain Workers WITHOUT killing them (SIGSTOP to the backend) — unlike
    /reset/hard, this is reversible with /api/workers/resume. Voice/mic are stopped by `session.stop()` on the
    client; this endpoint freezes what was already working in the background."""
    try:
        from nucleo import dispatch
        return JSONResponse({"ok": True, "paused": dispatch.pause_all()})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/workers/resume")
async def workers_resume():
    """Resume (SIGCONT) the workers that /api/workers/pause left frozen. They continue exactly where they were — no
    restart."""
    try:
        from nucleo import dispatch
        return JSONResponse({"ok": True, "resumed": dispatch.resume_all()})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/api/run")
async def run_get():
    """V2-092: is the agent RUNNING or STOPPED? The server owns the truth (`nucleo/runstate.py`), not browser
    `localStorage` — the frontend seeds from here on boot, so reloading the page (or opening it in another browser)
    inherits the real state instead of resurrecting an agent the operator had stopped."""
    from nucleo import runstate
    return JSONResponse(runstate.snapshot(), headers={"Cache-Control": "no-cache"})


@router.post("/api/run/stop")
async def run_stop():
    """STOP the agent: freeze Brain Workers (SIGSTOP, reversible) and SUSPEND widgets that are producing (music,
    video…). Replaces /api/workers/pause on the ⏻ button — same thing plus everything else. Returns what was frozen,
    so the operator log is not a list of intentions."""
    try:
        from nucleo import runstate
        return JSONResponse(await runstate.stop("operator"))
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/run/start")
async def run_start():
    """START the agent: frozen workers CONTINUE where they were. Widgets are deliberately NOT resumed — starting the
    music again is an operator gesture (see `nucleo/runstate.py`, "deliberate asymmetry")."""
    try:
        from nucleo import runstate
        return JSONResponse(await runstate.start("operator"))
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/api/desktop/epoch")
async def desktop_epoch():
    """Desktop WIPE epoch: `scripts/reset-memory.sh` bumps it on every wipeout. The frontend compares it with the
    value stored in localStorage and, if it is NEW, starts with an EMPTY desktop (blank session after a reset — open
    widgets live in browser localStorage, which a server-side deletion cannot reach)."""
    epoch = "0"
    try:
        _p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          ".meshkore", "logs", "desktop-epoch")
        with open(_p, encoding="utf-8") as f:
            epoch = f.read().strip() or "0"
    except Exception:
        pass
    return JSONResponse({"epoch": epoch})


def _who_asked(request: "Request | None") -> dict:
    """WHO asked for this reset — an attribution fact, kept with the event that destroys work.

    A hard reset kills live workers, cancels escalations and blanks the canvas, and the RESET event recorded
    everything about that EXCEPT who ordered it. Measured 2026-09-03 on the operator's own engine: a reset
    fired mid-errand with no `topbar:reset`, no `orb:power` and no `run/stop` in front of it — so it did not
    come from the button — and there was no way to say what did. The engine then apologised to the operator
    for closing widgets it had not chosen to close, because nothing in the prompt or the log could name the
    author. An event that records what was destroyed and not who ordered it cannot answer the only question
    asked afterwards.

    Deliberately coarse: client host and a bounded User-Agent. Enough to tell the desktop frontend from an
    automated caller (a harness sends a fixed short UA; a real browser's carries its version), and nothing
    that would turn an event log into a tracking record.
    """
    if request is None:
        return {"host": "", "ua": ""}
    try:
        return {"host": str(getattr(getattr(request, "client", None), "host", "") or ""),
                "ua": str(request.headers.get("user-agent") or "")[:120]}
    except Exception:  # noqa: BLE001 — attribution must never be the reason a reset fails
        return {"host": "", "ua": ""}


@router.post("/reset")
async def reset():
    # LIGHT reset (also used by reconnect): clears session + log. Does NOT kill background work or write memory.
    S.reset_session_state()
    clear_log()
    return JSONResponse(emit("session", "RESET"))


@router.post("/reset/hard")
async def reset_hard(request: Request = None):
    """Deliberate HARD RESET (frontend «Reset» button, after confirmation). Careful sequence: FREEZE in-flight work
    in STATE memory, leave the order RECORD in short-term memory, KILL background processes, then clear the canvas
    (close all widgets) + session + log. See `nucleo/reset.py`."""
    try:
        from nucleo import reset as _reset
        summary = _reset.reset_all()
    except Exception:  # noqa: BLE001
        summary = {"frozen": 0, "killed": {}, "error": True}
    S.reset_session_state()
    ses = rotate_session("reset")          # NEW SESSION (new id + observability reset), not just a clean log
    emit("widget", "close", extra={})      # close ALL canvas cards (frontend: desktop.closeAll())
    return JSONResponse(emit("session", "RESET", extra={"hard": True, "reset": summary, "by": _who_asked(request),
                                                        "session": ses.get("session_id", "")}))


@router.post("/api/reset/full")
async def reset_full(payload: dict | None = None, request: Request = None):
    """Reset dialog with CHECKBOXES (V2-063, operator request 2026-07-23): besides the ALWAYS base (observability +
    blank desktop, same as /reset/hard), it can optionally delete `wipe_memory` (state/short/long term — one
    "Memory" button) and/or `wipe_credentials` (WhatsApp/Telegram/browser/search). Deleting memory/credentials
    requires the process to die (SQLite in use, browser profiles open) → if EITHER is requested, an AUTOMATIC
    restart is launched in the background (`scripts/reset-memory.sh` + `make run`, detached) and `restarting:true`
    is returned BEFORE the server dies, so the frontend can show "restarting…" and reconnect only when it comes
    back. If neither is requested, it is EXACTLY `/reset/hard` (live, no restart)."""
    p = payload or {}
    wipe_memory = bool(p.get("wipe_memory"))
    wipe_credentials = bool(p.get("wipe_credentials"))
    # V2-670, the operator's «quiero inicializar un agente nuevo en otro idioma, todo de cero»:
    # `wipe_profile` is what actually makes the first-run LANGUAGE CEREMONY fire again (it empties
    # `stt_language`, the gate `i18n.init.detect.should_detect()` reads), and `wipe_files` deletes the
    # agent's own library. Both need the process dead for the same reason the other two do.
    wipe_profile = bool(p.get("wipe_profile"))
    wipe_files = bool(p.get("wipe_files"))

    # ALWAYS base (observability + desktop): same sequence as /reset/hard, live, no restart.
    try:
        from nucleo import reset as _reset
        summary = _reset.reset_all()
    except Exception:  # noqa: BLE001
        summary = {"frozen": 0, "killed": {}, "error": True}
    S.reset_session_state()
    ses = rotate_session("reset")           # NEW SESSION (new id + observability reset), not just a clean log
    emit("widget", "close", extra={})

    if not wipe_memory and not wipe_credentials and not wipe_profile and not wipe_files:
        return JSONResponse(emit("session", "RESET", extra={"hard": True, "reset": summary, "restarting": False,
                                                            "by": _who_asked(request),
                                                            "session": ses.get("session_id", "")}))

    # Memory and/or credentials: AUTOMATIC restart in a DETACHED process (survives this process dying).
    # `reset-memory.sh` stops the server itself (finds the PID by port), deletes, and bumps desktop-epoch; then we
    # relaunch with a normal `make run`, logging to a file (same pattern as manual restarts).
    import subprocess
    import time as _time
    engine_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ts = _time.strftime("%Y%m%d-%H%M%S")
    flags = (("" if wipe_memory else " --keep-memory") + (" --wipe-credentials" if wipe_credentials else "")
             + (" --factory" if wipe_profile else "") + (" --wipe-files" if wipe_files else ""))
    cmd = (
        f"sleep 1; bash scripts/reset-memory.sh --yes{flags}; "
        f"nohup make run > .meshkore/logs/run-{ts}.log 2>&1 &"
    )
    try:
        subprocess.Popen(["bash", "-c", cmd], cwd=engine_dir, start_new_session=True,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_full: no se pudo lanzar el reinicio: {e}")
        return JSONResponse({"ok": False, "error": "restart_spawn_failed"}, status_code=500)
    return JSONResponse({"ok": True, "restarting": True, "wipe_memory": wipe_memory,
                         "wipe_credentials": wipe_credentials, "wipe_profile": wipe_profile,
                         "wipe_files": wipe_files, "reset": summary})


from server import voice_status as _vstatus  # noqa: E402 — V2-778 F1, reads this module back
