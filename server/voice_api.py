"""Voice HTTP API (LiveKit engine, INI-012).

The WebRTC transport, ICE/TURN negotiation and the audio pipeline are owned by the LiveKit engine now
(voice/engine/ + the embedded worker + server/livekit_api.py). This module keeps only the engine-agnostic
HTTP surface the front still needs: user name, the SSE event stream (observer), debug/status/providers panels,
the ⚙ settings + voice catalog, and client-log ingestion. No Pipecat, no /api/offer, no /api/ice-servers.
"""
import json
import os
import time

from fastapi import APIRouter
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

    items = []

    # ── Server (FastAPI) ──────────────────────────────────────────────────────────────────────────────────────
    # If this responds at all the server is up — but the operator asked to SEE it listed, so we surface it plainly.
    items.append({"key": "server", "label": "Servidor · FastAPI",
                  "state": "ok", "detail": f"en línea · puerto {os.getenv('PORT', '43917')}"})

    # ── Version (V2-074) — which code runs on THIS instance (certainty that restart loaded the new code) ──────
    try:
        import version as _ver
        _vi = _ver.info()
        _up = _vi["uptime_s"]
        _up_s = f"{_up // 3600}h {(_up % 3600) // 60}m" if _up >= 3600 else f"{_up // 60}m {_up % 60}s"
        items.append({"key": "version", "label": "Versión", "state": "ok",
                      "detail": f"{_vi['short']} · activa {_up_s}", "extra": _vi})
    except Exception as e:  # noqa: BLE001
        items.append({"key": "version", "label": "Versión", "state": "warn", "detail": f"desconocida ({e})"})

    # ── «Colmena» brain ───────────────────────────────────────────────────────────────────────────────────────
    from config.v2 import active_brain
    brain = active_brain()
    _brain_detail = {"nucleo": "«Colmena» · FlashBrain + brain workers + memoria propia"}.get(brain, f"modo {brain}")
    items.append({"key": "brain", "label": "Cerebro", "state": "ok", "detail": _brain_detail})

    # ── Voice session ─────────────────────────────────────────────────────────────────────────────────────────
    try:
        live = active.count() > 0
    except Exception:
        live = False
    # Voice ALWAYS ON (2026-07-07): there is no longer an "Activate" button — the session starts when the web opens.
    items.append({"key": "voice", "label": "Sistema de voz",
                  "state": "ok" if live else "off",
                  "detail": "sesión activa" if live else "en espera · se activa al abrir la web"})

    # ── LLM provider (the fast-layer model driving the conversation) ─────────────────────────────────────────
    # With BRAIN=nucleo, the fast-layer model is PER INVOCATION (config/v2 `fast`, UI-managed); here we show the
    # configured default.
    llm_err = health_state.get("llm")
    # REAL provider + key from the fast-layer ModelSpec (provider-agnostic: xAI / Groq / AIMLAPI / Gemini /
    # Ollama-local) — do not hardcode "AIMLAPI" (invariant: status reflects the provider in use).
    prov_label = "nube"; llm_key = True; model_name = SETTINGS.llm_model or os.getenv("LLM_MODEL", "?")
    if brain == "nucleo":
        try:
            from nucleo.flash.fast_client import spec_from_config
            _spec = spec_from_config()
            model_name = _spec.model or model_name
            _url = _spec.resolved_base_url().lower()
            prov_label = ("Ollama·local" if _spec.is_local() else "xAI" if "x.ai" in _url
                          else "Groq" if "groq" in _url else "Gemini" if "googleapis" in _url or "generativelanguage" in _url
                          else "AIMLAPI" if "aimlapi" in _url else "nube")
            llm_key = _spec.is_local() or bool(_spec.resolved_api_key())
        except Exception:
            prov_label = "nube"
    else:
        llm_key = has("AIMLAPI_KEY", "LLM_API_KEY")
    llm_detail = f"{model_name} · {prov_label}"
    if llm_err and llm_err.get("kind") == "slow":
        # ONE STUCK TURN ≠ PROVIDER NOT RESPONDING (2026-08-12). The turn silence deadline recorded the cut as if
        # the model were down → the ◉ stayed RED with "not responding" while the model answered perfectly before
        # and after. This is a WARNING with the concrete fact, not an outage diagnosis.
        state = "warn"; llm_detail += " · " + (llm_err.get("text") or "un turno se atascó")
    elif llm_err:
        state = "error"
        llm_detail += " · " + {"credit": "SIN SALDO/cuota", "auth": "credencial inválida"}.get(llm_err["kind"], "no responde")
    elif not llm_key:
        state = "warn"; llm_detail += " · falta API key"
    else:
        state = "ok"; llm_detail += " · key ✓"
    items.append({"key": "llm", "label": "Modelo LLM", "state": state, "detail": llm_detail})

    # ── Memory · write HEART (V2-066, operator request: no banner, only the status ◉) ─────────────────────────
    try:
        from nucleo import mem_processor
        _mp = mem_processor.status()
        mem_err = health_state.get("memory")
        if mem_err or _mp.get("degraded"):
            mem_state = "error"
            mem_detail = f"{_mp['model']} · {_mp['fail_streak']} fallos — escribiendo por heurística"
        elif _mp.get("fail_streak"):
            mem_state, mem_detail = "warn", f"{_mp['model']} · {_mp['fail_streak']} fallo(s) recientes"
        else:
            mem_state, mem_detail = "ok", f"{_mp['model']}"
        items.append({"key": "memory", "label": "Memoria · CORAZÓN", "state": mem_state, "detail": mem_detail})
    except Exception:
        items.append({"key": "memory", "label": "Memoria · CORAZÓN", "state": "warn", "detail": "no disponible"})

    # ── STT / TTS (from the LiveKit engine SETTINGS) ─────────────────────────────────────────────────────────
    stt_prov = SETTINGS.stt_provider
    stt_err = health_state.get("stt")
    stt_needs = {"voxtral": "MISTRAL_API_KEY", "deepgram": "DEEPGRAM_API_KEY"}.get(stt_prov)
    if stt_err:
        stt_state, stt_detail = "error", f"{stt_prov} · {stt_err['kind']}"
    elif stt_needs and not has(stt_needs):
        stt_state, stt_detail = "warn", f"{stt_prov} · falta {stt_needs}"
    else:
        stt_state, stt_detail = "ok", f"{stt_prov}" + (" · key ✓" if stt_needs else " · local/gratis")
    items.append({"key": "stt", "label": "STT · voz→texto", "state": stt_state, "detail": stt_detail})

    try:
        from voice.engine.speech.voices import tts_provider, voices_for
        prov = tts_provider()   # catalog key (kokoro_local → kokoro)
        vs = voices_for(prov)
        cur = vs[int(S.STATE.get("voice", 0)) % len(vs)]["label"]
    except Exception:
        prov, cur = SETTINGS.tts_provider, "?"
    tts_err = health_state.get("tts")
    needs_key = {"cartesia": "CARTESIA_API_KEY"}.get(prov)
    if tts_err:
        tts_state, tts_detail = "error", f"{prov} · {tts_err['kind']}"
    elif needs_key and not has(needs_key):
        tts_state, tts_detail = "warn", f"{prov} · falta {needs_key}"
    else:
        tts_state, tts_detail = "ok", f"{prov} · {cur}"
    items.append({"key": "tts", "label": "TTS · texto→voz", "state": tts_state, "detail": tts_detail})

    # ── Crons (proactivity · OWN orchestrator loop, nucleo/) ─────────────────────────────────────────────────
    if brain == "nucleo":
        try:
            from nucleo import loop as nucleo_loop
            from nucleo import scheduler
            running = nucleo_loop.is_running()
            n = len(scheduler.list_jobs(active_only=True))
            cron_detail = (f"loop activo · {n} tarea{'s' if n != 1 else ''} programada{'s' if n != 1 else ''}"
                           if running else "loop detenido")
            items.append({"key": "cron", "label": "Crons · proactividad",
                          "state": "ok" if running else "warn", "detail": cron_detail})
        except Exception:
            items.append({"key": "cron", "label": "Crons · proactividad", "state": "warn", "detail": "no disponible"})

    # ── Widgets (full-stack service) ─────────────────────────────────────────────────────────────────────────
    try:
        from widgets import runtime as widgets_runtime
        wcount = len(widgets_runtime.catalog())
        items.append({"key": "widgets", "label": "Widgets",
                      "state": "ok", "detail": f"{wcount} disponible" + ("s" if wcount != 1 else "")})
    except Exception:
        items.append({"key": "widgets", "label": "Widgets", "state": "off", "detail": "sin catálogo"})

    # ── MeshKore cluster ─────────────────────────────────────────────────────────────────────────────────────
    try:
        from connectors import meshkore
        clusters = meshkore.get_manager().clusters()
    except Exception:
        clusters = []
    if clusters:
        conn = [c for c in clusters if c.get("connected")]
        online = sum(len(c.get("online", []) or []) for c in conn)
        cl_detail = ", ".join(f"{c['name']}·{'/'.join(c.get('online') or []) or 'sin peers'}" for c in conn) or "sin conexión"
        items.append({"key": "cluster", "label": "Cluster MeshKore",
                      "state": "ok" if conn else "off", "detail": cl_detail})
    else:
        items.append({"key": "cluster", "label": "Cluster MeshKore", "state": "off", "detail": "sin clusters"})

    # Group items so the panel can show the CORE (what you boot from the terminal — must be up for zaelar to work)
    # above the fold, and SECONDARY features (proactivity, widgets, cluster) below in a quieter section.
    CORE = {"server", "brain", "voice", "llm", "memory", "stt", "tts"}
    for it in items:
        it["group"] = "core" if it["key"] in CORE else "extra"

    rank = {"error": 3, "warn": 2, "off": 0, "ok": 1}
    worst = max((it["state"] for it in items), key=lambda s: rank.get(s, 0))
    overall = "error" if worst == "error" else "warn" if worst == "warn" else "ok"
    return JSONResponse({"overall": overall, "items": items})


