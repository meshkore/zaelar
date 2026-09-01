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
        # Remote TTS plugins (Cartesia) keep a websocket ConnectionPool that is only opened on the FIRST
        # synthesis — so the session's first utterance (the kickoff greeting) paid a fresh TLS+WS handshake
        # (2026-09-01 latency audit). Plugins that expose prewarm() get their pool opened here, in the idle
        # executor; local TTS (Kokoro) has no such method and is already warmed by build_tts() itself.
        _pw = getattr(proc.userdata["tts"], "prewarm", None)
        if callable(_pw):
            _pw()
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


# GUARD: one kickoff per room (V2-047 F8): room → timestamp of the last greeting. A 2nd job for the SAME room in a
# short window does not greet again (LiveKit double dispatch / rapid frontend reconnection).
_KICKOFF_SEEN: dict = {}
_KICKOFF_WINDOW_S = 8.0


def _kickoff_recent(room: str) -> bool:
    t = _KICKOFF_SEEN.get(room or "")
    return t is not None and (time.time() - t) < _KICKOFF_WINDOW_S


def _mark_kickoff(room: str) -> None:
    now = time.time()
    _KICKOFF_SEEN[room or ""] = now
    for k in [k for k, v in _KICKOFF_SEEN.items() if now - v > 300]:   # prune old entries
        _KICKOFF_SEEN.pop(k, None)


def _endpointing_opts() -> dict:
    """How much silence closes a turn. The values live in `voice/endpointing.py` — the SINGLE source of truth for
    this decision, written from real sessions (INI-009) and orphaned until now. Env overrides allow hot adjustment
    without touching code."""
    from voice import endpointing as _ep

    def _f(name: str, default: float) -> float:
        v = (os.getenv(name) or "").strip()
        try:
            return float(v) if v else default
        except ValueError:
            return default

    lo = _f("ZAELAR_ENDPOINT_MIN_S", _ep.HOLD_BASE)
    hi = _f("ZAELAR_ENDPOINT_MAX_S", _ep.HOLD_MAX)
    return {"mode": "dynamic", "min_delay": lo, "max_delay": max(lo, hi)}


