"""LiveKit Agents worker — assembles the voice pipeline.

Wires the isolated component families (core + llm + speech) into one
``AgentSession`` and lets LiveKit own streaming, sessions, sync, interruptions
and orchestration. On top it adds ONLY observers: the 5-state machine and the
debug bus (per-session logs + live contract messages to the UI). The engine
(STT/LLM/TTS/VAD/turn) is untouched.

zaelar (INI-012): the engine runs EMBEDDED in the zaelar web server process.
``make_server()`` returns an ``AgentServer`` with ``job_executor_type=THREAD`` so
the voice job runs in a thread of THIS process and can share state with the brain.

Run standalone (debug worker):
    python -m voice.engine.pipeline.agent dev
    python -m voice.engine.pipeline.agent download-files
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobExecutorType,
    JobProcess,
    JobRequest,
    cli,
)

from ..core import langs
from ..core.config import SETTINGS
from ..core.logging import setup_console_logging
from ..core.state import State, StateMachine
from ..llm import build_llm
from ..speech import build_stt, build_tts, build_turn_detection, build_vad
from .instrument import BootChannel, tapped_vad

logger = logging.getLogger("zaelar.agent")


def prewarm(proc: JobProcess) -> None:
    """Load heavy local models once per worker process, BEFORE a job is assigned.

    With ``num_idle_processes>=1`` the worker keeps a fully-warm executor waiting
    (this runs there), so a session connects and the agent joins fast instead of
    paying the ~6s cold start (VAD + Whisper model load + Ollama) on the first turn.

    CONFIRMED WORKING (2026-07-08, INI-013): this runs in the ``job_thread_runner``
    thread of THIS process (THREAD executor); the very session that connects reuses
    THIS proc's ``userdata`` (``entrypoint`` reports ``vad_hit/stt_hit/tts_hit=True``).
    An earlier note claimed "prewarm never fires" — that was a FALSE NEGATIVE: the
    confirmation was ``logger.info`` but, in the job thread, the root logger has no
    handler yet (``entrypoint`` sets it up later), so Python's WARNING-level lastResort
    handler swallowed it. We now call ``setup_console_logging()`` FIRST so the confirmation
    is visible in the zaelar log, and this misdiagnosis can't recur.
    """
    setup_console_logging()  # make this thread's INFO logs visible (see docstring)
    logger.info("prewarm() START — warming VAD/STT/TTS(+Ollama) in the idle executor")
    proc.userdata["vad"] = build_vad()
    # Pre-build the STT so the Whisper model loads here (idle executor), not on the
    # first turn of each session. Reused verbatim in entrypoint.
    try:
        proc.userdata["stt"] = build_stt(vad=proc.userdata["vad"])
    except Exception as e:  # noqa: BLE001
        logger.warning("STT prewarm skipped: %s", e)
    try:
        proc.userdata["tts"] = build_tts()  # warms the Metal Kokoro model in the idle executor
    except Exception as e:  # noqa: BLE001
        logger.warning("TTS prewarm skipped: %s", e)

    # Pre-load any LOCAL Ollama model on the critical path so turn 1 isn't a ~3s cold start
    # (Ollama loads on first use + unloads when idle → keep_alive keeps it hot). Two cases:
    #   · llm_provider == "local"  → the main LLM is Ollama
    #   · llm_provider == "nucleo" with a LOCAL fast layer → the «Colmena» FlashBrain runs on Ollama
    _warm = []  # (ollama_v1_url, model)
    if SETTINGS.llm_provider == "local":
        _warm.append((SETTINGS.local_llm_url, SETTINGS.local_llm_model))
    if SETTINGS.llm_provider == "nucleo":
        try:
            from nucleo.flash.fast_client import spec_from_config
            spec = spec_from_config()
            if (spec.provider or "").lower() == "ollama" and spec.model:
                _warm.append((spec.resolved_base_url(), spec.model))
        except Exception as e:  # noqa: BLE001
            logger.warning("nucleo fast-layer prewarm probe skipped: %s", e)
    for url, model in _warm:
        try:
            import json
            import urllib.request

            req = urllib.request.Request(
                url.rsplit("/v1", 1)[0] + "/api/generate",
                data=json.dumps(
                    {"model": model, "prompt": "hola", "stream": False, "keep_alive": "30m"}
                ).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=60).read()
            logger.info("prewarmed local Ollama model %s", model)
        except Exception as e:  # noqa: BLE001
            logger.warning("local Ollama prewarm skipped (%s): %s", model, e)
    logger.info("prewarm() DONE — warm executor ready (userdata: %s)", sorted(proc.userdata.keys()))


def _metric_line(m) -> str:
    parts = []
    for attr, label in (("ttft", "ttft"), ("duration", "dur"), ("ttfb", "ttfb"),
                        ("end_of_utterance_delay", "eou"), ("audio_duration", "audio")):
        v = getattr(m, attr, None)
        if isinstance(v, (int, float)) and v > 0:
            parts.append(f"{label}={v:.2f}s")
    return f"{type(m).__name__}: " + " ".join(parts) if parts else type(m).__name__


# GUARD kickoff único por sala (V2-047 F8): sala → timestamp del último saludo. Un 2º job de la MISMA sala en una
# ventana corta no re-saluda (doble dispatch de LiveKit / reconexión rápida del frontend).
_KICKOFF_SEEN: dict = {}
_KICKOFF_WINDOW_S = 8.0


def _kickoff_recent(room: str) -> bool:
    t = _KICKOFF_SEEN.get(room or "")
    return t is not None and (time.time() - t) < _KICKOFF_WINDOW_S


def _mark_kickoff(room: str) -> None:
    now = time.time()
    _KICKOFF_SEEN[room or ""] = now
    for k in [k for k, v in _KICKOFF_SEEN.items() if now - v > 300]:   # poda entradas viejas
        _KICKOFF_SEEN.pop(k, None)


async def entrypoint(ctx: JobContext) -> None:
    setup_console_logging()
    await ctx.connect()

    session_id = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    boot = BootChannel(ctx.room, session_id)   # boot handshake (topic vl2) + optional mic recording; NOT the log

    # ÚNICO sistema de registro: voice.observer.emit() (anillo + fichero por sesión + timeline + SSE). Todo
    # evento de voz se registra aquí y de aquí lo consumen /debug, /events y el tester. Se adquiere pronto para
    # que hasta el worker_start pase por el observador (antes se partía en dos: DebugBus + observer).
    try:
        from voice.observer import emit as _emit
    except Exception:
        _emit = lambda *a, **k: None

    # Gate de atención (V2-015): sesión nueva → ventana de conversación cerrada (no heredar un estado viejo).
    try:
        from voice import attention
        attention.reset()
    except Exception:
        pass

    # Prewarm reuse check (INI-013 2026-07-08): a warm session reuses the idle executor's
    # userdata (all True); if any is False the session is paying a cold rebuild → investigate
    # prewarm (num_idle_processes exhausted, prewarm timed out, etc). Kept as a permanent probe.
    _ud = ctx.proc.userdata
    logger.info("session on %s executor — vad_hit=%s stt_hit=%s tts_hit=%s",
                "WARM" if _ud.get("stt") else "COLD",
                _ud.get("vad") is not None, _ud.get("stt") is not None, _ud.get("tts") is not None)
    vad_plain = ctx.proc.userdata.get("vad") or build_vad()
    stt = ctx.proc.userdata.get("stt") or build_stt(vad=vad_plain)  # reuse warm STT
    llm = build_llm(SETTINGS.llm_provider, SETTINGS.llm_model)

    # MEMORIA DE ARRANQUE: el «Colmena» FlashBrain (nucleo) NO tira de un briefing pre-arranque — su memoria de
    # arranque sale de la memoria central propia (`memory.state()`). Desde V2-011 (latencia) ese bloque se
    # CACHEA fuera del turno (`nucleo/flash/memory_cache.py`): se PRECOMPONE aquí, una vez, para que el PRIMER
    # turno (saludo por nombre) ya lo tenga sin disparar el retriever en el camino caliente. Best-effort — nunca
    # rompe ni retrasa el arranque de la voz. `set_briefing()` se conserva como no-op de compat (ver nucleo.py).
    if SETTINGS.llm_provider == "nucleo":
        try:
            from nucleo.flash import memory_cache
            await memory_cache.prime()
        except Exception as e:  # noqa: BLE001
            logger.warning("nucleo memory-cache prime skipped (voice continues): %s", e)

    # STT hardware backend actually resolved (metal/cuda/cpu), for logs + UI.
    stt_device = None
    if SETTINGS.stt_provider == "whisper_local":
        from ..speech.stt import whisper_local
        stt_device = whisper_local.RESOLVED_DEVICE

    _emit("worker_start", "motor de voz arriba", role="system",
          extra={"profile": SETTINGS.profile, "stt": SETTINGS.stt_provider, "stt_device": stt_device,
                 "llm_provider": SETTINGS.llm_provider, "llm_model": SETTINGS.llm_model or "(default)",
                 "tts": SETTINGS.tts_provider, "turn": SETTINGS.turn_provider})
    logger.info("Connected to %s (profile=%s, stt=%s%s) — session log %s",
                ctx.room.name, SETTINGS.profile, SETTINGS.stt_provider,
                f"/{stt_device}" if stt_device else "", boot.dir)

    tts = ctx.proc.userdata.get("tts") or build_tts()  # reuse warm TTS (Metal Kokoro loaded in prewarm)
    turn_detection = build_turn_detection() or "vad"   # None (disabled) → VAD-based EOU (no ML InferenceRunner)
    # tapea el VAD de la sesión SOLO para grabar el mic (ZAELAR_RECORD_MIC); si no, el VAD pelado directo.
    vad_session = tapped_vad(vad_plain, boot) if boot.recording else vad_plain

    _busy = {"bot": False, "user": False}   # feeds the proactive busy-probe (don't talk over a live turn)

    def on_state_change(state: State) -> None:
        logger.info("STATE -> %s", state.value)
        speaking = (getattr(state, "value", state) == "speaking")
        _busy["bot"] = speaking
        # estado completo (initializing/thinking/listening/speaking) al log unificado + bot_speech para el orbe.
        _emit("state", state.value, role="system", extra={"state": state.value})
        _emit("bot_speech", "speaking" if speaking else "idle", extra={"speaking": speaking})

    sm = StateMachine(on_change=on_state_change)

    # BARGE-IN / INTERRUPCIÓN — TUNEABLE por env (fallback a los defaults de LiveKit; config UI-managed es follow-up).
    # Un ruido/chasquido corto NO debería cortar la locución (queja del operador). Palancas:
    #   · ZAELAR_MIN_INTERRUPTION_SEC  — voz mínima (s) para contar como interrupción (LiveKit def 0.5; subimos a
    #     0.6 para filtrar transitorios sin dañar mucho la latencia del barge-in real).
    #   · ZAELAR_MIN_INTERRUPTION_WORDS — nº mínimo de palabras del STT para confirmar la interrupción (def 0 = off).
    #   · ZAELAR_FALSE_INTERRUPTION_TIMEOUT — silencio (s) tras cortar antes de declararla FALSA (LiveKit def 2.0).
    #   · ZAELAR_RESUME_FALSE_INTERRUPTION — reanudar la locución tras una falsa interrupción (LiveKit def True; la
    #     salida de audio de la sala soporta pause, así que aplica). Un ruido corta ~<timeout> y luego RETOMA.
    def _int_kwargs() -> dict:
        out: dict = {}
        def _f(name):
            v = (os.getenv(name) or "").strip()
            try:
                return float(v) if v else None
            except ValueError:
                return None
        def _i(name):
            v = (os.getenv(name) or "").strip()
            try:
                return int(v) if v else None
            except ValueError:
                return None
        dur = _f("ZAELAR_MIN_INTERRUPTION_SEC")
        out["min_interruption_duration"] = dur if dur is not None else 0.6
        words = _i("ZAELAR_MIN_INTERRUPTION_WORDS")
        if words is not None:
            out["min_interruption_words"] = words
        fit = _f("ZAELAR_FALSE_INTERRUPTION_TIMEOUT")
        if fit is not None:
            out["false_interruption_timeout"] = fit
        resume = (os.getenv("ZAELAR_RESUME_FALSE_INTERRUPTION") or "").strip().lower()
        if resume:
            out["resume_false_interruption"] = resume in ("1", "true", "yes", "on")
        return out

    _interruption = _int_kwargs()
    logger.info("barge-in tuning: %s (resume needs room audio pause=True)", _interruption)

    session = AgentSession(
        vad=vad_session,
        stt=stt,
        llm=llm,
        tts=tts,
        turn_detection=turn_detection,
        preemptive_generation=True,   # latency: start generating before EOU confirmed
        allow_interruptions=True,     # barge-in: user speech cancels TTS immediately
        **_interruption,
    )

    @session.on("agent_state_changed")
    def _on_agent_state(ev) -> None:
        sm.on_agent_state(ev.new_state)

    @session.on("user_state_changed")
    def _on_user_state(ev) -> None:
        sm.on_user_state(ev.new_state)
        new = getattr(ev.new_state, "value", ev.new_state)
        was_bot_speaking = _busy["bot"]
        _busy["user"] = (new == "speaking")
        # OBSERVABILIDAD DE VOZ: hasta ahora el observador (/events, la lista de /debug) NO veía el borde de VAD
        # del usuario ni el instante en que su voz PISA la locución de zaelar (barge-in). Sin esto era imposible
        # diagnosticar "un ruido cortó la locución". Ahora se ve: voz detectada · barge-in · fin de voz.
        if new == "speaking":
            if was_bot_speaking:
                _emit("vad", "✂️ barge-in — voz pisa la locución (LiveKit corta el TTS)",
                      role="user", extra={"over_agent": True})
            else:
                _emit("vad", "🎤 voz detectada (VAD)", role="user", extra={"over_agent": False})
        elif new == "listening":
            _emit("vad", "… fin de voz", role="user", extra={})

    # FIRST-RUN LANGUAGE AUTO-DETECTION (V2-089 P3): on a brand-new install, detect the operator's language from
    # their first utterance(s) and lock it — no trip to settings. Fires at most once per session; a no-op after a
    # language has been chosen (i18n.init.detect.should_detect()). Off the hot path: classify runs in a thread.
    _lang_detect = {"busy": False, "done": False}

    def _maybe_detect_language(text: str) -> None:
        if _lang_detect["done"] or _lang_detect["busy"]:
            return
        try:
            from i18n.init import detect as _d
        except Exception:
            _lang_detect["done"] = True
            return
        if not _d.should_detect():
            _lang_detect["done"] = True
            return
        if len((text or "").strip()) < 2:
            return
        _lang_detect["busy"] = True

        async def _run() -> None:
            try:
                code = await asyncio.to_thread(_d.classify, text)
                if code:
                    await _d.lock(code)
                    _lang_detect["done"] = True
            except Exception as e:  # noqa: BLE001
                logger.warning("i18n first-run detect failed: %s", e)
            finally:
                _lang_detect["busy"] = False

        try:
            asyncio.create_task(_run())
        except RuntimeError:
            _lang_detect["busy"] = False

    @session.on("user_input_transcribed")
    def _on_transcript(ev) -> None:
        if ev.is_final:
            # → observer/SSE: chat wall + the front-end voice-command fast-path (show/close widgets) consume this.
            _emit("transcript", "🗣", text=ev.transcript, role="user")
            _maybe_detect_language(ev.transcript)
        else:
            _emit("interim", "…", text=ev.transcript, role="user")   # live, UI-only (dedup/no-disk en observer)

    @session.on("conversation_item_added")
    def _on_item(ev) -> None:
        item = ev.item
        role, text = getattr(item, "role", None), getattr(item, "text_content", None)
        if role == "assistant" and text:
            _emit("transcript", "zaelar", text=text, role="assistant")

    @session.on("agent_false_interruption")
    def _on_false_interrupt(ev) -> None:
        # Un ruido/backchannel cortó la locución pero NO era una interrupción real (ni transcripción dirigida).
        # `resumed` dice si LiveKit reanudó la locución (necesita que la salida de audio soporte pause; la sala sí).
        # Si aparece `resumed=False` de forma sistemática, ESE es el bug de "se paró todo y no siguió".
        resumed = bool(getattr(ev, "resumed", False))
        _emit("vad", "🤫 falsa interrupción (ruido) — reanudo la locución" if resumed
              else "🤫 falsa interrupción (ruido) — NO reanudo (audio sin pause)",
              role="system", extra={"resumed": resumed})

    @session.on("overlapping_speech")
    def _on_overlap(ev) -> None:
        # Voz solapada mientras zaelar habla; el detector la clasifica interrupción vs backchannel (charla de fondo).
        # Solo dispara con el detector ML de interrupción activo; inofensivo si el turno va por VAD puro.
        is_int = bool(getattr(ev, "is_interruption", False))
        _emit("vad", "🔊 voz solapada — interrupción" if is_int
              else "🔊 voz solapada — backchannel (ignorada)",
              role="user", extra={"is_interruption": is_int})

    @session.on("metrics_collected")
    def _on_metrics(ev) -> None:
        # ANTI-FLOOD (2026-07-12): las métricas SIN latencias reales (sobre todo VADMetrics, ~2/s de forma
        # continua — más con ruido de fondo) NO se registran: no aportan dato útil y cada evento hacía 2
        # escrituras de fichero SÍNCRONAS en el hilo de voz + floodeaba el SSE. `_metric_line` solo mete un
        # "=" cuando hay números (ttft/dur/ttfb/eou/audio) → si no hay "=", es un nombre pelado y se descarta.
        line = _metric_line(ev.metrics)
        if "=" in line:
            _emit("metric", line, role="system")
        # Forward REMOTE STT/TTS latency into the observer stream too — Cartesia/Deepgram/Voxtral run entirely
        # inside their LiveKit plugin (no zaelar call site to instrument directly), so LiveKit's own per-provider
        # metric is the only place this ever surfaces. Local backends (Kokoro/whisper_local) already emit their
        # own tts_ms/stt_ms at the exact call site (more precise: text/backend attached) — skip here to avoid a
        # duplicate row for the same utterance.
        m = ev.metrics
        kind = type(m).__name__
        if kind == "TTSMetrics" and SETTINGS.tts_provider != "kokoro_local":
            dur = getattr(m, "duration", None)
            if dur:
                _emit("tts", f"🔊 {SETTINGS.tts_provider}", extra={"tts_ms": round(dur * 1000)})
            try:
                from nucleo import energy_meter as _energy
                _energy.report_tts_usage(characters=getattr(m, "characters_count", None))
            except Exception:
                pass
        elif kind == "STTMetrics" and SETTINGS.stt_provider != "whisper_local":
            dur = getattr(m, "duration", None)
            if dur:
                _emit("stt", f"👂 {SETTINGS.stt_provider}", extra={"stt_ms": round(dur * 1000)})
            try:
                from nucleo import energy_meter as _energy
                _energy.report_stt_usage(audio_seconds=getattr(m, "audio_duration", None))
            except Exception:
                pass

    @session.on("error")
    def _on_error(ev) -> None:
        _emit("error", "⚠️ " + str(getattr(ev, "error", ev))[:200], role="system")
        logger.error("session error: %s", getattr(ev, "error", ev))

    # PROACTIVE VOICE: let PROCESS-LEVEL callers (the orchestrator loop's scheduled tasks/sparks, SlowBrain
    # escalation delivery) SPEAK a specific text through this live session's TTS — no brain turn, no re-generation.
    # Registered while the session is live, cleared on close. If no session is live, delivery still reaches the UI (SSE).
    from voice import proactive as _proactive

    async def _speak(text: str) -> None:
        # INSTRUMENTACIÓN (V2-047 F7): el operador reporta que a media locución zaelar se corta, pausa y suelta el
        # SIGUIENTE mensaje. Sospecha: una entrega proactiva (session.say) que entra mientras el bot AÚN habla y
        # corta el TTS en vuelo. Registramos `say` con si había locución/turno vivo al empezar → medible en /debug
        # (si `bot_in_flight` sale True a menudo, el fix es SERIALIZAR: encolar el say hasta que el handle vivo
        # acabe, en vez de solaparlo). Solo telemetría; no cambia el comportamiento todavía.
        _bot0, _usr0 = _busy["bot"], _busy["user"]
        try:
            _emit("tts", "say (entrega proactiva)", text=(text or "")[:120], role="assistant",
                  extra={"bot_in_flight": bool(_bot0), "user_in_flight": bool(_usr0)})
        except Exception:
            pass
        await session.say((text or "").strip(), allow_interruptions=True)

    _proactive.register_speaker(_speak)
    _proactive.register_busy_probe(lambda: _busy["bot"] or _busy["user"])   # don't talk over a live turn

    # DEMO CAP (INI-018 T6): closer registry, same shape as the proactive speaker above — a no-op
    # everywhere the ZAELAR_DEMO_* env vars aren't set (self-host, the operator's own cloud account).
    from nucleo import demo_limits as _demo_limits

    async def _close_demo_session(reason: str) -> None:
        _emit("session", f"demo limit reached ({reason}) — closing", role="system")
        # let the closing line (already queued via send()/session.say before this was called) finish
        # playing before the room actually goes away.
        for _ in range(50):  # ~10s hard cap so a stuck busy-probe can never wedge the close forever
            if not _busy["bot"]:
                break
            await asyncio.sleep(0.2)
        await asyncio.sleep(0.3)
        ctx.shutdown(reason=f"demo:{reason}")

    _demo_limits.register_closer(_close_demo_session)

    # ACCOUNT ENERGY CAP (2026-08-09): real-account counterpart of the demo cap above, same closer
    # shape — but unlike demo_limits.check() (called synchronously BEFORE the next turn, with its
    # closing line already queued by the caller), account_limits fires ASYNCHRONOUSLY from
    # energy_meter.py's fire-and-forget usage report, well after the triggering turn's own reply
    # already finished — so this closer must SPEAK the closing line itself, not just wait for one.
    # No-op everywhere ZAELAR_USER_ID isn't set (self-host, demo) — cloud_account.is_cloud_account().
    from nucleo import account_limits as _account_limits
    from nucleo import cloud_account as _cloud_account

    async def _close_account_session(reason: str) -> None:
        _emit("session", f"account energy exhausted ({reason}) — closing", role="system")
        try:
            await session.say(langs.current_language().energy_exhausted, allow_interruptions=True)
        except Exception:
            pass
        for _ in range(50):  # ~10s hard cap so a stuck busy-probe can never wedge the close forever
            if not _busy["bot"]:
                break
            await asyncio.sleep(0.2)
        await asyncio.sleep(0.3)
        ctx.shutdown(reason=f"account:{reason}")

    if _cloud_account.is_cloud_account():
        _account_limits.register_closer(_close_account_session)

    # CHAT TEXT: the frontend publishes typed/pasted messages on the LiveKit data topic "zaelar-text"
    # (session-lk.js). Inject each as a normal user turn so the brain answers it exactly like a spoken turn.
    import json as _json

    @ctx.room.on("data_received")
    def _on_data(packet) -> None:
        try:
            topic = getattr(packet, "topic", None)
            # PTT (V2-015): el frontend publica el estado del push-to-talk en el topic `zaelar-ptt`; en modo
            # ZAELAR_ATTENTION=ptt es la señal que marca un turno como dirigido (ver voice/attention.py).
            if topic == "zaelar-ptt":
                try:
                    from voice import attention
                    attention.set_ptt(bool(_json.loads(bytes(packet.data).decode("utf-8")).get("active")))
                except Exception:
                    pass
                return
            # SILENCIO = decisión del OPERADOR (V2-054 · redefinido en V2-088). El frontend publica {audio:false}
            # cuando el operador SILENCIA con el icono 🔊, y {audio:true} cuando lo reactiva. Con audio_enabled=False
            # el pipeline de LiveKit NO invoca el TTS (agent_activity: audio_output=None → rama text-only) → CERO
            # síntesis: ahorra latencia y coste, y es la diferencia entre «silenciado» y «bajar el volumen».
            #
            # Ya NO lo dispara abrir el chat. Eso era V2-054 («modo chat = voz off») y partía de una premisa falsa:
            # que abrir el panel significaba «prefiero leer». El panel tiene cuatro pestañas y se entra a mirar
            # procesos, crons o clusters sin querer callar a nadie. Ahora el chat y la voz son independientes; el
            # único dueño del silencio es el icono. La respuesta llega SIEMPRE al ChatWall por el evento
            # transcript/assistant (conversation_item_added), que es independiente del audio: chat, subtítulos y
            # voz son tres vistas de lo mismo, no modos que se excluyan.
            if topic == "zaelar-voice":
                try:
                    want = bool(_json.loads(bytes(packet.data).decode("utf-8")).get("audio", True))
                    session.output.set_audio_enabled(want)
                    # La etiqueta importa: es lo que un agente lee en `/api/debug` para diagnosticar «no se oye».
                    # Decía «modo chat», y desde V2-088 eso ya no es la causa — silenciar es SIEMPRE una decisión
                    # del operador con el icono. Una etiqueta que apunta a una causa falsa cuesta horas.
                    _emit("session", "voz ON (síntesis activa)" if want
                          else "voz OFF (el operador silenció con el icono 🔊 — sin TTS)",
                          role="system")
                except Exception as ve:
                    logger.warning("zaelar-voice toggle failed: %s", ve)
                return
            if topic not in (None, "", "zaelar-text"):
                return
            payload = _json.loads(bytes(packet.data).decode("utf-8"))
            if payload.get("t") != "zaelar-text":
                return
            txt = (payload.get("text") or "").strip()
            if txt:
                # El chat/paste escrito SIEMPRE va dirigido a zaelar → abre la ventana de atención antes de
                # generar la respuesta (así el gate del provider lo trata como turno atendido, no ambiente).
                try:
                    from voice import attention
                    attention.note_directed()
                except Exception:
                    pass
                # OBSERVABILIDAD (diag intermitencia chat/paste): deja rastro de que el texto LLEGÓ, y si
                # generate_reply lanza. Si en un all-1s de chat vemos "recibido" pero no reply → generate_reply
                # es el culpable (sesión ocupada); si no vemos "recibido" → el paquete de datos no llegó. (2026-07-07)
                _emit("brain", "📥 chat/paste recibido", text=txt, role="user")
                # generate_reply() is SYNC (returns a SpeechHandle and schedules the reply itself); calling it
                # directly (wrapping in create_task raised "a coroutine was expected"). (fix 2026-07-07)
                try:
                    session.generate_reply(user_input=txt)
                except Exception as ge:
                    _emit("alert", "chat/paste generate_reply falló", text=str(ge)[:160])
                    logger.warning("chat-text generate_reply failed: %s", ge)
        except Exception as e:
            logger.warning("chat-text data handler: %s", e)

    @session.on("close")
    def _on_close(ev) -> None:
        _emit("session", "session closed", role="system")
        try:
            _proactive.clear_speaker(_speak)
        except Exception:
            pass
        try:
            _demo_limits.clear_closer(_close_demo_session)
        except Exception:
            pass
        try:
            _account_limits.clear_closer(_close_account_session)
        except Exception:
            pass
        boot.close()

    # Reply LANGUAGE = the active interface language (⚙/voice, live). Appended to the persona so
    # direct/duo reply in it; Hermes also gets it in the kickoff brief below (memory still wins for names).
    _lang = langs.current_language()
    agent = Agent(instructions=SETTINGS.system_prompt + " " + _lang.reply_directive)
    await session.start(room=ctx.room, agent=agent)
    logger.info("Session started.")

    # BOOT SEQUENCE — INIT then PROCESS. The voice must NOT run under the splash: we report the ordered backend
    # milestones over the "vl2" channel (the frontend's «Colmena» splash lights one cluster per phase), emit the
    # `ready` BARRIER, and ONLY THEN hand the brain its greeting. The heavy startup cost (mic permission, room
    # connect, Whisper warm) is already paid and the central memory is persisted (V2-011, precomposed above via
    # memory_cache.prime) → these are quick; the tiny sleeps are a deliberate ~0.5s sweep, not a fake wait.
    boot.boot("memoria")   # central-memory state block precomposed (memory_cache.prime, above)
    await asyncio.sleep(0.25)
    boot.boot("reflejo")   # STT/TTS warm + FlashBrain provider live → the reflex is ready to serve
    await asyncio.sleep(0.25)
    # BARRIER: init done — voice session live, memory composed, warm. The splash lifts and IMPLODES into the orb
    # NOW, BEFORE zaelar speaks, so the greeting lands as the orb appears — never buried under the loading screen.
    # Room-scoped signal (not the global /events SSE) so it ties to exactly the room this browser just joined.
    boot.ready()

    # KICKOFF — only AFTER `ready`. V2-027: NO re-inyectamos aquí el brief verboso de capacidades (widgets/
    # meshkore/cron/architect/messaging). El system prompt POR TURNO ya lleva el ESTADO + los recursos TERSOS
    # (`build_flash_system` → `_flash_layer`), así que volcarlo otra vez en el kickoff era el volcado VIEJO que
    # bloateaba justo el PRIMER turno (el más sensible a latencia). El saludo solo necesita la instrucción de
    # primer turno memory-aware: el cerebro ya saluda por nombre desde la memoria central.
    kickoff_text = (f"[The operator's selected interface language is {_lang.native} — SPEAK "
                    f"{_lang.name}.]\n"
                    "I just connected. FIRST turn — SHORT and warm. CHECK YOUR MEMORY first: if you "
                    "already know me (my name), greet me BY NAME and pick up naturally — do NOT ask my "
                    f"name again. If you do NOT know me yet, introduce yourself in one line and ask my name. "
                    f"Reply in {_lang.name}. Two sentences max. Then stop and wait for me.")
    # GUARD kickoff ÚNICO por sala (V2-047 F8, sesión 23:15: DOS «motor de voz arriba» a las 23:15:45 y :46 → dos
    # saludos generados). Una reconexión rápida del frontend / doble dispatch de LiveKit levanta dos jobs para la
    # MISMA sala; el segundo NO debe volver a saludar (el operador oía el saludo repetido). Determinista, por sala,
    # con ventana corta: si otro job ya saludó esta sala hace <8s, este se lo salta (la sesión sigue viva y atiende
    # turnos normalmente; solo se evita el saludo duplicado).
    # CONTINUIDAD (bug 2026-07-25, operador: "le pongo un mensaje y me dice ¿qué necesitas?"): una RECONEXIÓN a una
    # conversación EN CURSO no debe re-saludar. Cada reconexión de voz disparaba el kickoff de "primer turno,
    # preséntate" en mitad de una charla de una hora → «Hola, ¿qué necesitas?» absurdo. Si el operador habló hace
    # poco (buffer conv reciente), NO saludamos: sembramos contexto y esperamos su próximo turno en silencio.
    _resume_window = float(os.getenv("ZAELAR_RESUME_WINDOW_S", "1800"))  # 30 min: reconexión = misma sesión
    _last_conv_age = None
    try:
        from memory import api as _mem
        _last_conv_age = _mem.seconds_since_last_conv()
    except Exception:
        _last_conv_age = None
    if _kickoff_recent(ctx.room.name):
        _emit("brain", "🚫 kickoff duplicado evitado (otra sesión ya saludó esta sala)", role="system")
    elif _last_conv_age is not None and _last_conv_age < _resume_window:
        # sesión EN CURSO: retomamos sin saludar (el operador sigue la conversación; no lo interrumpas con un hola)
        _mark_kickoff(ctx.room.name)
        _emit("brain", f"↩️ kickoff omitido — reconexión a sesión en curso (último turno hace {int(_last_conv_age)}s), "
                       "retomando en silencio", role="system")
    else:
        _mark_kickoff(ctx.room.name)
        _emit("brain", "kickoff (saludo memory-aware vía cerebro)", role="system")
        await session.generate_reply(user_input=kickoff_text)


async def request_fnc(req: JobRequest) -> None:
    """Only take our own rooms. Several projects can share one local LiveKit dev
    server; without this our worker would also grab e.g. a voice-lab-2 room from
    another session (auto-dispatch = all rooms) and step on it. Per-session tokens
    mint ``<room_name>-<uuid>`` (server/livekit_api.py), so the prefix matches."""
    if req.room.name.startswith(SETTINGS.room_name):
        await req.accept()
    else:
        await req.reject()


def make_server() -> AgentServer:
    """Build the embeddable ``AgentServer`` (zaelar runs this in-process).

    VERIFIED empirically against livekit-agents 1.6.4 (voice-lab-2 .venv):
      * ``AgentServer.__init__`` does NOT take ``entrypoint_fnc``/``prewarm_fnc`` —
        those parameters live on the legacy ``WorkerOptions``. In 1.6.4 the
        entrypoint is registered via the ``rtc_session`` decorator/registrar
        (``server.rtc_session(entrypoint)``) and prewarm is the ``setup_fnc``
        constructor argument. (``cli.run_app`` accepts either an ``AgentServer`` or
        a ``WorkerOptions``; ``_legacy.run_app`` converts WorkerOptions ->
        ``AgentServer.from_server_options``.)
      * ``JobExecutorType.THREAD`` runs the job in a thread of the current process
        (vs. the default ``PROCESS`` that spawns a subprocess), which is what lets
        the voice job share state with the zaelar brain.

    Signatures observed:
      AgentServer.__init__(self, *, job_executor_type=PROCESS, ..., setup_fnc=None,
                           load_fnc=None, ws_url=None, api_key=None, api_secret=None, ...)
      AgentServer.rtc_session(self, func=None, *, agent_name="", type=ROOM, ...)
    """
    server = AgentServer(
        job_executor_type=JobExecutorType.THREAD,
        setup_fnc=prewarm,                      # prewarm is `setup_fnc` on AgentServer
        # Keep one fully-warm executor idle (prewarm loads Whisper) so the first
        # connect joins fast; the ProcPool warms it for the THREAD executor too.
        num_idle_processes=1,
        initialize_process_timeout=90,          # prewarm loads Whisper (+ Ollama on local)
        ws_url=SETTINGS.livekit_url,
        api_key=SETTINGS.livekit_api_key,
        api_secret=SETTINGS.livekit_api_secret,
    )
    # on_request = request_fnc: only service zaelar's own rooms (room isolation when
    # a local LiveKit dev server is shared with other projects, e.g. voice-lab-2).
    server.rtc_session(entrypoint, on_request=request_fnc)
    return server


if __name__ == "__main__":
    # Standalone debug worker via the (deprecated) rich CLI. cli.run_app accepts an
    # AgentServer directly in 1.6.4, so we reuse the same factory the embedded path uses.
    cli.run_app(make_server())
