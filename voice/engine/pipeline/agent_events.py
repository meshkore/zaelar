"""The voice session's EVENT HANDLERS, lifted out of `entrypoint` (V2-778 F1, 2026-10-01).

`voice/engine/pipeline/agent.py::entrypoint` was 729 lines, most of them closures registered on the session and
the room. Each one lives here now as a plain function: what it closed over is passed as keyword arguments by the
thin closure that stays registered in `entrypoint`, at CALL time — the same late binding a closure has. Every
module-level name of `agent` it reads is read through it (`_ag.<name>`), so a patch on `agent` still governs it.
"""
from __future__ import annotations

from voice.engine.pipeline import agent as _ag


def _on_data(packet, *, _emit, _json, _wake, session) -> None:
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
        # THE CHEAP EAR SPEAKS (V2-749). In a wake-word mode the paid STT is PARKED: no audio leaves
        # the browser until a free, browser-local recogniser hears the assistant's own name
        # (`frontend/app/services/wakeword.js`). It arrives in TWO phases, and the split is the whole
        # difference between a wake word that works and one that looks broken.
        #
        # ⚠️ WHY TWO (measured 2026-09-22, session 5789bad4). The first build only believed a FINAL
        # result — the safe choice against a fragment the recogniser later rewrites. But Chrome only
        # finalises when you STOP TALKING, so the operator, who kept going, had his five «Johnny»s
        # delivered as ONE final **33.5 s after the session started**: «he estado diciendo la palabra
        # Johnny mucho tiempo y la primera vez le ha costado mucho… si dicen Johnny cuatro veces
        # después de darle el botón de Start y no funciona se van a preocupar». The latency of a
        # finals-only spot is not a number, it is «however long he keeps speaking».
        #
        # `spot` (from an INTERIM) is cheap and reversible: it opens the tap and the window, and the
        # ring lights AT ONCE. A false one costs a few seconds of STT, never a wrong action.
        # `final` is the BACKSTOP for the one case the spot alone leaves silent — he said the name and
        # nothing else, so the paid STT, which only came up mid-word, heard nothing to answer.
        #
        # `before` is the half of the sentence that came BEFORE the name and is the point of doing it
        # this way rather than like a smart speaker: «muéstrame el tiempo, Johnny» must not arrive as
        # «Johnny». It feeds `note_preroll`, which is the tail `reclaim_ambient_tail` (10 s) already
        # reclaims — the turn right behind it glues the two back together with no new branch.
        #
        # A browser that lies about having heard the word buys the same turn a browser that types it
        # into the chat already buys: the exposure this seam already had.
        if topic == "zaelar-wake":
            try:
                _d = _json.loads(bytes(packet.data).decode("utf-8"))
                _phase = (_d.get("phase") or "final").strip()
                _txt = (_d.get("text") or "").strip()
                _before = (_d.get("before") or "").strip()
                from voice import attention as _attn_wake
                if _phase == "spot":
                    if _before:
                        _attn_wake.note_preroll(_before)
                    # This is PERMISSION, not a hint: the tap is open now and whatever he says next
                    # must land inside a window, or the paid STT would transcribe it into a discard.
                    _attn_wake.note_directed()
                    _emit("ambient", "👂 palabra de activación (oído local)",
                          extra={"directed": True, "reason": "wakeword_spot",
                                 "window_s": _attn_wake.window_s(), "before": _before[:200]})
                    _wake["spot_at"] = _ag.time.time()
                    return
                if not _txt:
                    return
                # The backstop decides LATE on purpose: the paid STT's own transcript of the tail of
                # this utterance can land either side of this packet, and answering twice is worse
                # than answering once a second later.
                async def _wake_backstop(text: str, spot_at: float):
                    await _ag.asyncio.sleep(1.2)
                    if _wake["last_user_final"] > spot_at:
                        _emit("brain", "🤐 respaldo de palabra descartado — el STT de pago ya tiene el turno",
                              text=text[:120], role="system")
                        return
                    _attn_wake.drop_preroll()   # `text` already carries what the spot sent as `before`
                    _emit("brain", "📥 respaldo de palabra de activación (oído local)", text=text, role="user")
                    session.generate_reply(user_input=text)
                if _wake["spot_at"]:
                    _ag.asyncio.create_task(_wake_backstop(_txt, _wake["spot_at"]))
                    _wake["spot_at"] = 0.0
                    return
                # No spot ever fired for this utterance (the name only surfaced in the final): the
                # browser owns the turn outright, exactly as the first build did.
                if _before:
                    _attn_wake.note_preroll(_before)
                _emit("brain", "📥 palabra de activación (oído local)", text=_txt, role="user",
                      extra={"before": _before[:200], "src": "browser-spotter"})
                session.generate_reply(user_input=_txt)
            except Exception as we:  # noqa: BLE001
                _emit("alert", "zaelar-wake falló", text=str(we)[:160])
                _ag.logger.warning("zaelar-wake handler: %s", we)
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
                _ag.logger.warning("zaelar-voice toggle failed: %s", ve)
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
                attention.note_typed()   # V2-646: a typed turn can never be ambient — see the mute backstop
            except Exception:
                pass
            # OBSERVABILITY (intermittent chat/paste diagnosis): leave a trace showing that the text ARRIVED,
            # and whether generate_reply raises. If a one-second chat poll shows “received” but no reply →
            # generate_reply is at fault (session busy); if “received” is absent → the data packet did not arrive.
            # (2026-07-07)
            _emit("brain", "📥 chat/paste recibido", text=txt, role="user")
            # V2-773 — HIS LINE ON EVERY WALL. The tab that typed it paints its own bubble; every other
            # tab (his Chrome while an orchestrator drives the agent, the phone) saw only the replies, and
            # `sse.js` had been waiting for a `text-injected` transcript nobody emitted. Same shape as the
            # STT's final transcript, so a typed order and a spoken one leave the same trace on screen.
            _emit("transcript", "text-injected chat", text=txt, role="user")
            # generate_reply() is SYNC (returns a SpeechHandle and schedules the reply itself); calling it
            # directly (wrapping in create_task raised "a coroutine was expected"). (fix 2026-07-07)
            try:
                session.generate_reply(user_input=txt)
            except Exception as ge:
                _emit("alert", "chat/paste generate_reply falló", text=str(ge)[:160])
                _ag.logger.warning("chat-text generate_reply failed: %s", ge)
    except Exception as e:
        _ag.logger.warning("chat-text data handler: %s", e)