@router.get("/api/settings")
async def get_settings():
    """The ⚙ config panel: current values + option lists for the swappable knobs (STT/TTS/voice/idioma/cerebro)."""
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


@router.post("/api/canvas/state")
async def canvas_state(payload: dict):
    """The frontend (authoritative for the canvas) reports which widgets the operator has OPEN → stored in memory
    STATE (`open_widgets`), which ALWAYS travels in the prompt (memory_cache) and appears in the map. This lets the
    brain know "what the operator has in front of them" and resolve "modify the X widget" without asking.
    Best-effort, fire-and-forget from `desktop._persist()`. Normalizes instance ids (navegador::t3 → navegador)
    and dedupes."""
    raw = payload.get("open") or []
    seen: list[str] = []
    inst: list[str] = []                        # V2-047 F9: full INSTANCE ids, as-is (navegador::t1)
    for wid in raw:
        w = str(wid or "").strip()
        if w and w not in inst:
            inst.append(w)
        base = w.split("::", 1)[0].strip().lower()
        if base and base not in seen:
            seen.append(base)
    # V2-047 F9 (23:15 session, "two browsers, one blank"): the NORMALIZED set collapses navegador::t1 and
    # navegador::t2 into one "navegador" → it was impossible afterwards to know whether there were really TWO
    # cards. Record raw instances in a `ui` event (cheap, only when the canvas changes) for diagnostics.
    try:
        from voice.observer import emit as _emit_inst
        _prev_inst = getattr(canvas_state, "_last_inst", None)
        canvas_state._last_inst = inst          # V2-259 F3: ALWAYS, not only when it changes — see open_instances()
        if inst != _prev_inst:
            _emit_inst("ui", "canvas (instancias)", role="user",
                       extra={"instances": inst, "n": len(inst), "cat": "main"})
    except Exception:
        pass
    # V2-039 — AUDIT of the OPERATOR's canvas orders: the frontend is authoritative and reports the OPEN set on each
    # change; comparing it with the previous set tells us what the user opened/closed (manually, by dragging, or via
    # the close button), and we record it on the timeline with "user" provenance — these used to be SILENT actions.
    try:
        from memory import api as memory
        prev = set((memory.state() or {}).get("open_widgets") or [])
        now = set(seen)
        from voice.observer import emit
        # V2-044: a MANUAL operator action on the canvas is also a stimulus → it gets its trace (origin="ui").
        # Fresh HTTP context per request — the ctxvar remains scoped by itself. Only when there is a real diff.
        if (now - prev) or (prev - now):
            try:
                from voice import trace as _trace
                _delta = [f"+{w}" for w in sorted(now - prev)] + [f"−{w}" for w in sorted(prev - now)]
                _trace.begin("canvas: " + " ".join(_delta), origin="ui")
            except Exception:
                pass
        for wid in (now - prev):
            emit("widget", "show", extra={"id": wid, "src": "user"})
        for wid in (prev - now):
            emit("widget", "close", extra={"id": wid, "src": "user"})
        memory.set_state({"open_widgets": seen})
        # V2-078: widgets that BECOME open enter the `recent_widgets` MRU (2nd scoping layer open>recent>catalog).
        # It persists after closing → "the one I used a moment ago" still has priority. Single hook: every show
        # (from the operator OR the brain via [[show]]) re-reports the canvas here.
        if (now - prev):
            try:
                memory.note_widgets_used(sorted(now - prev))
            except Exception:
                pass
    except Exception:  # noqa: BLE001
        pass
    # DESKTOP REHYDRATION (2026-08-12): the frontend also sends GEOMETRY (which card, where, with which query) and
    # it is saved as a SAFETY NET for `localStorage`, which is where restoration normally comes from. localStorage is
    # per-ORIGIN and per-browser: the same zaelar served at `https://local.zaelar.com:44317` and
    # `http://localhost:43917` are two different desktops, and another browser/profile has none. When the operator
    # thinks "the desktop was lost", they are almost always looking at an empty store that is not theirs. It goes to
    # `sys_kv` (UI state, NOT the root state that travels in every prompt: the brain does not care about a card's
    # coordinates). It is only WRITTEN here; `GET /api/canvas/layout` restores it.
    try:
        items = (payload or {}).get("layout")
        if isinstance(items, list):
            from memory import api as memory
            clean = []
            for it in items[:40]:
                if not isinstance(it, dict) or not str(it.get("id") or "").strip():
                    continue
                clean.append({k: str(it.get(k) or "")[:120] for k in ("id", "q", "left", "top", "z")})
            memory.kv_set("canvas_layout", {"at": time.time(), "items": clean})
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse({"ok": True, "open_widgets": seen})


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


