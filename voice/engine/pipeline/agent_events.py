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
        # PTT (V2-015): push-to-talk state marks a turn as directed in ZAELAR_ATTENTION=ptt (voice/attention.py).
        if topic == "zaelar-ptt":
            try:
                from voice import attention
                attention.set_ptt(bool(_json.loads(bytes(packet.data).decode("utf-8")).get("active")))
            except Exception:
                pass
            return
        # V2-831 T-18 — the tap's park reaches the input door (`voice/mic_input.py::feeds_stt`): a parked (muted)
        # remote track still yields frames here, and a cloud STT bills every frame it is pushed.
        if topic == "zaelar-tap":
            try:
                from voice import mic_input
                mic_input.set_parked(bool(_json.loads(bytes(packet.data).decode("utf-8")).get("parked")))
            except Exception as te:  # noqa: BLE001
                _ag.logger.warning("zaelar-tap handler: %s", te)
            return
        # THE CHEAP EAR SPEAKS (V2-749). In a wake-word mode the paid STT is PARKED until a free, browser-local
        # recogniser hears the assistant's name (`frontend/app/services/wakeword.js`). TWO phases, because Chrome
        # only finalises when you STOP TALKING (session 5789bad4: five «Johnny»s arrived as ONE final 33.5 s in):
        # `spot` (an INTERIM) opens the tap and the window at once — a false one costs seconds of STT, never an
        # action; `final` is the backstop for the name said alone, which the paid STT came up too late to hear.
        # `before` is what he said BEFORE the name («muéstrame el tiempo, Johnny» must not arrive as «Johnny»),
        # fed to `note_preroll` for `reclaim_ambient_tail` (10 s) to glue back. A browser that lies about the
        # word buys only what typing it into the chat already buys.
        if topic == "zaelar-wake":
            try:
                _d = _json.loads(bytes(packet.data).decode("utf-8"))
                _phase = (_d.get("phase") or "final").strip()
                if _phase == "spot":   # a spot OPENS the tap: open the input too, even if `zaelar-tap` was lost
                    from voice import mic_input
                    mic_input.set_parked(False)
                _txt = (_d.get("text") or "").strip()
                _before = (_d.get("before") or "").strip()
                # V2-802 T-08: the pre-roll exists for words the paid STT did NOT hear (tap parked). With the
                # tap open it already transcribed them, and the browser's ear, which keeps running while our
                # voice plays, sends our own reply as his — measured: the reply glued in front of his turn.
                if _d.get("parked") is False:
                    _before = ""
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
        # SILENCE = OPERATOR decision (V2-088): the 🔊 icon publishes {audio:false|true}. Output disabled → the
        # pipeline takes its text-only branch → ZERO synthesis (cost and latency), «muted» not «volume down».
        # The chat no longer triggers it (V2-054's premise was false); replies always reach the ChatWall through
        # `conversation_item_added`, independent of audio. The input side's twin is `open_mic_door` (T-18).
        if topic == "zaelar-voice":
            try:
                want = bool(_json.loads(bytes(packet.data).decode("utf-8")).get("audio", True))
                session.output.set_audio_enabled(want)
                # The label is what `/api/debug` shows for «no sound»: name the true cause (the icon, V2-088).
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
            # V2-778 F1 — the body lives in `voice/engine/pipeline/agent_events.py`; this branch passes what it reads.
            return receive_typed(txt, _emit=_emit, session=session)
    except Exception as e:
        _ag.logger.warning("chat-text data handler: %s", e)


