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
_ephemeral_speaker = None  # async callable(text) -> None — same TTS, but NEVER added to conversation history
                            # (LiveKit `session.say(..., add_to_chat_ctx=False)`) — see `ephemeral_speaker()`
_busy_probe = None         # callable() -> bool, True if the operator/bot is mid-turn right now (engine-provided)
_user_probe = None         # callable() -> bool, True if the OPERATOR is speaking RIGHT NOW (engine-provided)
_bot_probe = None          # callable() -> bool, True if the BOT is speaking RIGHT NOW (engine-provided)


def register_speaker(fn) -> None:
    """The live voice session registers how to speak proactively (LiveKit: session.say via voice/engine)."""
    global _speaker
    _speaker = fn


def register_ephemeral_speaker(fn) -> None:
    """The live voice session registers the EPHEMERAL half of the same channel — see `ephemeral_speaker()`."""
    global _ephemeral_speaker
    _ephemeral_speaker = fn


def register_busy_probe(fn) -> None:
    """The live session registers a probe telling whether a turn is in flight (bot speaking or user talking), so a
    proactive delivery waits for a gap instead of talking over the operator. Engine-agnostic; None → assume free."""
    global _busy_probe
    _busy_probe = fn


def register_user_probe(fn) -> None:
    """La sesión viva registra si el OPERADOR está hablando AHORA MISMO.

    Distinto del busy-probe a propósito: aquél es «hay algo en vuelo» (bot O usuario) y sirve para que una entrega
    proactiva espere hueco. Éste separa la mitad que NO admite excepción — al operador **no se le habla encima
    nunca**, ni siquiera con un relleno de espera, que es justo el caso que el busy-probe no cubría porque el
    relleno se salta la espera de hueco por diseño (`speaker()`)."""
    global _user_probe
    _user_probe = fn


def user_speaking() -> bool:
    """True si el operador está hablando ahora. Sin probe (sesión sin instrumentar, tests) → False: asumir que
    habla y callarse dejaría mudo al agente en cualquier entorno sin instrumentar, que es peor."""
    try:
        return bool(_user_probe()) if _user_probe is not None else False
    except Exception:
        return False


def register_bot_probe(fn) -> None:
    """La sesión viva registra si el BOT está hablando (TTS en curso) AHORA MISMO — distinto del busy-probe (bot
    O usuario) porque `nucleo.py::_maybe_close_flow` (2026-08-16) necesita saber específicamente si SU PROPIA
    locución sigue sonando antes de cerrar el flujo, no si hay cualquier cosa en vuelo."""
    global _bot_probe
    _bot_probe = fn


def bot_speaking() -> bool:
    """True si el bot está hablando ahora. Sin probe (sesión sin instrumentar, tests) → False: cerrar el flujo de
    inmediato es el comportamiento de siempre en un entorno sin pipeline de voz real."""
    try:
        return bool(_bot_probe()) if _bot_probe is not None else False
    except Exception:
        return False


def clear_speaker(fn=None) -> None:
    """Session teardown clears it (only if it still owns the slot, to avoid a race with a newer session). Clears
    the ephemeral speaker too — the same session registers both at the same point (`agent.py`), so they share one
    lifecycle; matched by the SPEAKER's identity, not the ephemeral one's (the caller only ever has `fn`=`_speak`)."""
    global _speaker, _ephemeral_speaker, _busy_probe, _user_probe, _bot_probe
    if fn is None or _speaker is fn:
        _speaker = None
        _ephemeral_speaker = None
        _busy_probe = None
        _user_probe = None
        _bot_probe = None


def has_voice() -> bool:
    return _speaker is not None


def speaker():
    """El hablador FUERA DE BANDA de la sesión viva (`session.say`), o None si no hay sesión.

    Existe para contenido con SENTIDO propio que debe sonar YA y no puede esperar al agregador de frases del
    stream del modelo — la pregunta aclaratoria del juez de completitud (V2-102), el aviso de fragmento perdido
    o el "sigo aquí" del acumulador (V2-096). Cada llamada AÑADE un item a la conversación de LiveKit
    (`session.say(..., add_to_chat_ctx=True)`, el default) — correcto aquí: esto SÍ es algo que decir de verdad.

    Para el LEAD-IN neutro del FlashBrain (V2-093, «Mmm…», «A ver…») usa `ephemeral_speaker()`, no este —
    ver su docstring para el porqué exacto (V2-114, 2026-08-17)."""
    return _speaker


def ephemeral_speaker():
    """La mitad EFÍMERA del mismo canal fuera de banda: suena igual (`session.say`) pero con
    `add_to_chat_ctx=False`, así que NUNCA entra en el historial de conversación de LiveKit ni dispara
    `conversation_item_added` — el orden en que LiveKit decide disparar ese evento es lo que causó el bug
    original (V2-093, 2026-08-17): un filler dicho por `speaker()` normal («Déjame que mire…») acababa
    apareciendo DESPUÉS de una respuesta que ya había resuelto («¡Hola! ¿Cómo va todo?»), porque el orden de
    `conversation_item_added` no es el orden en que se decidió cada cosa. `None` si no hay sesión viva.

    Esto NO significa que el relleno sea invisible — SÍ pertenece al muro de chat y a la observabilidad (es una
    frase real que el agente dijo), solo que su visibilidad la empuja el propio `lead_in_filler.py` de forma
    EXPLÍCITA (`kind="filler"`, síncrono, en el momento exacto en que se decide — SIEMPRE antes de que exista
    texto de respuesta real), no delegada en el mecanismo de LiveKit que causó el desorden. `speaker()` sigue
    siendo el correcto para cualquier locución fuera de banda que SÍ pueda depender del orden natural de
    LiveKit porque no compite con una respuesta en curso (V2-102, V2-096, `notify()`)."""
    return _ephemeral_speaker


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
    # NO VOICE SESSION = the conversation never hears about it. V2-217, measured 2026-08-20: `brain_notes.push`
    # lived INSIDE the speech branch below, so with no live speaker a proactive delivery reached the
    # observability panel and stopped there. On the TEXT channel — which is what the use-case harness drives,
    # and what a chat-only operator uses — that is EVERY proactive delivery: the loop's stall notice
    # (`worker.stuck`), a worker finishing, the messaging connector, Architect. The harness kept measuring
    # `stuck/nudge` firing in the events while the turn went on saying «sigo con ello», and the two facts were
    # the same fact.
    #
    # The note is an INSTRUCTION, never the bare phrase (V2-214): its reader is the AGENT at a later moment, so
    # handing it prose reads as something to file rather than something to say.
    if not (speak and _speaker is not None):
        try:
            from voice import brain_notes
            brain_notes.push(f"[SISTEMA] Aviso para el operador ({title or 'zaelar'}): {text[:400]} "
                             f"Díselo en ESTE turno con tus palabras — todavía no lo sabe.")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"proactive notify (nota al cerebro) failed: {e}")
        return
    # SPEECH GATE: the UI keeps the raw text (debug), but the SPEAKER only ever gets clean operator-facing prose.
    # If nothing speakable survives (pure metadata / markdown / empty), stay silent on voice — the UI already has it.
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
