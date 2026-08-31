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
import threading
import time

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


async def notify(title: str, text: str, *, speak: bool = True, kind: str = "notify",
                 key: str = "") -> None:
    """Deliver a proactive message: UI always, voice if a session is live. Best-effort — never raises."""
    text = (text or "").strip()
    if not text:
        return
    try:
        from voice.observer import emit
        emit(kind, ("🔔 " + (title or "zaelar"))[:60], text=text, role="assistant", extra={"title": title or ""})
    except Exception as e:
        logger.warning(f"proactive notify (UI) failed: {e}")
    # NO VOICE SESSION = the conversation never hears about it. V2-220, measured 2026-08-20: `brain_notes.push`
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
                             f"Díselo en ESTE turno con tus palabras — todavía no lo sabe.", key=key)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"proactive notify (nota al cerebro) failed: {e}")
        return
    # SPEECH GATE: the UI keeps the raw text (debug), but the SPEAKER only ever gets clean operator-facing prose.
    # If nothing speakable survives (pure metadata / markdown / empty), stay silent on voice — the UI already has it.
    from voice import speech
    spoken = speech.sanitize(text)
    if not spoken:
        return
    # PREEMPCIÓN (INI-008 F2) + COLA (2026-08-31): la voz del OPERADOR manda, y los mensajes proactivos salen
    # DE UNO EN UNO y en orden de llegada — ver la cola de tickets de abajo. Cada mensaje espera su turno, y ya
    # con el turno espera un hueco de silencio; si el total no da tregua, el mensaje NO se pierde: entra como
    # nota [SISTEMA] al siguiente turno (el cerebro lo dirá él mismo, en contexto). La UI ya lo mostró arriba.
    def _degrade(reason: str) -> None:
        try:
            from voice import brain_notes
            brain_notes.push(f"[SISTEMA] Entrega proactiva pendiente ({reason}): {spoken}", key=key)
            logger.info(f"proactive: {reason} → delivered as a [SISTEMA] note instead of talking over")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"proactive fallback note failed: {e}")

    t_arrival = time.monotonic()
    ticket = _take_ticket()
    if not await asyncio.to_thread(_wait_turn, ticket, _QUEUE_MAX_WAIT):
        _degrade("la cola de entregas no avanzó a tiempo")
        return
    try:
        # The budget counts from ARRIVAL: a message that already queued behind a long explanation gets the
        # remainder, not a fresh 45 s — otherwise a burst of finishes could hold the floor for minutes.
        left = PROACTIVE_MAX_WAIT - (time.monotonic() - t_arrival)
        if not await _wait_for_quiet(max(0.0, left)):
            _degrade("no hubo silencio para hablarla")
            return
        # THE BREATH between two queued deliveries (`_BOT_GRACE_SECS` — defined since INI-008, used by nobody
        # until 2026-08-31). Back-to-back, message B would start the very instant A's playout ends: two notices
        # in a burst that sound like one. Only paid when the previous delivery just ended; a floor that has
        # been quiet for a while speaks immediately.
        pause = _BOT_GRACE_SECS - (time.monotonic() - _last_spoke[0])
        if pause > 0:
            await asyncio.sleep(pause)
        try:
            r = _speaker(spoken)
            if asyncio.iscoroutine(r):
                await r
        finally:
            _last_spoke[0] = time.monotonic()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"proactive notify (voice) failed: {e}")
        # VISIBLE, not just logged (operator, 2026-08-31: «si necesitas más observabilidad en la gestión de la
        # voz, añádela»). A delivery that died mid-say was a WARNING line in server.log and nothing anywhere the
        # operator looks — today's cut («A coroutine object is required») sat there for an hour while the session
        # timeline showed a normal-looking say. An error event lands in the session file and the master.
        try:
            from voice.observer import emit as _emit_err
            _emit_err("error", "⚠️ entrega proactiva por VOZ falló a media locución", text=str(e)[:200],
                      role="system", extra={"spoken": spoken[:120]})
        except Exception:
            pass
    finally:
        _release(ticket)   # always: a held ticket after a crash would mute every delivery that follows


# Cuánto esperamos un hueco de silencio antes de degradar a nota [SISTEMA]; y el respiro tras la voz del bot.
PROACTIVE_MAX_WAIT = float(os.getenv("PROACTIVE_MAX_WAIT", "45"))
_BOT_GRACE_SECS = 1.2