def open_mic_door(*, session, _emit=None):
    """V2-831 T-18 — installs THE input door: `voice/mic_input.py` decides whether audio may reach the STT, this
    hands it the session's audio INPUT (disabled, the room input drops every frame before VAD and STT). Called
    by the entrypoint ON the session's loop and BEFORE `session.start`; writes from other threads (HTTP routes)
    are hopped onto that loop. Uninstalled on close, only if still ours."""
    from voice import mic_input
    loop = _ag.asyncio._get_running_loop()   # None outside a loop, without raising

    def _set(enabled: bool) -> None:
        if loop is None or loop.is_closed() or _ag.asyncio._get_running_loop() is loop:
            session.input.set_audio_enabled(bool(enabled))
        else:
            loop.call_soon_threadsafe(session.input.set_audio_enabled, bool(enabled))

    mic_input.use_input(_set)
    session.on("close", lambda _ev=None: mic_input.clear_input(_set))
    return _set


def receive_typed(txt: str, *, _emit, session, dev: str = "") -> None:
    """A typed line becomes a turn — from this room's data channel (the voice holder) or from another screen through
    `POST /api/chat` (V2-792), which has no room of its own. One body for both, so a line typed on the phone and one
    typed on the desktop leave the same trace. `dev` names the screen; empty = the holder, as before."""
    _dev = {"dev": dev} if dev else None
    # Written chat/paste is ALWAYS directed to zaelar → open the attention window before generating
    # the response (so the provider gate treats it as an attended turn, not ambient speech).
    try:
        from voice import attention
        attention.note_directed()
        attention.note_typed(text=txt)   # V2-646: a typed turn can never be ambient — see the mute backstop
    except Exception:
        pass
    # OBSERVABILITY (intermittent chat/paste diagnosis): leave a trace showing that the text ARRIVED,
    # and whether generate_reply raises. If a one-second chat poll shows “received” but no reply →
    # generate_reply is at fault (session busy); if “received” is absent → the data packet did not arrive.
    # (2026-07-07)
    _emit("brain", "📥 chat/paste recibido", text=txt, role="user", extra=_dev)
    # V2-773 — HIS LINE ON EVERY WALL. The tab that typed it paints its own bubble; every other
    # tab (his Chrome while an orchestrator drives the agent, the phone) saw only the replies, and
    # `sse.js` had been waiting for a `text-injected` transcript nobody emitted. Same shape as the
    # STT's final transcript, so a typed order and a spoken one leave the same trace on screen.
    _emit("transcript", "text-injected chat", text=txt, role="user", extra=_dev)
    _route_typed(txt, _emit=_emit, session=session)


def open_typed_door(*, _emit, _on_session_loop, session):
    """V2-792 — THE TYPED DOOR FOR EVERY SCREEN. A surface without the voice has no room, so the data channel a typed
    line rides does not exist for it; `POST /api/chat` hands the line to this session instead. The origin is set ON
    the session's loop, around the injection, so the reply task LiveKit spawns inherits it and every card that turn
    opens goes back to the screen that typed. Registered here, cleared by `_on_close` (only if it is still ours)."""
    from voice import screens as _screens

    async def _typed_from_screen(text: str, dev: str) -> None:
        async def _do():
            _tok = _screens.ORIGIN.set(dev)
            try:
                receive_typed(text, _emit=_emit, session=session, dev=dev)
            finally:
                _screens.ORIGIN.reset(_tok)
        await _on_session_loop(_do)

    _screens.register_typed(_typed_from_screen)
    return _typed_from_screen

def _route_typed(txt: str, *, _emit, session) -> None:
    """Turns run in the order he STARTED them: a sentence he began saying before this text is still a
    turn-to-be, and its end-of-turn would interrupt this one (`typed_order`, 2026-10-22)."""
    from nucleo.input import typed as _order
    _since = _ag.time.monotonic()
    if _order.must_wait(_since):
        _emit("brain", "⏸ texto en espera: la voz empezó antes", text=txt, role="system", extra={"cat": "flash"})
        _ag.asyncio.ensure_future(_typed_after_voice(txt, _since, _emit=_emit, session=session))
    else:
        _inject_typed(txt, _emit=_emit, session=session)


