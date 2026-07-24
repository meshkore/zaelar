#
# PROACTIVE DELIVERY — how zaelar reaches the operator on its OWN initiative (no user turn), e.g. when a native
# Hermes cron fires. Two surfaces, brain-agnostic:
#   • UI  — always: emit an SSE event ("notify") so the frontend shows it (chat wall + toast) whenever a browser
#           is connected, even with no active voice turn.
#   • VOICE— if a live voice session registered a speaker, speak the text through the TTS stage.
#
# The voice pipeline is per-session; this registry lets a PROCESS-LEVEL caller (the cron ticker) speak through
# whatever session is live right now, and no-op the voice half when none is (the UI half still fires).
#
import asyncio
import os

from loguru import logger

_speaker = None            # async callable(text) -> None, set by the live voice session (voice/engine entrypoint)
_busy_probe = None         # callable() -> bool, True if the operator/bot is mid-turn right now (engine-provided)


def register_speaker(fn) -> None:
    """The live voice session registers how to speak proactively (LiveKit: session.say via voice/engine)."""
    global _speaker
    _speaker = fn


def register_busy_probe(fn) -> None:
    """The live session registers a probe telling whether a turn is in flight (bot speaking or user talking), so a
    proactive delivery waits for a gap instead of talking over the operator. Engine-agnostic; None → assume free."""
    global _busy_probe
    _busy_probe = fn


def clear_speaker(fn=None) -> None:
    """Session teardown clears it (only if it still owns the slot, to avoid a race with a newer session)."""
    global _speaker, _busy_probe
    if fn is None or _speaker is fn:
        _speaker = None
        _busy_probe = None


def has_voice() -> bool:
    return _speaker is not None


async def notify(title: str, text: str, *, speak: bool = True, kind: str = "notify") -> None:
    """Deliver a proactive message: UI always, voice if a session is live. Best-effort — never raises."""
    text = (text or "").strip()
    if not text:
        return
    try:
        from voice.observer import emit
        emit(kind, ("🔔 " + (title or "zaelar"))[:60], text=text, role="assistant", extra={"title": title or ""})
    except Exception as e:
        logger.warning(f"proactive notify (UI) failed: {e}")
    # SPEECH GATE: the UI keeps the raw text (debug), but the SPEAKER only ever gets clean operator-facing prose.
    # If nothing speakable survives (pure metadata / markdown / empty), stay silent on voice — the UI already has it.
    if speak and _speaker is not None:
        from voice import speech
        spoken = speech.sanitize(text)
        if not spoken:
            return
        # PREEMPCIÓN (INI-008 F2): la voz del OPERADOR manda. No se le habla encima — ni con un turno de usuario
        # abierto ni pisando la cola del TTS del bot. Esperamos un hueco de silencio; si la conversación no da
        # tregua en PROACTIVE_MAX_WAIT, el mensaje NO se pierde: entra como nota [SISTEMA] al siguiente turno
        # (el cerebro lo dirá él mismo, en contexto). La UI ya lo mostró arriba en cualquier caso.
        if not await _wait_for_quiet():
            try:
                from voice import brain_notes
                brain_notes.push(f"[SISTEMA] Entrega proactiva pendiente (no hubo silencio para hablarla): {spoken}")
                logger.info("proactive: conversation busy → delivered as a [SISTEMA] note instead of talking over")
            except Exception as e:
                logger.warning(f"proactive fallback note failed: {e}")
            return
        try:
            r = _speaker(spoken)
            if asyncio.iscoroutine(r):
                await r
        except Exception as e:
            logger.warning(f"proactive notify (voice) failed: {e}")


# Cuánto esperamos un hueco de silencio antes de degradar a nota [SISTEMA]; y el respiro tras la voz del bot.
PROACTIVE_MAX_WAIT = float(os.getenv("PROACTIVE_MAX_WAIT", "45"))
_BOT_GRACE_SECS = 1.2


async def _wait_for_quiet(timeout: float | None = None) -> bool:
    """Espera (polling suave) a que NO haya turno en vuelo (bot hablando o usuario hablando), consultando el
    busy-probe que registró la sesión viva. True = hay hueco, habla ya. False = timeout, la conversación no dio
    tregua. Sin probe registrado (sesión sin instrumentar) → asumimos hueco: LiveKit gestiona el barge-in del
    operador vía session.say(allow_interruptions=True), así que hablar no lo pisa de forma dura."""
    import time as _t
    timeout = PROACTIVE_MAX_WAIT if timeout is None else timeout
    t0 = _t.time()
    while _t.time() - t0 < timeout:
        try:
            busy = bool(_busy_probe()) if _busy_probe is not None else False
        except Exception:
            busy = False
        if not busy:
            return True
        await asyncio.sleep(0.3)
    return False