async def entrypoint(ctx: JobContext) -> None:
    setup_console_logging()
    await ctx.connect()

    session_id = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    boot = BootChannel(ctx.room, session_id)   # boot handshake (topic vl2) + optional mic recording; NOT the log

    # SINGLE logging system: voice.observer.emit() (ring + per-session file + timeline + SSE). Every voice
    # event is logged here and consumed from here by /debug, /events, and the tester. Acquire it early so even
    # worker_start passes through the observer (previously it was split in two: DebugBus + observer).
    try:
        from voice.observer import emit as _emit
    except Exception:
        _emit = lambda *a, **k: None

    # Attention gate (V2-015): new session → conversation window closed (do not inherit an old state).
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

    # STARTUP MEMORY: the «Colmena» FlashBrain (nucleo) does NOT use a pre-startup briefing — its startup memory
    # comes from its own central memory (`memory.state()`). Since V2-011 (latency), that block is CACHED outside
    # the turn (`nucleo/flash/memory_cache.py`): it is PRECOMPOSED here once so the FIRST turn (name greeting)
    # already has it without triggering the retriever on the hot path. Best-effort — it never breaks or delays
    # voice startup. `set_briefing()` is retained as a compatibility no-op (see nucleo.py).
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
                 "tts": SETTINGS.tts_provider, "turn": SETTINGS.turn_provider,
                 **{f"endpoint_{k}": v for k, v in _endpointing_opts().items()}})
    logger.info("Connected to %s (profile=%s, stt=%s%s) — session log %s",
                ctx.room.name, SETTINGS.profile, SETTINGS.stt_provider,
                f"/{stt_device}" if stt_device else "", boot.dir)

    tts = ctx.proc.userdata.get("tts") or build_tts()  # reuse warm TTS (Metal Kokoro loaded in prewarm)
    turn_detection = build_turn_detection() or "vad"   # None (disabled) → VAD-based EOU (no ML InferenceRunner)
    # tap the session VAD ONLY to record the mic (ZAELAR_RECORD_MIC); otherwise use the bare VAD directly.
    vad_session = tapped_vad(vad_plain, boot) if boot.recording else vad_plain

    _busy = {"bot": False, "user": False}   # feeds the proactive busy-probe (don't talk over a live turn)

    # States whose trace is SAFE to read from active() (2026-08-16, source audit): "speaking"/"listening"/
    # "interrupted" describe something about a turn that ALREADY has a trace (TTS starts only once there is text
    # generated by THAT turn; "listening" is its natural tail; "interrupted" is the barge-in that INTERRUPTS that speech).
    # "thinking"/"idle" can fire BEFORE the turn has a trace (LiveKit emits them from its own orchestration task,
    # before invoking the LLM) — attaching active() to them would assign the PREVIOUS turn's trace more often than
    # the correct one, so they are left UNFORCED (the same criterion as the operator transcript; see active()'s
    # comment in voice/trace.py).
    _STATE_TRACE_SAFE = {"speaking", "listening", "interrupted"}

    def on_state_change(state: State) -> None:
        logger.info("STATE -> %s", state.value)
        speaking = (getattr(state, "value", state) == "speaking")
        _busy["bot"] = speaking
        # This handler runs in the pipeline's LiveKit task, a SIBLING of the one that sets the turn trace — the
        # ambient ContextVar never sees it (source audit 2026-08-16, see voice/trace.py::active()).
        _tid = ""
        if state.value in _STATE_TRACE_SAFE:
            from voice import trace as _trace
            _tid = _trace.active()
        # full state (initializing/thinking/listening/speaking) to the unified log + bot_speech for the orb.
        _emit("state", state.value, role="system", extra={"state": state.value, **({"trace": _tid} if _tid else {})})
        _emit("bot_speech", "speaking" if speaking else "idle",
              extra={"speaking": speaking, **({"trace": _tid} if _tid else {})})
        # Nothing is still sounding at this instant — this is the safe point to close any flow that finished
        # generate text WHILE the bot was still narrating the response (operator report, 2026-08-16: the turn
        # disappeared from the master during TTS). See `nucleo.py::_maybe_close_flow`/`drain_pending_flow_closes`.
        if not speaking:
            try:
                from voice.engine.llm.providers.nucleo import drain_pending_flow_closes
                drain_pending_flow_closes()
            except Exception:
                pass

    sm = StateMachine(on_change=on_state_change)

    # BARGE-IN / INTERRUPTION — TUNABLE via env (fallback to LiveKit defaults; UI-managed config is follow-up).
    # A short noise/click should NOT cut speech (operator complaint). Controls:
    #   · ZAELAR_MIN_INTERRUPTION_SEC — minimum voice duration (s) to count as an interruption (LiveKit def 0.5; raised to
    #     0.6 to filter transients without greatly harming real barge-in latency).
    #   · ZAELAR_MIN_INTERRUPTION_WORDS — minimum STT word count to confirm interruption (def 0 = off).
    #   · ZAELAR_FALSE_INTERRUPTION_TIMEOUT — silence (s) after cutting before declaring it FALSE (LiveKit def 2.0).
    #   · ZAELAR_RESUME_FALSE_INTERRUPTION — resume speech after a false interruption (LiveKit def True; the room's
    #     audio output supports pause, so it applies). Noise cuts it for ~<timeout> and then RESUMES.
    # 2026-08-10: these settings were passed as LOOSE arguments to `AgentSession`, which LiveKit 1.6 already
    # declares deprecated (“use turn_handling=TurnHandlingOptions(...) instead”) and removes in 2.0. Wiring
    # endpointing —which exists only in the new form— would have left TWO forms coexisting in the same call,
    # exactly the kind of half-finished seam that costs an afternoon six months from now. All three are migrated together.
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
        out["enabled"] = True
        dur = _f("ZAELAR_MIN_INTERRUPTION_SEC")
        out["min_duration"] = dur if dur is not None else 0.6
        words = _i("ZAELAR_MIN_INTERRUPTION_WORDS")
        if words is not None:
            out["min_words"] = words
        fit = _f("ZAELAR_FALSE_INTERRUPTION_TIMEOUT")
        if fit is not None:
            out["false_interruption_timeout"] = fit
        resume = (os.getenv("ZAELAR_RESUME_FALSE_INTERRUPTION") or "").strip().lower()
        if resume:
            out["resume_false_interruption"] = resume in ("1", "true", "yes", "on")
        return out

    _interruption = _int_kwargs()
    logger.info("barge-in tuning: %s (resume needs room audio pause=True)", _interruption)

    # ENDPOINTING — how much silence closes a turn (2026-08-10). LiveKit closes after **0.5 s** by default, and with
    # with the ML turn detector disabled (`turn_provider="disabled"`, see core/config.py), EOU is pure VAD. A
    # dictated sentence with the natural pauses of someone thinking while speaking gets split into several turns, and the agent
    # answers half-sentences: in the 13:20:50 session, a single ferry request produced 8 final transcriptions,
    # and one of them —“...from Denia to”— asked for the destination the operator was saying.
    # The values are NOT invented: they come from `voice/endpointing.py`, written for THIS bug (INI-009) from
    # real in-car sessions… and ORPHANED since then — the engine moved to LiveKit and nobody wired it,
    # so its only reference in the repo was its own test. Now it is the source of truth, and
    # `mode:"dynamic"` (moving average of observed pauses, between min and max) makes native what `hold_secs()`
    # calculated manually: short pause → quick response; speaker taking their time → more margin.
    # NOTE the expectation: this fixes ~1 s cuts, not 5 s cuts. A long silence in the middle of a sentence
    # will STILL close the turn (raising hold to 5 s would kill any short command). The brain's FRAGMENT GUARD
    # (`nucleo.py::_superseded`) prevents the damage: an superseded fragment neither speaks nor acts.
    _endpointing = _endpointing_opts()
    logger.info("endpointing: %s (turn_detection=%s)", _endpointing, turn_detection)

    session = AgentSession(
        vad=vad_session,
        stt=stt,
        llm=llm,
        tts=tts,
        turn_handling={
            "turn_detection": turn_detection,       # None (ML disabled) → EOU by VAD
            "endpointing": _endpointing,            # how much silence closes the turn (see above)
            "interruption": _interruption,          # barge-in: the operator's voice cuts TTS
            "preemptive_generation": {"enabled": True},   # latency: starts generating before EOU is confirmed
        },
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
        # VOICE OBSERVABILITY: until now the observer (/events, the /debug list) did NOT see the user's VAD edge
        # of the user or the instant when their voice OVERLAPS zaelar's speech (barge-in). Without this it was impossible
        # to diagnose "noise cut speech". Now it is visible: voice detected · barge-in · end of voice.
        if new == "speaking":
            if was_bot_speaking:
                # ONLY this case is safe to label with active() (source audit 2026-08-16): a barge-in interrupts
                # speech that ALREADY has a trace — it is THE SAME turn, not one about to begin. "voice
                # detected"/"end of voice" (below) ALWAYS precede the trace of the turn they will trigger —
                # attaching active() would assign the PREVIOUS conversation's trace more often than the correct one;
                # leave them unforced, like the operator transcript (same criterion, see voice/trace.py).
                from voice import trace as _trace
                _tid = _trace.active()
                _emit("vad", "✂️ barge-in — voz pisa la locución (LiveKit corta el TTS)",
                      role="user", extra={"over_agent": True, **({"trace": _tid} if _tid else {})})
            else:
                _emit("vad", "🎤 voz detectada (VAD)", role="user", extra={"over_agent": False})
        elif new == "listening":
            _emit("vad", "… fin de voz", role="user", extra={})

    # FIRST-RUN LANGUAGE AUTO-DETECTION (V2-089 P3, extended by V2-101): on a brand-new install, detect the
    # operator's language from their first utterance(s) and lock it — no trip to settings. Fires at most once
    # per session; a no-op after a language has been chosen (i18n.init.detect.should_detect()). Off the hot
    # path: classify runs in a thread. `onboarding` is flipped True by the kickoff block below when this is the
    # explicit "what language do you want?" turn (blocking modal on the frontend) rather than the old silent
    # background guess — it changes what `lock()` does (see detect.lock's onboarding docstring) and makes this
    # function speak the confirmation once ready. `misses` is the fail-open valve: STT noise or an unclear
    # answer must never leave a first-run operator stuck behind a modal forever.
    _lang_detect = {"busy": False, "done": False, "onboarding": False, "misses": 0}

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
                if not code and _lang_detect["onboarding"]:
                    _lang_detect["misses"] += 1
                    if _lang_detect["misses"] >= 3:
                        logger.warning("i18n onboarding: 3 unclear answers — falling back to English")
                        code = "en"
                if code:
                    result = await _d.lock(code, onboarding=_lang_detect["onboarding"])
                    _lang_detect["done"] = True
                    if _lang_detect["onboarding"] and result.get("confirm_text"):
                        try:
                            from voice import proactive
                            await proactive.notify("", result["confirm_text"], kind="language")
                        except Exception as e:  # noqa: BLE001
                            logger.warning("i18n onboarding confirmation speech failed: %s", e)
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
            # SAFE to label with active() (source audit 2026-08-16, unlike the OPERATOR transcript below in
            # _on_transcript): the assistant item is added AFTER the turn's LLM+TTS chain has run — its trace
            # already exists; it is not about to begin.
            from voice import trace as _trace
            _tid = _trace.active()
            _emit("transcript", "zaelar", text=text, role="assistant",
                  extra=({"trace": _tid} if _tid else None))

    @session.on("agent_false_interruption")
    def _on_false_interrupt(ev) -> None:
        # Noise/backchannel cut speech but was NOT a real interruption (nor directed transcription).
        # `resumed` says whether LiveKit resumed speech (the audio output must support pause; the room does).
        # If `resumed=False` appears systematically, THAT is the bug where "everything stopped and did not continue".
        # SAFE to label with active() (same case as _on_user_state's barge-in): it describes speech that was
        # ALREADY playing, not a turn about to begin.
        from voice import trace as _trace
        _tid = _trace.active()
        resumed = bool(getattr(ev, "resumed", False))
        _emit("vad", "🤫 falsa interrupción (ruido) — reanudo la locución" if resumed
              else "🤫 falsa interrupción (ruido) — NO reanudo (audio sin pause)",
              role="system", extra={"resumed": resumed, **({"trace": _tid} if _tid else {})})

    @session.on("overlapping_speech")
    def _on_overlap(ev) -> None:
        # Overlapping voice while zaelar speaks; the detector classifies it as interruption vs backchannel (background talk).
        # Fires only with the ML interruption detector active; harmless when the turn uses pure VAD.
        # SAFE to label with active(), for the same reason as above.
        from voice import trace as _trace
        _tid = _trace.active()
        is_int = bool(getattr(ev, "is_interruption", False))
        _emit("vad", "🔊 voz solapada — interrupción" if is_int
              else "🔊 voz solapada — backchannel (ignorada)",
              role="user", extra={"is_interruption": is_int, **({"trace": _tid} if _tid else {})})

    @session.on("metrics_collected")
    def _on_metrics(ev) -> None:
        # ANTI-FLOOD (2026-07-12): metrics WITHOUT real latencies (especially VADMetrics, ~2/s continuously
        # continuously — more with background noise) are NOT logged: they provide no useful data and each event caused 2
        # SYNCHRONOUS file writes in the voice thread + flooded SSE. `_metric_line` adds "=" only when there are numbers
        # (ttft/dur/ttfb/eou/audio) → without "=", it is a bare name and is discarded.
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
                # SAFE to label with active() (source audit 2026-08-16): a TTS metric describes audio synthesized
                # for text the turn ALREADY generated — its trace exists. Unlike STTMetrics (below, untouched):
                # that describes recognition of what the operator is saying NOW, which almost always precedes the
                # trace of the turn it will trigger.
                from voice import trace as _trace
                _tid = _trace.active()
                _emit("tts", f"🔊 {SETTINGS.tts_provider}", extra={"tts_ms": round(dur * 1000),
                      **({"trace": _tid} if _tid else {})})
            from nucleo import energy_meter as _energy
            # The PROVIDER is passed, not looked up inside the meter: the rate has to follow whatever
            # backend actually produced this audio, and this hook is the only place that knows it.
            _energy.report_tts_usage(characters=getattr(m, "characters_count", None),
                                     provider=SETTINGS.tts_provider)
        elif kind == "STTMetrics" and SETTINGS.stt_provider != "whisper_local":
            dur = getattr(m, "duration", None)
            if dur:
                _emit("stt", f"👂 {SETTINGS.stt_provider}", extra={"stt_ms": round(dur * 1000)})
            from nucleo import energy_meter as _energy
            _energy.report_stt_usage(audio_seconds=getattr(m, "audio_duration", None),
                                     provider=SETTINGS.stt_provider)

    @session.on("error")
    def _on_error(ev) -> None:
        _emit("error", "⚠️ " + str(getattr(ev, "error", ev))[:200], role="system")
        logger.error("session error: %s", getattr(ev, "error", ev))

    # PROACTIVE VOICE: let PROCESS-LEVEL callers (the orchestrator loop's scheduled tasks/sparks, SlowBrain
    # escalation delivery) SPEAK a specific text through this live session's TTS — no brain turn, no re-generation.
    # Registered while the session is live, cleared on close. If no session is live, delivery still reaches the UI (SSE).
    from voice import proactive as _proactive

    # THE LOOP MATTERS (2026-08-31, measured live). `session.say()` builds its playout futures on the loop that
    # runs the LiveKit job — a thread of its own. But every proactive delivery is awaited from the CALLER's loop
    # (uvicorn: a worker finishing, the messaging connector, the orchestrator's scheduled tasks), and crossing
    # that boundary makes LiveKit await a future born on the other loop:
    #
    #   RuntimeError: Task <…_wait_buffered_audio…> got Future <…> attached to a different loop
    #
    # raised INSIDE a task nobody retrieves — so `proactive.notify`'s own try/except never saw it and the only
    # trace in the log was asyncio's garbage-collector complaint, which names neither the voice nor the delivery.
    # What the operator saw: zaelar says a word or two and cuts, sometimes for good. Session c480413b: FIVE
    # proactive deliveries, five of those RuntimeErrors ~2 s later, one-to-one with no exceptions.
    #
    # Hopping onto the session's own loop is the whole fix. It is a no-op for a caller already on it (the voice
    # turn itself), so the hot path pays nothing.
    #
    # CALL SHAPE MATTERS (2026-08-31, the SECOND cut, measured live in session f5e833f7): `AgentSession.say` is
    # NOT a coroutine function — it is a SYNC method that schedules the speech on whatever loop is current and
    # returns an awaitable SpeechHandle. The first version of this hop took `lambda: session.say(...)`: calling
    # the lambda ran `say` on the CALLER's loop (the disease this hop exists to cure, alive and well), and
    # `run_coroutine_threadsafe` then rejected the returned handle — the log said, verbatim,
    # «proactive notify (voice) failed: A coroutine object is required», the buffered-audio task died cross-loop
    # three seconds in, and TTSMetrics recorded `dur=3.02s audio=99.34s`: ninety-nine seconds synthesized, three
    # spoken. `coro_fn` MUST be an `async def` whose BODY makes the call: creating the coroutine object is free
    # anywhere, but its body — the `say` call included — executes on the session's loop.
    _session_loop = asyncio.get_running_loop()
    try:
        # Make this session's loop introspectable from `/api/debug/stacks` (see `voice/debug_stacks.py`) —
        # the ONLY way to see where a wedged playout coroutine is parked without root for py-spy.
        from voice import debug_stacks as _debug_stacks
        _debug_stacks.register_loop(f"voice-session:{ctx.room.name}", _session_loop)
    except Exception:
        pass

    async def _on_session_loop(coro_fn) -> None:
        try:
            here = asyncio.get_running_loop()
        except RuntimeError:
            here = None
        if here is _session_loop:
            await coro_fn()
            return
        await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coro_fn(), _session_loop))

    async def _speak(text: str) -> None:
        # INSTRUMENTATION (V2-047 F7): record `say` with whether speech/a live turn existed at start → measurable
        # in /debug. The SERIALIZATION requested by this comment (queue `say` until the live handle finishes)
        # has existed since 2026-08-31: `voice/proactive.py` puts each notify into a FIFO ticket queue and
        # speaks ONE AT A TIME, so `bot_in_flight=True` here no longer means «it will cut»; it measures whether
        # the queue is doing its job — if it is often True again, the queue is broken, not this code.
        _bot0, _usr0 = _busy["bot"], _busy["user"]
        try:
            _emit("tts", "say (entrega proactiva)", text=(text or "")[:120], role="assistant",
                  extra={"bot_in_flight": bool(_bot0), "user_in_flight": bool(_usr0)})
        except Exception:
            pass
        async def _do_say():
            await session.say((text or "").strip(), allow_interruptions=True)   # call AND await on the session loop
        _t0 = time.perf_counter()
        await _on_session_loop(_do_say)
        # OBSERVABILITY the operator asked for (2026-08-31): the delivery's REAL playout time, next to the
        # synthesized audio length TTSMetrics already reports. `playout_ms` ≪ the audio duration is the
        # one-glance tell of a cut — exactly the comparison that took a log dig to make today.
        try:
            _emit("tts", "say (entrega proactiva) COMPLETADA", role="assistant",
                  extra={"playout_ms": round((time.perf_counter() - _t0) * 1000)})
        except Exception:
            pass

    async def _speak_ephemeral(text: str) -> None:
        # V2-122: same TTS, but `add_to_chat_ctx=False` — LiveKit never registers a conversation item for this,
        # so `conversation_item_added` (→ `_on_item` below → the chat wall) never sees it. Exclusively for the
        # FlashBrain's neutral lead-in filler (V2-093) — see `voice.proactive.ephemeral_speaker()`'s docstring
        # for the bug this fixes (a filler landing AFTER the real reply in the chat wall, reported live).
        async def _do_say():
            await session.say((text or "").strip(), allow_interruptions=True, add_to_chat_ctx=False)
        await _on_session_loop(_do_say)

    _proactive.register_speaker(_speak)
    _proactive.register_ephemeral_speaker(_speak_ephemeral)
    _proactive.register_busy_probe(lambda: _busy["bot"] or _busy["user"])   # don't talk over a live turn
    # …and the half that admits no exception, separately: do not speak over the OPERATOR, even with a waiting
    # filler (2026-08-15). The filler intentionally skips the gap wait, so it needs this dedicated signal.
    _proactive.register_user_probe(lambda: bool(_busy["user"]))
    # Same, but ONLY for the bot (2026-08-16): `nucleo.py::_maybe_close_flow` uses it to avoid closing the
    # observability flow while the response is still being narrated (see the drain in `on_state_change` below).
    _proactive.register_bot_probe(lambda: bool(_busy["bot"]))

    # ACCOUNT ENERGY CAP (2026-08-09): closer registry, same shape as the proactive speaker above.
    # Fires ASYNCHRONOUSLY from energy_meter.py's fire-and-forget usage report, well after the
    # triggering turn's own reply already finished — so this closer must SPEAK the closing line
    # itself, not just wait for one. No-op everywhere ZAELAR_USER_ID isn't set (self-host) —
    # cloud_account.is_cloud_account().
    from nucleo import account_limits as _account_limits
    from nucleo import cloud_account as _cloud_account

    async def _close_account_session(reason: str) -> None:
        _emit("session", f"account energy exhausted ({reason}) — closing", role="system")
        try:
            # Same loop hop: this closer fires from `energy_meter`'s fire-and-forget report, i.e. off this loop.
            async def _do_say():
                await session.say(langs.current_language().energy_exhausted, allow_interruptions=True)
            await _on_session_loop(_do_say)
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
            # PTT (V2-015): the frontend publishes push-to-talk state on topic `zaelar-ptt`; in
            # ZAELAR_ATTENTION=ptt this is the signal marking a turn as directed (see voice/attention.py).
            if topic == "zaelar-ptt":
                try:
                    from voice import attention
                    attention.set_ptt(bool(_json.loads(bytes(packet.data).decode("utf-8")).get("active")))
                except Exception:
                    pass
                return
            # SILENCE = OPERATOR decision (V2-054 · redefined in V2-088). The frontend publishes {audio:false}
            # when the operator MUTES with the 🔊 icon, and {audio:true} when re-enabled. With audio_enabled=False
            # the LiveKit pipeline does NOT invoke TTS (agent_activity: audio_output=None → text-only branch) → ZERO
            # synthesis: saves latency and cost, and is the difference between «muted» and «turning down the volume».
            #
            # It is NO LONGER triggered by opening the chat. That was V2-054 (“chat mode = voice off”) and rested
            # on a false premise: that opening the panel meant “I prefer to read.” The panel has four tabs, and
            # users may open it to inspect processes, crons, or clusters without wanting to silence anyone. Chat
            # and voice are now independent; the icon is the SOLE owner of silence. The response ALWAYS reaches
            # the ChatWall through the transcript/assistant event (conversation_item_added), which is independent
            # of audio: chat, subtitles, and voice are three views of the same thing, not mutually exclusive modes.
            if topic == "zaelar-voice":
                try:
                    want = bool(_json.loads(bytes(packet.data).decode("utf-8")).get("audio", True))
                    session.output.set_audio_enabled(want)
                    # The label matters: it is what an agent reads in `/api/debug` to diagnose “no sound.”
                    # It used to say “chat mode,” but since V2-088 that is no longer the cause — muting is ALWAYS
                    # a decision made by the operator with the icon. A label pointing to a false cause costs hours.
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
                # Written chat/paste is ALWAYS directed to zaelar → open the attention window before generating
                # the response (so the provider gate treats it as an attended turn, not ambient speech).
                try:
                    from voice import attention
                    attention.note_directed()
                except Exception:
                    pass
                # OBSERVABILITY (intermittent chat/paste diagnosis): leave a trace showing that the text ARRIVED,
                # and whether generate_reply raises. If a one-second chat poll shows “received” but no reply →
                # generate_reply is at fault (session busy); if “received” is absent → the data packet did not arrive.
                # (2026-07-07)
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
            _account_limits.clear_closer(_close_account_session)
        except Exception:
            pass
        boot.close()

    # Reply LANGUAGE = the active interface language (⚙/voice, live). Appended to the persona so
    # direct/duo reply in it; Hermes also gets it in the kickoff brief below (memory still wins for names).
    _lang = langs.current_language()

    class ZaelarAgent(Agent):
        # V2-529: the lead-in filler is the reply's FIRST SEGMENT. A `say()`-based filler is structurally
        # late (the reply is already the scheduler's current speech, so the say is only authorized when the
        # reply finishes playing — measured live: «Vale, empiezo» … «Espera, espera»), and a `tts_node`
        # wrapper cannot work either: this pipeline only calls tts_node from `_start_segment()`, i.e. once
        # the first text chunk exists, so it can never observe that the text is LATE. Emitting the filler
        # from `llm_node` with a FlushSentinel closes a segment of its own → synthesized and played while
        # the model still thinks, with the reply as segment two. `transcription_node` strips it from what
        # LiveKit forwards (subtitles + chat_ctx); its chat-wall visibility is our own marked event.
        # Full history and the arm/consume contract: `voice/engine/speech/filler_audio.py`.
        def llm_node(self, chat_ctx, tools, model_settings):
            from voice.engine.speech import filler_audio as _fa
            return _fa.llm_node_with_filler(self, Agent.default.llm_node, chat_ctx, tools, model_settings)

        def transcription_node(self, text, model_settings):
            from voice.engine.speech import filler_audio as _fa
            return _fa.transcription_node_without_filler(self, Agent.default.transcription_node,
                                                         text, model_settings)

    agent = ZaelarAgent(instructions=SETTINGS.system_prompt + " " + _lang.reply_directive)
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

    # KICKOFF — only AFTER `ready`. V2-027: we do NOT re-inject the verbose capabilities brief here (widgets/
    # meshkore/cron/architect/messaging). The per-turn system prompt already carries the STATE + the CONCISE
    # resources (`build_flash_system` → `_flash_layer`), so dumping it again in the kickoff was the OLD dump that bloated
    # the FIRST turn (the most latency-sensitive). The greeting only needs the memory-aware first-turn instruction:
    # the brain already greets by name from central memory.
    # FIRST-RUN LANGUAGE ONBOARDING (V2-101): before anything else — no name, no capabilities — a brand-new
    # install must be asked what language to use. The frontend already blocks its whole UI behind a modal for
    # exactly this turn (gated on the SAME `should_detect()`, via GET /api/i18n/state's `chosen` field), so the
    # question HAS to go out now, in English (the product default), and nothing else. `_lang_detect["onboarding"]`
    # tells `_maybe_detect_language` (above) that the NEXT answer is this question's answer, not idle chatter.
    _onboarding_kickoff = False
    try:
        from i18n.init import detect as _d_kickoff
        _onboarding_kickoff = _d_kickoff.should_detect()
    except Exception:
        _onboarding_kickoff = False
    if _onboarding_kickoff:
        _lang_detect["onboarding"] = True
        kickoff_text = (
            "[FIRST RUN — no language has been chosen yet. SPEAK ENGLISH ONLY, regardless of any other "
            "instruction.] I just connected for the very first time. Greet briefly (one short sentence) and "
            "ask what language I'd like you to use — nothing else this turn (no name, no capabilities, no "
            "small talk). Then stop and wait for my answer.")
    else:
        kickoff_text = (f"[The operator's selected interface language is {_lang.native} — SPEAK "
                        f"{_lang.name}.]\n"
                        "I just connected. FIRST turn — SHORT and warm. CHECK YOUR MEMORY first: if you "
                        "already know me (my name), greet me BY NAME and pick up naturally — do NOT ask my "
                        f"name again. If you do NOT know me yet, introduce yourself in one line and ask my name. "
                        f"Reply in {_lang.name}. Two sentences max. Then stop and wait for me.")
    # GUARD: only ONE kickoff per room (V2-047 F8, 23:15 session: TWO “voice engine up” events at 23:15:45 and :46 → two
    # generated greetings). A quick frontend reconnection / LiveKit double dispatch starts two jobs for the SAME
    # room; the second must NOT greet again (the operator heard the greeting repeated). Deterministic, per room,
    # with a short window: if another job greeted this room <8s ago, this one skips it (the session remains alive
    # and handles turns normally; only the duplicate greeting is avoided).
    # CONTINUITY (2026-07-25 bug, operator: “I send it a message and it says ‘what do you need?’”): a RECONNECTION
    # to an IN-PROGRESS conversation must not greet again. Each voice reconnection triggered the “first turn,
    # introduce yourself” kickoff in the middle of an hour-long conversation → absurd “Hello, what do you need?”
    # If the operator spoke recently (recent conversation buffer), do NOT greet: seed context and silently wait
    # for their next turn.
    _resume_window = float(os.getenv("ZAELAR_RESUME_WINDOW_S", "1800"))  # 30 min: reconnection = same session
    _last_conv_age = None
    try:
        from memory import api as _mem
        _last_conv_age = _mem.seconds_since_last_conv()
    except Exception:
        _last_conv_age = None
    if _kickoff_recent(ctx.room.name):
        _emit("brain", "🚫 kickoff duplicado evitado (otra sesión ya saludó esta sala)", role="system")
    elif _last_conv_age is not None and _last_conv_age < _resume_window:
        # IN-PROGRESS session: resume without greeting (the operator is continuing the conversation; do not interrupt with a hello)
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