def _inject_typed(txt: str, *, _emit, session) -> None:
    # generate_reply() is SYNC (returns a SpeechHandle and schedules the reply itself); calling it
    # directly (wrapping in create_task raised "a coroutine was expected"). (fix 2026-07-07)
    try:
        session.generate_reply(user_input=txt)
    except Exception as ge:
        _emit("alert", "chat/paste generate_reply falló", text=str(ge)[:160])
        _ag.logger.warning("chat-text generate_reply failed: %s", ge)


async def _typed_after_voice(txt: str, since: float, *, _emit, session) -> None:
    """Hold a typed order until the utterance that began before it is a turn, then queue it behind that turn."""
    from nucleo.input import typed as _order
    while _order.must_wait(since, _ag.time.monotonic()):
        await _ag.asyncio.sleep(0.1)
    _emit("brain", "▶️ texto en cola tras la voz", text=txt, role="system",
          extra={"cat": "flash", "held_ms": round((_ag.time.monotonic() - since) * 1000)})
    _inject_typed(txt, _emit=_emit, session=session)


def on_state_change(state: "_ag.State", *, _ONSET_MAX_S, _STATE_TRACE_SAFE, _air, _busy, _emit, _onset) -> None:
    _ag.logger.info("STATE -> %s", state.value)
    speaking = (getattr(state, "value", state) == "speaking")
    _busy["bot"] = speaking
    if speaking:
        _air.on_speaking()
    # RESPONSE ONSET (V2-535): from the end of HIS voice to the first audio that sounds — the wait he lives.
    # Once per wait, only when plausibly this turn's; `covered` = the filler, not the reply, sounded first.
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
    # Wake-word window: our own speech holds/re-anchors an OPEN window, so `window_s()` measures his real
    # silence; it only OPENS one for speech `note_addressed_speech` armed (the kickoff greeting, V2-749b).
    try:
        from voice import attention as _attn
        _attn.note_bot_speech(speaking)
    except Exception:
        pass
    # Nothing sounds now: close flows that finished while the reply was narrated (`drain_pending_flow_closes`).
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
    # VOICE OBSERVABILITY: his VAD edges and barge-in, so «noise cut speech» can be diagnosed.
    if new == "speaking":
        if was_bot_speaking:
            # ONLY a barge-in may carry active() (audit 2026-08-16): it interrupts a turn that HAS a trace;
            # the voice edges below precede theirs, so labelling them would pick the previous turn (voice/trace.py).
            from voice import trace as _trace
            _tid = _trace.active()
            # V2-661: `edge` holds the orb's ring while his voice is ACTIVE and re-arms it after (sse.js).
            _emit("vad", "✂️ barge-in — voz pisa la locución (LiveKit corta el TTS)",
                  role="user", extra={"over_agent": True, "edge": "on", **({"trace": _tid} if _tid else {})})
        else:
            _emit("vad", "🎤 voz detectada (VAD)", role="user", extra={"over_agent": False, "edge": "on"})
        # V2-660 — the window measures his SILENCE, which ends HERE, not at the STT's final.
        try:
            from voice import attention as _attn_onset
            _attn_onset.note_speech_onset()
        except Exception:
            pass
        from nucleo.input import typed as _order_on
        _order_on.note_onset()
    elif new == "listening":
        _emit("vad", "… fin de voz", role="user", extra={"edge": "off"})
        _onset["voice_ended"] = _ag.time.monotonic()   # the near end of the wait the operator is about to live
        # V2-661 — his SILENCE starts here; the next rising edge decides whether it continues this utterance.
        try:
            from voice import attention as _attn_end
            _attn_end.note_speech_end()
        except Exception:
            pass
        from nucleo.input import typed as _order_end
        _order_end.note_end()


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
    # INSTRUMENTATION (V2-047 F7): `say` with whether speech/a live turn existed at start. `voice/proactive.py`
    # serialises notifies (FIFO, 2026-08-31), so a frequent `bot_in_flight=True` here means that queue broke.
    _bot0, _usr0 = _busy["bot"], _busy["user"]
    try:
        _emit("tts", "say (entrega proactiva)", text=(text or "")[:120], role="assistant",
              extra={"bot_in_flight": bool(_bot0), "user_in_flight": bool(_usr0)})
    except Exception:
        pass
    _owner, _queued, _t0 = _speech_of_this_task(), [], _ag.time.perf_counter()

    async def _do_say():
        handle = session.say((text or "").strip(), allow_interruptions=True)   # call AND await on the session loop
        if not _behind_its_own_turn(_owner, _emit, _queued):
            await handle
    await _on_session_loop(_do_say)
    if _queued:
        return
    # The REAL playout time next to TTSMetrics' audio length (2026-08-31): ≪ means the delivery was cut.
    try:
        _emit("tts", "say (entrega proactiva) COMPLETADA", role="assistant",
              extra={"playout_ms": round((_ag.time.perf_counter() - _t0) * 1000)})
    except Exception:
        pass