def on_state_change(state: "_ag.State", *, _ONSET_MAX_S, _STATE_TRACE_SAFE, _air, _busy, _emit, _onset) -> None:
    _ag.logger.info("STATE -> %s", state.value)
    speaking = (getattr(state, "value", state) == "speaking")
    _busy["bot"] = speaking
    if speaking:
        _air.on_speaking()
    # RESPONSE ONSET (V2-535) — the clock the PERSON lives: from the moment their voice ends to the moment
    # audio actually sounds. Both edges were already emitted, in two different handlers, and nobody paired
    # them: TTFT and the TTS ttfb each measure a leg, and neither is the wait. Reported ONCE per wait (the
    # edge is cleared) so a segmented reply does not report its second segment as a second onset, and only
    # when the wait is plausibly this turn's — a proactive delivery minutes later is not an answer to
    # anything. `covered` says whether what sounded first was the filler or the reply itself, which is the
    # difference between «it answered in 2 s» and «it made a noise in 1.1 s and answered in 2 s».
    if speaking and _onset.get("voice_ended"):
        _ended = _onset["voice_ended"]
        _gap = _ag.time.monotonic() - _ended
        _onset["voice_ended"] = 0.0
        if _gap <= _ONSET_MAX_S:
            try:
                from voice.engine.speech import filler_audio as _fa
                _cov = _fa.last_fired_at() >= _ended       # it sounded DURING this wait, not in an older one
            except Exception:
                _cov = False
            _emit("perf", f"⏱ primer audio {int(_gap * 1000)} ms desde que dejó de hablar"
                          + (" (relleno)" if _cov else ""),
                  role="system", extra={"cat": "system", "module": "voice", "func": "onset",
                                        "onset_ms": round(_gap * 1000, 1), "covered_by_filler": _cov})
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
    # Wake-word window: zaelar's own speech holds/re-anchors an OPEN conversation window, so `window_s()`
    # measures real silence after its last word (2026-09-09). It only OPENS one for an utterance that
    # `note_addressed_speech` armed — which, since V2-749b, includes the kickoff greeting in the modes
    # where the tap parks: there the greeting asks a question into a microphone nobody would open.
    try:
        from voice import attention as _attn
        _attn.note_bot_speech(speaking)
    except Exception:
        pass
    # Nothing is still sounding at this instant — this is the safe point to close any flow that finished
    # generate text WHILE the bot was still narrating the response (operator report, 2026-08-16: the turn
    # disappeared from the master during TTS). See `nucleo.py::_maybe_close_flow`/`drain_pending_flow_closes`.
    if not speaking:
        try:
            from voice.engine.llm.providers.nucleo import drain_pending_flow_closes
            drain_pending_flow_closes()
        except Exception:
            pass


