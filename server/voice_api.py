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
        # STT · voz → texto — engine providers: voxtral (cloud), deepgram (cloud), whisper_local (on-machine).
        {"fn": "STT · voz → texto", "options": [
            opt("Voxtral · Mistral (cloud)", "paid·barato", has("MISTRAL_API_KEY"), stt_cur == "voxtral", "MISTRAL_API_KEY"),
            opt("Deepgram Nova-3 (cloud)", "free·tier", has("DEEPGRAM_API_KEY"), stt_cur == "deepgram", "DEEPGRAM_API_KEY"),
            opt("Whisper local (privado · gratis)", "free·local", whisper_ok, stt_cur == "whisper_local", "faster-whisper")]},
        # TTS · texto → voz — engine providers: cartesia (cloud), kokoro_local (on-machine).
        {"fn": "TTS · texto → voz", "options": [
            opt("Cartesia Sonic", "paid", has("CARTESIA_API_KEY"), tts_cur == "cartesia", "CARTESIA_API_KEY"),
            opt("Kokoro local (es/en · privado)", "free·local", kokoro_reachable, tts_cur == "kokoro_local", "Kokoro-FastAPI local")]},
        {"fn": "LLM · modelo (cerebro)", "options": [
            # Solo no-razonadores en el path de voz (regla dura): un razonador no cierra el turno → zaelar muda.
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

    # ── Servidor (FastAPI) ────────────────────────────────────────────────────────────────────────────────────
    # If this responds at all the server is up — but the operator asked to SEE it listed, so we surface it plainly.
    items.append({"key": "server", "label": "Servidor · FastAPI",
                  "state": "ok", "detail": f"en línea · puerto {os.getenv('PORT', '43917')}"})

    # ── Versión (V2-074) — qué código corre en ESTA instancia (certeza de que el reinicio cargó lo nuevo) ─────────
    try:
        import version as _ver
        _vi = _ver.info()
        _up = _vi["uptime_s"]
        _up_s = f"{_up // 3600}h {(_up % 3600) // 60}m" if _up >= 3600 else f"{_up // 60}m {_up % 60}s"
        items.append({"key": "version", "label": "Versión", "state": "ok",
                      "detail": f"{_vi['short']} · activa {_up_s}", "extra": _vi})
    except Exception as e:  # noqa: BLE001
        items.append({"key": "version", "label": "Versión", "state": "warn", "detail": f"desconocida ({e})"})

    # ── Cerebro «Colmena» ─────────────────────────────────────────────────────────────────────────────────────
    from config.v2 import active_brain
    brain = active_brain()
    _brain_detail = {"nucleo": "«Colmena» · FlashBrain + brain workers + memoria propia"}.get(brain, f"modo {brain}")
    items.append({"key": "brain", "label": "Cerebro", "state": "ok", "detail": _brain_detail})

    # ── Voice session ─────────────────────────────────────────────────────────────────────────────────────────
    try:
        live = active.count() > 0
    except Exception:
        live = False
    # Voz SIEMPRE ENCENDIDA (2026-07-07): ya no hay botón "Activar" — la sesión arranca sola al abrir la web.
    items.append({"key": "voice", "label": "Sistema de voz",
                  "state": "ok" if live else "off",
                  "detail": "sesión activa" if live else "en espera · se activa al abrir la web"})

    # ── LLM provider (the fast-layer model driving the conversation) ─────────────────────────────────────────
    # Con BRAIN=nucleo el modelo de la capa rápida es POR INVOCACIÓN (config/v2 `fast`, gestionado por la UI);
    # aquí mostramos el default configurado.
    llm_err = health_state.get("llm")
    # Proveedor + key REALES desde el ModelSpec de la capa rápida (provider-agnóstico: xAI / Groq / AIMLAPI /
    # Gemini / Ollama-local) — no hardcodear "AIMLAPI" (invariante: el estado refleja el proveedor en uso).
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
        # UN TURNO ATASCADO ≠ EL PROVEEDOR NO RESPONDE (2026-08-12). El plazo de silencio del turno registraba el
        # corte como si el modelo estuviera caído → el ◉ se quedaba ROJO con «no responde» mientras el modelo
        # contestaba perfectamente antes y después. Es un AVISO con el hecho concreto, no un diagnóstico de caída.
        state = "warn"; llm_detail += " · " + (llm_err.get("text") or "un turno se atascó")
    elif llm_err:
        state = "error"
        llm_detail += " · " + {"credit": "SIN SALDO/cuota", "auth": "credencial inválida"}.get(llm_err["kind"], "no responde")
    elif not llm_key:
        state = "warn"; llm_detail += " · falta API key"
    else:
        state = "ok"; llm_detail += " · key ✓"
    items.append({"key": "llm", "label": "Modelo LLM", "state": state, "detail": llm_detail})

    # ── Memoria · CORAZÓN de escritura (V2-066, petición del operador: sin banner, solo el ◉ de estado) ────────
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

    # ── Crons (proactividad · loop orquestador PROPIO, nucleo/) ──────────────────────────────────────────────
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

    # ── Widgets (servicio full-stack) ────────────────────────────────────────────────────────────────────────
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
    # above the fold, and SECONDARY features (proactividad, widgets, cluster) below in a quieter section.
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
    """V2-039 — AUDITORÍA de lo que pasa en el frontend, en la MISMA línea de tiempo que las órdenes del FlashBrain
    y los workers. Dos cosas distintas entran por aquí y se distinguen por `src`:

    - **`src="user"`** (por defecto): lo que HACE el operador — taps de los iconos del orbe/TopBar (kind="ui") y
      geometría de widgets a mano (mover/redimensionar, kind="widget").
    - **`src="frontend"`** (2026-08-10): TRANSICIONES DE ESTADO del propio cliente — el agente pasa a
      `live`/`stalled`, se abre o se suelta el analizador de micro, se engancha o se suelta la pista de audio del
      bot, la pestaña se va al fondo. No son actividad, son estado: pocos eventos y solo cuando algo cambia de
      verdad. Sin ellos un agente CAÍDO que se pinta vivo, un altavoz zombi o un micro que no se libera no dejan
      ni una línea (el log solo tenía la INTENCIÓN del operador, `orb:power`, no la realidad).

    Best-effort: esto nunca puede romper el frontend que lo reporta."""
    kind = str((payload or {}).get("kind") or "ui")
    if kind not in ("ui", "widget"):
        kind = "ui"
    label = str((payload or {}).get("action") or (payload or {}).get("label") or "")[:60]
    src = str((payload or {}).get("src") or "user")
    extra = {"src": src if src in ("user", "frontend") else "user"}
    wid = (payload or {}).get("id")
    if wid:
        extra["id"] = str(wid).split("::", 1)[0].strip().lower()
    # `prev`/`reason`/`cause` son los que hacen LEGIBLE una transición: de qué estado venía y por qué se movió.
    # Sin ellos, `agent:state stalled` no dice si veníamos de `live` (se ha caído) o de `starting` (no llegó a subir).
    for k in ("where", "state", "detail", "prev", "reason", "cause"):
        v = (payload or {}).get(k)
        if v is not None:
            extra[k] = str(v)[:120]
    return JSONResponse(emit(kind, label, extra=extra))


@router.post("/api/canvas/state")
async def canvas_state(payload: dict):
    """El frontend (autoritativo del canvas) reporta qué widgets tiene ABIERTOS el operador → se guarda en el
    ESTADO de la memoria (`open_widgets`), que viaja SIEMPRE en el prompt (memory_cache) y se ve en el mapa. Así el
    cerebro sabe "lo que el operador tiene delante" y resuelve "modifica el widget de X" sin preguntar. Best-effort,
    fire-and-forget desde `desktop._persist()`. Normaliza ids de instancia (navegador::t3 → navegador) y dedup."""
    raw = payload.get("open") or []
    seen: list[str] = []
    inst: list[str] = []                        # V2-047 F9: ids de INSTANCIA completos, tal cual (navegador::t1)
    for wid in raw:
        w = str(wid or "").strip()
        if w and w not in inst:
            inst.append(w)
        base = w.split("::", 1)[0].strip().lower()
        if base and base not in seen:
            seen.append(base)
    # V2-047 F9 (sesión 23:15 «dos navegadores, uno en blanco»): el set NORMALIZADO colapsa navegador::t1 y
    # navegador::t2 en un solo «navegador» → era imposible saber a posteriori si de verdad había DOS tarjetas.
    # Registramos las instancias crudas en un evento `ui` (barato, solo al cambiar el canvas) para diagnosticar.
    try:
        from voice.observer import emit as _emit_inst
        _prev_inst = getattr(canvas_state, "_last_inst", None)
        if inst != _prev_inst:
            canvas_state._last_inst = inst
            _emit_inst("ui", "canvas (instancias)", role="user",
                       extra={"instances": inst, "n": len(inst), "cat": "main"})
    except Exception:
        pass
    # V2-039 — AUDITORÍA de las órdenes del OPERADOR sobre el canvas: el frontend es autoritativo y reporta el set
    # ABIERTO en cada cambio; comparándolo con el anterior sabemos qué abrió/cerró el usuario (a mano, arrastrando o
    # con el aspa) y lo registramos en la línea de tiempo con procedencia "user" — antes eran acciones SILENCIOSAS.
    try:
        from memory import api as memory
        prev = set((memory.state() or {}).get("open_widgets") or [])
        now = set(seen)
        from voice.observer import emit
        # V2-044: una acción MANUAL del operador sobre el canvas también es un estímulo → nace con su trace
        # (origin="ui"). Contexto HTTP fresco por request — el ctxvar queda acotado solo. Solo si hay diff real.
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
        # V2-078: los que PASAN a abiertos entran al MRU `recent_widgets` (2ª capa de acotación open>reciente>
        # catálogo). Persiste tras cerrarse → "el que usé hace un momento" sigue teniendo prioridad. Único hook:
        # todo show (del operador O del cerebro vía [[show]]) re-reporta el canvas por aquí.
        if (now - prev):
            try:
                memory.note_widgets_used(sorted(now - prev))
            except Exception:
                pass
    except Exception:  # noqa: BLE001
        pass
    # REHIDRATACIÓN DEL ESCRITORIO (2026-08-12): el frontend manda además la GEOMETRÍA (qué tarjeta, dónde, con qué
    # consulta) y se guarda como RED DE SEGURIDAD del `localStorage`, que es de donde se restaura normalmente. El
    # localStorage es per-ORIGEN y per-navegador: el mismo zaelar servido en `https://local.zaelar.com:44317` y en
    # `http://localhost:43917` son dos escritorios distintos, y desde otro navegador/perfil no hay ninguno. Cuando el
    # operador cree que «se ha perdido el escritorio», casi siempre está mirando un almacén vacío que no es el suyo.
    # Va a `sys_kv` (estado de UI, NO el estado raíz que viaja en cada prompt: al cerebro no le importan las
    # coordenadas de una tarjeta). Solo se ESCRIBE aquí; quien restaura es `GET /api/canvas/layout`.
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


@router.get("/api/canvas/layout")
async def canvas_layout():
    """El escritorio TAL COMO lo dejó el operador (tarjetas + posiciones). Es el fallback de restauración cuando el
    `localStorage` del navegador no lo tiene — otro navegador, otro perfil, o el mismo zaelar por otro origen
    (localhost:43917 vs local.zaelar.com:44317, dos almacenes distintos para el mismo escritorio). Read-only."""
    try:
        from memory import api as memory
        snap = memory.kv_get("canvas_layout")
        if isinstance(snap, dict) and isinstance(snap.get("items"), list):
            return JSONResponse({"items": snap["items"], "at": snap.get("at") or 0})
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse({"items": [], "at": 0})


@router.get("/api/energy")
async def energy():
    """El saldo de Energy de la cuenta, para la PILA de la barra superior. Read-only, no-cache.

    Devuelve HECHOS (saldo, de cuánto se partía, si esta instalación tiene cuenta de nube) y NO la escala con la
    que se dibuja: cuántos huecos tiene la pila, cuánto vale cada rayita y de qué color es son decisiones de
    PRESENTACIÓN y viven en el frontend (`EnergyGauge.js`). Así el servidor no tiene que saber nada de colores y
    la escala se puede cambiar sin tocar Python.

    En self-host devuelve `cloud:false` y el frontend no pinta nada: no hay saldo que gastar."""
    try:
        from nucleo import energy_meter
        return JSONResponse(energy_meter.snapshot(), headers={"Cache-Control": "no-cache"})
    except Exception:
        return JSONResponse({"cloud": False, "known": False}, headers={"Cache-Control": "no-cache"})


@router.get("/api/tasks")
async def tasks():
    """Sesiones de Brain Workers VIVAS ahora — lee el REGISTRO EN RAM de dispatch (la FUENTE DE VERDAD, §v2·C),
    no el ESTADO proyectado. El frontend RECONCILIA sus chips contra esto al (re)conectar → fin de los chips
    huérfanos (V2-038). Read-only, no-cache."""
    try:
        from nucleo import dispatch
        return JSONResponse({"sessions": dispatch.active_sessions()},
                            headers={"Cache-Control": "no-cache"})
    except Exception:
        return JSONResponse({"sessions": []}, headers={"Cache-Control": "no-cache"})


@router.get("/api/workers/history")
async def workers_history():
    """V2-079: HISTÓRICO de Brain Workers TERMINADOS (ledger durable) — para la pestaña «Procesos» del ChatWall,
    que da PERSPECTIVA de lo hecho hoy/ayer/hace días (los vivos van por /api/tasks). Read-only, no-cache."""
    try:
        from nucleo.workers import ledger
        return JSONResponse({"history": ledger.history()}, headers={"Cache-Control": "no-cache"})
    except Exception:
        return JSONResponse({"history": []}, headers={"Cache-Control": "no-cache"})


@router.post("/api/workers/pause")
async def workers_pause():
    """V2-065 (botón ⏻ del operador): congela los Brain Workers vivos SIN matarlos (SIGSTOP al backend) — a
    diferencia de /reset/hard, esto es reversible con /api/workers/resume. Voz/mic los apaga `session.stop()` en
    el cliente; este endpoint congela lo que ya estaba trabajando en segundo plano."""
    try:
        from nucleo import dispatch
        return JSONResponse({"ok": True, "paused": dispatch.pause_all()})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/workers/resume")
async def workers_resume():
    """Reanuda (SIGCONT) los workers que /api/workers/pause dejó congelados. Continúan exactamente donde
    estaban — no reinicia nada."""
    try:
        from nucleo import dispatch
        return JSONResponse({"ok": True, "resumed": dispatch.resume_all()})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/api/run")
async def run_get():
    """V2-092: ¿está el agente EN MARCHA o PARADO? La verdad la tiene el servidor (`nucleo/runstate.py`), no el
    `localStorage` del navegador — el frontend siembra de aquí al arrancar, así que recargar la página (o abrirla en
    otro navegador) hereda el estado real en vez de resucitar un agente que el operador había parado."""
    from nucleo import runstate
    return JSONResponse(runstate.snapshot(), headers={"Cache-Control": "no-cache"})


@router.post("/api/run/stop")
async def run_stop():
    """PARA el agente: congela los Brain Workers (SIGSTOP, reversible) y SUSPENDE los widgets que estén
    produciendo (música, vídeo…). Sustituye a /api/workers/pause en el botón ⏻ — hace lo mismo y además todo lo
    demás. Devuelve qué se congeló, para que el log del operador no sea una lista de intenciones."""
    try:
        from nucleo import runstate
        return JSONResponse(await runstate.stop("operator"))
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/run/start")
async def run_start():
    """ARRANCA el agente: los workers congelados CONTINÚAN donde estaban. Los widgets NO se reanudan a propósito —
    volver a poner la música es un gesto del operador (ver `nucleo/runstate.py`, «asimetría deliberada»)."""
    try:
        from nucleo import runstate
        return JSONResponse(await runstate.start("operator"))
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/api/desktop/epoch")
async def desktop_epoch():
    """Época de WIPE del escritorio: `scripts/reset-memory.sh` la bumpea en cada wipeout. El frontend la compara con
    la que guardó en localStorage y, si es NUEVA, arranca con el escritorio VACÍO (sesión en blanco tras un reset —
    los widgets abiertos viven en el localStorage del navegador, que un borrado de servidor no alcanza)."""
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
    # Reset LIGERO (lo usa también el reconnect): limpia sesión + log. NO mata trabajo de fondo ni escribe memoria.
    S.reset_session_state()
    clear_log()
    return JSONResponse(emit("session", "RESET"))


@router.post("/reset/hard")
async def reset_hard():
    """HARD RESET deliberado (botón «Reset» del frontend, tras confirmación). Secuencia cautelosa: CONGELA el
    trabajo en curso en la memoria de ESTADO, deja el REGISTRO de la orden en CORTO plazo, MATA los procesos de
    fondo, y luego limpia el canvas (cierra todos los widgets) + la sesión + el log. Ver `nucleo/reset.py`."""
    try:
        from nucleo import reset as _reset
        summary = _reset.reset_all()
    except Exception:  # noqa: BLE001
        summary = {"frozen": 0, "killed": {}, "error": True}
    S.reset_session_state()
    ses = rotate_session("reset")          # SESIÓN NUEVA (id nuevo + observabilidad a cero), no solo log limpio
    emit("widget", "close", extra={})      # cierra TODAS las tarjetas del canvas (frontend: desktop.closeAll())
    return JSONResponse(emit("session", "RESET", extra={"hard": True, "reset": summary,
                                                        "session": ses.get("session_id", "")}))


@router.post("/api/reset/full")
async def reset_full(payload: dict | None = None):
    """Diálogo de Reset con CHECKBOXES (V2-063, petición del operador 2026-07-23): además de la base de
    SIEMPRE (observabilidad + escritorio en blanco, igual que /reset/hard), permite borrar opcionalmente
    `wipe_memory` (state/corto/largo plazo — un solo botón "Memoria") y/o `wipe_credentials` (WhatsApp/Telegram/
    navegador/búsqueda). Borrar memoria/credenciales exige que el proceso muera (SQLite en uso, perfiles de
    navegador abiertos) → si se pide CUALQUIERA de los dos, se lanza un reinicio AUTOMÁTICO en segundo plano
    (`scripts/reset-memory.sh` + `make run`, detached) y se responde `restarting:true` ANTES de que el server
    muera, para que el frontend pueda mostrar "reiniciando…" y reconectar solo cuando vuelva. Sin ninguna de las
    dos, es EXACTAMENTE `/reset/hard` (live, sin reinicio)."""
    p = payload or {}
    wipe_memory = bool(p.get("wipe_memory"))
    wipe_credentials = bool(p.get("wipe_credentials"))

    # Base SIEMPRE (observabilidad + escritorio): la misma secuencia que /reset/hard, live, sin reinicio.
    try:
        from nucleo import reset as _reset
        summary = _reset.reset_all()
    except Exception:  # noqa: BLE001
        summary = {"frozen": 0, "killed": {}, "error": True}
    S.reset_session_state()
    ses = rotate_session("reset")           # SESIÓN NUEVA (id nuevo + observabilidad a cero), no solo log limpio
    emit("widget", "close", extra={})

    if not wipe_memory and not wipe_credentials:
        return JSONResponse(emit("session", "RESET", extra={"hard": True, "reset": summary, "restarting": False,
                                                            "session": ses.get("session_id", "")}))

    # Memoria y/o credenciales: reinicio AUTOMÁTICO en un proceso DETACHED (sobrevive a que este muera).
    # `reset-memory.sh` para el server él mismo (busca el PID por puerto), borra, y bumpea desktop-epoch; tras
    # eso relanzamos con un `make run` normal, con log a fichero (mismo patrón que los reinicios manuales).
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