def _live_canvas_instances() -> list:
    """The instance cards of work running RIGHT NOW (V2-351): the sheet of every live errand whose surface is
    the results sheet, plus every browser-tab card the server holds. This is what a refresh must put back even
    when the saved desktop never knew them — the card opened while the page was closed, or another browser did
    the work. Best-effort by construction: an empty list means «no sé», and the restore falls back to the saved
    desktop alone."""
    out: list = []
    try:
        from nucleo import dispatch as _d
        from nucleo import sheets as _sh
        from widgets.results import data as _rd
        for r in _d._sheet_sessions():
            sid = _sh.sheet_of(r)
            if sid:
                out.append(_rd.instance_id(sid))
    except Exception:  # noqa: BLE001
        pass
    try:
        from widgets.navegador import tasks as _t
        for tid in _t.all_ids():
            out.append(_t.inst_id(tid))
    except Exception:  # noqa: BLE001
        pass
    seen: list = []
    for i in out:
        if i and i not in seen:
            seen.append(i)
    return seen


@router.post("/api/canvas/arrange")
async def canvas_arrange():
    """Aligns every open card into a grid — the OS-style window snap, invocable by API (V2-464).

    The frontend does the geometry (it is the canvas authority, V2-035); this only broadcasts the ORDER over
    the same SSE rail every other canvas command travels. Exists for the use-case recorder (a video where the
    cards land tidy without a hand on the mouse) and for anything else that can POST — the operator asked for
    it by analogy with the desktop-arrange gesture of macOS/Windows."""
    return JSONResponse(emit("widget", "arrange", extra={"src": "api"}))