# ── ONE MESSAGE AT A TIME: the delivery queue (operator's spec, 2026-08-31) ─────────────────────────────────
# «El propio FlashBrain es quien se encarga de comunicarse con el usuario … tiene que tener un buffer: cuando ya
# se lo ha explicado, le manda otro. Si hay dos tareas a la vez y terminan simultáneamente, primero se informará
# de una y después de la segunda.»
#
# Until now NOTHING serialized concurrent notifies. Each one waited for quiet on its own, and two workers
# finishing in the same instant both saw silence and both called `session.say` — whatever order and overlap came
# out was LiveKit's internal scheduling, not a decision of ours. The V2-047 F7 instrumentation in
# `voice/engine/pipeline/agent.py` had already named the fix («el fix es SERIALIZAR: encolar el say hasta que el
# handle vivo acabe») and stayed telemetry-only. This is that queue.
#
# Strict ARRIVAL order, guaranteed by ticket — not by lock-acquisition luck. Cross-LOOP on purpose: notifies are
# awaited from whatever loop their caller runs on (uvicorn workers, the orchestrator, the messaging connector),
# so an `asyncio.Lock` — which binds to one loop — would be exactly the «attached to a different loop» class of
# bug this file just got cured of. Plain threading primitives, entered via `asyncio.to_thread`, care about none
# of that.
#
# A message NEVER dies in the queue: whoever cannot speak in time degrades to the same `[SISTEMA]` note as
# always (the brain says it itself, in context, next turn) and ABANDONS its ticket, so the queue cannot wedge
# behind a slot nobody will ever fill. And the busy re-check runs AFTER winning the turn — the silence that let
# the previous message start says nothing about the moment this one gets to speak.
_QUEUE_MAX_WAIT = float(os.getenv("PROACTIVE_QUEUE_MAX_WAIT", "180"))   # cap on waiting for the turn itself
_queue_cv = threading.Condition()
_next_ticket = [0]      # next ticket to hand out
_serving = [0]          # ticket allowed to speak right now
_abandoned: set = set()  # tickets that gave up while waiting (their turn is skipped, never held)
_last_spoke = [0.0]     # monotonic end of the last spoken delivery — the breath between two queued messages
#                         cannot come from OBSERVING busy (the next in line is blocked in `_wait_turn` while the
#                         previous one speaks, so its quiet-poll starts after the voice already ended)


def _take_ticket() -> int:
    with _queue_cv:
        t = _next_ticket[0]
        _next_ticket[0] += 1
        return t


def _wait_turn(ticket: int, timeout: float) -> bool:
    """BLOCKING (run via asyncio.to_thread): wait until it is this ticket's turn. False = timed out — the
    ticket is marked abandoned under the same lock, so the advance in `_release` skips it atomically."""
    deadline = time.monotonic() + max(0.0, timeout)
    with _queue_cv:
        while _serving[0] != ticket:
            left = deadline - time.monotonic()
            if left <= 0:
                _abandoned.add(ticket)
                return False
            _queue_cv.wait(timeout=min(left, 1.0))
        return True


def _release(ticket: int) -> None:
    """The ticket holder is done (spoke, degraded, or blew up — `finally` calls this always): pass the turn,
    skipping any ticket that abandoned while waiting."""
    with _queue_cv:
        _serving[0] = ticket + 1
        while _serving[0] in _abandoned:
            _abandoned.discard(_serving[0])
            _serving[0] += 1
        _queue_cv.notify_all()


def _reset_queue_for_tests() -> None:
    with _queue_cv:
        _next_ticket[0] = 0
        _serving[0] = 0
        _abandoned.clear()
        _last_spoke[0] = 0.0
        _queue_cv.notify_all()


async def _wait_for_quiet(timeout: float | None = None) -> bool:
    """Espera (polling suave) a que NO haya turno en vuelo (bot hablando o usuario hablando), consultando el
    busy-probe que registró la sesión viva. True = hay hueco, habla ya. False = timeout, la conversación no dio
    tregua. Sin probe registrado (sesión sin instrumentar) → asumimos hueco: LiveKit gestiona el barge-in del
    operador vía session.say(allow_interruptions=True), así que hablar no lo pisa de forma dura."""
    timeout = PROACTIVE_MAX_WAIT if timeout is None else timeout
    t0 = time.time()
    saw_busy = False
    while time.time() - t0 < timeout:
        try:
            busy = bool(_busy_probe()) if _busy_probe is not None else False
        except Exception:
            busy = False
        if not busy:
            # El RESPIRO (2026-08-31): `_BOT_GRACE_SECS` llevaba definido desde INI-008 y no lo usaba NADIE —
            # el «respiro tras la voz del bot» del comentario de arriba era letra muerta. Con la cola en serie
            # se notaría de verdad: el mensaje B arrancaría en el MISMO instante en que acaba la locución de A,
            # dos avisos en ráfaga que suenan a uno solo. Solo se paga cuando venimos de una locución viva
            # (saw_busy); un hueco que ya estaba en silencio habla al momento, como siempre.
            if saw_busy:
                await asyncio.sleep(_BOT_GRACE_SECS)
                saw_busy = False
                continue          # re-check: the operator may have started talking during the breath
            return True
        saw_busy = True
        await asyncio.sleep(0.3)
    return False