def _on_user_state(ev, *, _busy, _emit, _onset, sm) -> None:
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
            # V2-661: `edge` is the client's key — the ring on the orb holds while his voice is ACTIVE
            # and re-arms its window when it stops (sse.js), instead of dying mid-sentence on a timer.
            _emit("vad", "✂️ barge-in — voz pisa la locución (LiveKit corta el TTS)",
                  role="user", extra={"over_agent": True, "edge": "on", **({"trace": _tid} if _tid else {})})
        else:
            _emit("vad", "🎤 voz detectada (VAD)", role="user", extra={"over_agent": False, "edge": "on"})
        # V2-660 — the window measures the operator's SILENCE, which ends HERE, not when the STT
        # finalizes the sentence (a 4-second sentence begun inside a 5 s window used to be judged outside it).
        try:
            from voice import attention as _attn_onset
            _attn_onset.note_speech_onset()
        except Exception:
            pass
    elif new == "listening":
        _emit("vad", "… fin de voz", role="user", extra={"edge": "off"})
        _onset["voice_ended"] = _ag.time.monotonic()   # the near end of the wait the operator is about to live
        # V2-661 — his SILENCE starts here; the next rising edge decides whether it continues this utterance.
        try:
            from voice import attention as _attn_end
            _attn_end.note_speech_end()
        except Exception:
            pass


def _int_kwargs() -> dict:
    out: dict = {}
    def _f(name):
        v = (_ag.os.getenv(name) or "").strip()
        try:
            return float(v) if v else None
        except ValueError:
            return None
    def _i(name):
        v = (_ag.os.getenv(name) or "").strip()
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
    resume = (_ag.os.getenv("ZAELAR_RESUME_FALSE_INTERRUPTION") or "").strip().lower()
    if resume:
        out["resume_false_interruption"] = resume in ("1", "true", "yes", "on")
    return out


async def _speak(text: str, *, _busy, _emit, _on_session_loop, session) -> None:
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
    _t0 = _ag.time.perf_counter()
    await _on_session_loop(_do_say)
    # OBSERVABILITY the operator asked for (2026-08-31): the delivery's REAL playout time, next to the
    # synthesized audio length TTSMetrics already reports. `playout_ms` ≪ the audio duration is the
    # one-glance tell of a cut — exactly the comparison that took a log dig to make today.
    try:
        _emit("tts", "say (entrega proactiva) COMPLETADA", role="assistant",
              extra={"playout_ms": round((_ag.time.perf_counter() - _t0) * 1000)})
    except Exception:
        pass


def _on_close(ev, *, _account_limits, _close_account_session, _emit, _proactive, _speak, boot) -> None:
    _emit("session", "session closed", role="system")
    # Closing ON AN ERROR is a death, not a goodbye → record + alert + recycle (see session_health).
    err = getattr(ev, "error", None)
    if err is not None:
        from .session_health import on_session_dead
        on_session_dead(err, _emit)
    try:
        _proactive.clear_speaker(_speak)
    except Exception:
        pass
    try:
        _account_limits.clear_closer(_close_account_session)
    except Exception:
        pass
    boot.close()


def _on_item(ev, *, _emit) -> None:
    item = ev.item
    role, text = getattr(item, "role", None), getattr(item, "text_content", None)
    # V2-773 — already on the wall because the voice could not say it (reply_wall.surface): not twice.
    if role == "assistant" and text and not _ag._reply_wall.already_surfaced(text):
        # SAFE to label with active() (source audit 2026-08-16, unlike the OPERATOR transcript below in
        # _on_transcript): the assistant item is added AFTER the turn's LLM+TTS chain has run — its trace
        # already exists; it is not about to begin.
        from voice import trace as _trace
        _tid = _trace.active()
        _emit("transcript", "zaelar", text=text, role="assistant",
              extra=({"trace": _tid} if _tid else None))
        # The finished reply sizes the wake-word window it re-anchors (2026-09-09, dynamic 4-15s).
        try:
            from voice import attention as _attn_w
            _attn_w.note_reply(text)
        except Exception:
            pass


def _on_transcript(ev, *, _emit, _wake) -> None:
    if ev.is_final:
        _wake["last_user_final"] = _ag.time.time()
        # → observer/SSE: chat wall + the front-end voice-command fast-path (show/close widgets) consume this.
        _emit("transcript", "🗣", text=ev.transcript, role="user")
    else:
        _emit("interim", "…", text=ev.transcript, role="user")   # live, UI-only (dedup/no-disk in observer)
        # INSTANT wake-word spotting (2026-09-09): a regex over the interim stream — the orb lights the
        # moment the word is HEARD, not after STT-final + the turn gate (measured 1-3s late). Signal only:
        # the turn's real verdict is still the gate's.
        try:
            from voice import attention as _attn_spot
            if _attn_spot.mode() in ("smart", "wakeword") and _attn_spot.has_wakeword(ev.transcript):
                _attn_spot.note_wakeword_spotted()
        except Exception:
            pass