@router.get("/api/canvas/layout")
async def canvas_layout():
    """The desktop AS the operator left it (cards + positions) PLUS `live`, the instance cards of errands
    running right now (V2-351). Restoration fallback when browser `localStorage` does not have it — another
    browser, another profile, or the same zaelar through another origin (localhost:43917 vs
    local.zaelar.com:44317, two distinct stores for the same desktop). Read-only."""
    live = _live_canvas_instances()
    try:
        from memory import api as memory
        snap = memory.kv_get("canvas_layout")
        if isinstance(snap, dict) and isinstance(snap.get("items"), list):
            return JSONResponse({"items": snap["items"], "at": snap.get("at") or 0, "live": live})
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse({"items": [], "at": 0, "live": live})


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


@router.get("/api/tasks")
async def tasks():
    """Brain Worker sessions LIVE now — reads dispatch's IN-MEMORY REGISTRY (the SOURCE OF TRUTH, §v2·C), not the
    projected STATE. The frontend RECONCILES its chips against this on (re)connect → no more orphan chips (V2-038).
    Read-only, no-cache."""
    try:
        from nucleo import dispatch
        return JSONResponse({"sessions": dispatch.active_sessions()},
                            headers={"Cache-Control": "no-cache"})
    except Exception:
        return JSONResponse({"sessions": []}, headers={"Cache-Control": "no-cache"})


