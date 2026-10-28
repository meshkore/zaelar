"""Voice HTTP API (LiveKit engine).

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

from . import reset_api as _reset_api
from . import run_api as _run_api
from . import state as S
from .canvas_api import (  # noqa: E402,F401 — V2-778 F1: moved, imported back under their names
    _live_canvas_instances, _prune_ghost_sheets, _sheet_ids_on_disk, canvas_arrange, canvas_layout, canvas_state)

router = APIRouter()
router.include_router(_run_api.router)      # /api/run*, /api/workers/*, /api/energy, /api/desktop/epoch
router.include_router(_reset_api.router)    # /reset, /reset/hard, /api/reset/full


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
    # TODO: audition a voice over the LiveKit TTS plugins (Cartesia/Kokoro) without spinning up a full
    # AgentSession — e.g. call the plugin's synthesize() into an in-memory buffer and return it as audio.
    return JSONResponse(
        {"error": "audición de voz no disponible aún en el motor LiveKit"},
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
async def events(dev: str = ""):
    # V2-792 — the stream says WHICH SCREEN it feeds (`?dev=`, the frontend's `api.js::DEVICE`). It is how the server
    # knows a second screen is open; the events themselves stay the same for every surface (each one filters).
    from voice import screens as _screens
    q = subscribe()

    async def gen():
        _screens.attach(dev)          # inside the generator, so the `finally` that detaches is guaranteed to pair it
        try:
            yield f"data: {json.dumps({'kind':'session','label':'SSE','voice_dev':_screens.holder()})}\n\n"
            try:
                from nucleo import notices as _notices   # V2-796: what no channel could take is shown here
                _notices.drain_to_screen(dev)
            except Exception as e:  # noqa: BLE001 — a ledger hiccup never costs the stream
                logger.warning(f"events: owed notices not drained: {e!r}")
            while True:
                ev = await q.get()
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            unsubscribe(q)
            _screens.detach(dev)

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

    # A network error is re-checked against the network before anything reads it (see `nucleo/net_probe.py`).
    try:
        from nucleo import net_probe
        await asyncio.to_thread(health_state.revalidate_network, net_probe.back)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"status: network revalidation skipped: {e}")

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
                             ("device", "muted", "enabled", "state", "rms", "raw", "dev") if k in payload}))


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
    dev = str((payload or {}).get("dev") or "")[:40]
    from server.livekit_api import speaks_for_the_mic
    if not speaks_for_the_mic(dev):
        return JSONResponse({"ok": True, "muted": mic_input.is_muted(), "ignored": "not_the_voice_holder"})
    return JSONResponse(mic_input.set_muted(muted, source=src, dev=dev))


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
    for k in ("where", "state", "detail", "prev", "reason", "cause", "dev"):
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

from server import voice_status as _vstatus  # noqa: E402 — V2-778 F1, reads this module back