def _behind_its_own_turn(owner, _emit, queued: list) -> bool:
    """A CIRCULAR WAIT (V2-831 T-19 R13): from inside a speech's own generation (a hard close's receipt) the say
    queues BEHIND that speech, which cannot end until we return — awaiting it wedged the session for good. It plays
    after the turn; nobody waits on it."""
    if owner is None or owner.done():
        return False
    _emit("tts", "say (entrega proactiva) PROGRAMADA tras el turno en curso", role="assistant",
          extra={"owner_speech": getattr(owner, "id", "")})
    queued.append(owner)
    return True


def _speech_of_this_task():
    """The LiveKit speech whose generation this runs inside, or None (LiveKit guards function tools only)."""
    from livekit.agents.voice.agent_activity import _SpeechHandleContextVar
    return _SpeechHandleContextVar.get(None)


def _on_close(ev, *, _account_limits, _close_account_session, _emit, _proactive, _speak, boot, _typed=None) -> None:
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
        from voice import screens as _screens
        # V2-792: only OUR door. When the voice moves, the new room's session registers before this one closes.
        if _typed is not None:
            _screens.clear_typed(_typed)
    except Exception as e:  # noqa: BLE001
        _ag.logger.warning("typed door not cleared: %s", e)
    try:
        _account_limits.clear_closer(_close_account_session)
    except Exception:
        pass
    boot.close()


def _on_item(ev, *, _emit) -> None:
    item = ev.item
    role, text = getattr(item, "role", None), getattr(item, "text_content", None)
    if role == "user":
        from nucleo.input import typed as _order
        _order.note_committed()   # whatever he was saying is a turn now: a typed order held behind it may go
    # V2-773 — already on the wall (reply_wall.surface): not twice.
    if role == "assistant" and text and not _ag._reply_wall.already_surfaced(text):
        # V2-831 T-23 — the trace of the turn that CREATED these words: the item lands when the PLAYOUT ends,
        # often inside the next turn, so `active()` alone named the wrong one (pass 7: M3's NASDAQ line as M4's).
        from voice import trace as _trace
        _h = _speech_of_this_task()
        _tid = _trace.of_speech(getattr(_h, "id", "")) or _trace.active()
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
        # → observer/SSE: the chat wall + the front-end voice-command fast path.
        _emit("transcript", "🗣", text=ev.transcript, role="user")
    else:
        _emit("interim", "…", text=ev.transcript, role="user")   # live, UI-only (dedup/no-disk in observer)
        # INSTANT wake-word spotting (2026-09-09) over the interim stream: the orb lights on HEARING; signal only.
        try:
            from voice import attention as _attn_spot
            if _attn_spot.mode() in ("smart", "wakeword") and _attn_spot.has_wakeword(ev.transcript):
                _attn_spot.note_wakeword_spotted()
        except Exception:
            pass