@router.get("/api/workers/history")
async def workers_history():
    """V2-079: HISTORY of FINISHED Brain Workers (durable ledger) — for the ChatWall «Processes» tab, which gives
    PERSPECTIVE on what was done today/yesterday/days ago (live ones go through /api/tasks). Read-only, no-cache."""
    try:
        from nucleo.workers import ledger
        return JSONResponse({"history": ledger.history()}, headers={"Cache-Control": "no-cache"})
    except Exception:
        return JSONResponse({"history": []}, headers={"Cache-Control": "no-cache"})


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


@router.post("/reset")
async def reset():
    # LIGHT reset (also used by reconnect): clears session + log. Does NOT kill background work or write memory.
    S.reset_session_state()
    clear_log()
    return JSONResponse(emit("session", "RESET"))


@router.post("/reset/hard")
async def reset_hard():
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
    return JSONResponse(emit("session", "RESET", extra={"hard": True, "reset": summary,
                                                        "session": ses.get("session_id", "")}))


@router.post("/api/reset/full")
async def reset_full(payload: dict | None = None):
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

    # ALWAYS base (observability + desktop): same sequence as /reset/hard, live, no restart.
    try:
        from nucleo import reset as _reset
        summary = _reset.reset_all()
    except Exception:  # noqa: BLE001
        summary = {"frozen": 0, "killed": {}, "error": True}
    S.reset_session_state()
    ses = rotate_session("reset")           # NEW SESSION (new id + observability reset), not just a clean log
    emit("widget", "close", extra={})

    if not wipe_memory and not wipe_credentials:
        return JSONResponse(emit("session", "RESET", extra={"hard": True, "reset": summary, "restarting": False,
                                                            "session": ses.get("session_id", "")}))

    # Memory and/or credentials: AUTOMATIC restart in a DETACHED process (survives this process dying).
    # `reset-memory.sh` stops the server itself (finds the PID by port), deletes, and bumps desktop-epoch; then we
    # relaunch with a normal `make run`, logging to a file (same pattern as manual restarts).
    import subprocess
    import time as _time
    engine_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ts = _time.strftime("%Y%m%d-%H%M%S")
    flags = ("" if wipe_memory else " --keep-memory") + (" --wipe-credentials" if wipe_credentials else "")
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
                         "wipe_credentials": wipe_credentials, "reset": summary})
