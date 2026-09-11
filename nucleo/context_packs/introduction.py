"""The INTRODUCTION pack — the only phase that exists today (V2-675).

The operator's words: *«una excepción al inicio en el que la conversación fuera guiada por el agente… ¿quién
eres? ¿cómo te llamas? ¿dónde vives? ¿qué podría hacer por ti?»*, *«tiene que conocerse a sí mismo y saber
quién es y sus capacidades»*, and the limit that shapes the whole block — *«tampoco hace falta que le diga qué
puede hacer y que se pase cuatro minutos hablando»*.

Measured before writing it (his own English session, 2026-09-11): the kickoff asked his name, he answered
around it, and the profile still held `operator_name: None` three sessions later. There was no phase — the
first turn had an instruction and the second turn had nothing, so the introduction depended entirely on
whether a single greeting happened to land.

**What this pack does NOT contain, and why.** It does not list the widgets: the resource layer
(`_flash_layer`) already puts the real, live catalog in the same prompt, and a second inventory written by
hand is how two lists end up disagreeing — the failure this codebase has paid for repeatedly (V2-594 named
it, V2-603 measured a prompt claiming less coverage than existed). What it names are the FAMILIES of what
the agent can do, which are architecture and do not go stale, and it points at the catalog for the rest.

**Closing it is the hard half.** The operator asked that the decision be ours and, when needed, a model's:
*«puede decidirlo un modelo de lenguaje con unas llamadas internas propias nuestras»*. So there are three
exits, cheapest first: a DETERMINISTIC one (we know his name — the one fact the introduction exists to
learn), a JUDGE (off the hot path, at most one call every `_JUDGE_EVERY` turns), and a CAP (an introduction
that never ends is a bug, not a long introduction). Whichever fires, the flag is written and the block is
gone for good — `settings.intro_done`, which lives on the AGENT side, so a factory reset correctly starts
the relationship over.
"""
from __future__ import annotations

import asyncio

from loguru import logger

FLAG = "intro_done"

_JUDGE_AFTER = 4        # turns before the judge is worth a call at all — nothing is settled before then
_JUDGE_EVERY = 4        # and then at most one call every N turns: this is off the hot path, not free
_MAX_TURNS = 30         # the cap. An introduction still running after this many turns is not introducing.

_turns = 0              # process-lived on purpose: a restart mid-introduction re-arms the cap, which is the
#                         safe direction — the cap is a backstop, and the other two exits are the real ones.
_judging = False
_tasks: list = []


# ── is the phase running? ───────────────────────────────────────────────────────────────────────────────
def is_active() -> bool:
    """Cheap, local, and asked on EVERY turn. Two conditions, and the second is not redundant: while the
    language ceremony is still open nobody has spoken yet (V2-672), and an introduction block riding a
    prompt in a language the operator has not chosen is the exact failure that batch closed."""
    try:
        from config import settings
        if settings.get(FLAG):
            return False
        return bool(str(settings.get("stt_language") or "").strip())
    except Exception:  # noqa: BLE001
        return False        # unreadable settings → no phase. A missing block costs a plainer first
    #                         conversation; a block that cannot be turned off costs every turn forever.


def close(reason: str) -> None:
    """End the phase. Idempotent, and it says so out loud — a phase of the relationship ending is exactly
    the kind of thing that is impossible to reconstruct later if nobody wrote it down."""
    try:
        from config import settings
        if settings.get(FLAG):
            return
        settings.update({FLAG: True})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"context_packs.introduction: could not persist {FLAG}: {e!r}")
        return
    logger.info(f"context_packs.introduction: phase CLOSED ({reason})")
    try:
        from voice.observer import emit
        emit("phase", "🎓 presentación terminada — su contexto se archiva", role="system",
             extra={"cat": "flash", "pack": "introduction", "reason": reason, "turns": _turns})
    except Exception:  # noqa: BLE001
        pass


# ── the block ───────────────────────────────────────────────────────────────────────────────────────────
def _known() -> dict:
    try:
        from memory import api as _mem
        return _mem.state() or {}
    except Exception:  # noqa: BLE001
        return {}


def block() -> str:
    """The phase's instructions. Written as what to DO this turn, never as what the agent IS — a permanent
    fact would survive the phase in the model's reading of itself even after the text stops being sent."""
    st = _known()
    name = str(st.get("operator_name") or "").strip()
    missing = [label for label, key in (("su nombre", "operator_name"),
                                        ("dónde vive", "location"),
                                        ("cómo prefiere que le hables (tú/usted)", "treatment"))
               if not str(st.get(key) or "").strip()]
    lines = [
        "ES EL PRINCIPIO DE VUESTRA RELACIÓN: todavía no os conocéis. Durante esta fase, además de atender "
        "lo que te pida, te toca a ti llevar la conversación hacia conoceros.",
        "CÓMO: **una sola cosa por turno**, encajada en lo que estéis hablando, nunca un cuestionario ni una "
        "ristra de preguntas. Si te está pidiendo algo, primero se lo resuelves; la pregunta va después y "
        "solo si cabe con naturalidad. Si te contesta con evasivas o cambia de tema, lo dejas estar: no se "
        "insiste ni se vuelve a preguntar lo mismo dos veces.",
    ]
    if missing:
        lines.append("LO QUE TODAVÍA NO SABES de él, por orden de importancia: " + " · ".join(missing)
                     + ". Cuando te lo diga, se guarda solo — tú no tienes que hacer nada para recordarlo.")
    else:
        lines.append("Ya sabes quién es. Lo que falta es que él sepa quién eres tú y para qué le sirves.")
    if name:
        lines.append(f"Se llama {name}: úsalo con naturalidad, ni en cada frase ni nunca.")
    lines.append(
        "SI TE PREGUNTA QUÉ PUEDES HACER (o «¿y tú para qué sirves?»), la respuesta es **corta y concreta**: "
        "dos o tres cosas, elegidas por lo que ya te haya contado de él, y paras para ver si le interesan. "
        "NUNCA recites un catálogo ni encadenes capacidades: una lista larga no se recuerda y suena a folleto. "
        "Mejor una frase con un ejemplo de algo que podríais hacer ahora mismo que cinco enumerando.")
    lines.append(
        "LO QUE ERES, para elegir esos ejemplos (el catálogo REAL de widgets y herramientas lo tienes arriba "
        "en este mismo prompt — úsalo, no te inventes capacidades ni lo repitas entero): hablas con él por "
        "voz y por texto; llevas tarjetas en su escritorio (agenda con avisos, música, vídeo, fotos, "
        "documentos, un navegador de verdad, sus archivos); investigas en internet y le traes el resultado "
        "en vez de una lista de enlaces; te ocupas de encargos largos por tu cuenta y le avisas al terminar; "
        "le lees y le contestas mensajes y correo si conecta sus cuentas; y te acuerdas de lo que te cuenta, "
        "sesión tras sesión.")
    lines.append(
        "LO QUE NO HACES en esta fase: prometer nada que no puedas hacer, y hablar de cómo estás hecho por "
        "dentro. Si te pregunta qué eres, eres su asistente — no un modelo, ni una lista de piezas.")
    return "\n".join(f"· {ln}" if i else ln for i, ln in enumerate(lines))


# ── closing it ──────────────────────────────────────────────────────────────────────────────────────────
def _deterministic_close() -> str:
    """The cheap exit, asked before any model. Knowing his name is the one fact the introduction exists to
    learn, and it is also the one the memory writes on its own — so in the common case this phase ends
    without a single extra call."""
    st = _known()
    if str(st.get("operator_name") or "").strip():
        return "ya sabemos su nombre"
    return ""


_JUDGE_SYSTEM = (
    "You watch the FIRST conversation between a person and their new personal assistant, to decide whether "
    "the introduction phase is over. It is OVER when the two have actually met: the assistant knows who the "
    "person is (at least their name), and the person has been told what the assistant can do for them — or "
    "has made clear they are not interested in being introduced and just want to use it. It is NOT over if "
    "they have only exchanged greetings, or if the assistant has not yet said what it is for. "
    'Answer with ONE word: "yes" if the introduction is over, "no" if it is not. Nothing else.'
)


def _judge_sync(transcript: str) -> bool:
    from nucleo import memllm
    raw = memllm.chat_sync("errand_scope", _JUDGE_SYSTEM, transcript,
                           max_tokens=6, temperature=0.0, timeout=20.0)
    return (raw or "").strip().lower().startswith(("yes", "sí", "si"))


def _recent(limit: int = 14) -> str:
    try:
        from memory import api as _mem
        win = _mem.recent_window(limit=limit) or []
    except Exception:  # noqa: BLE001
        return ""
    lines = []
    for m in win:
        who = "PERSON" if (m.get("role") == "user") else "ASSISTANT"
        txt = (m.get("content") or "").strip().replace("\n", " ")[:220]
        if txt:
            lines.append(f"{who}: {txt}")
    return "\n".join(lines[-limit:])


async def _maybe_close() -> None:
    """Off the hot path, one turn behind the conversation. Fail-open in the direction that keeps the phase
    RUNNING: a judge that cannot be reached leaves the introduction open, and the cap ends it eventually."""
    global _judging
    if _judging:
        return
    why = _deterministic_close()
    if why:
        close(why)
        return
    if _turns >= _MAX_TURNS:
        close(f"tope de {_MAX_TURNS} turnos")
        return
    if _turns < _JUDGE_AFTER or (_turns - _JUDGE_AFTER) % _JUDGE_EVERY:
        return
    transcript = _recent()
    if not transcript:
        return
    _judging = True
    try:
        done = await asyncio.to_thread(_judge_sync, transcript)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"context_packs.introduction: judge unreachable, phase stays open: {e!r}")
        done = False
    finally:
        _judging = False
    if done:
        close("el juez dice que ya os conocéis")


async def _consume_turns(q) -> None:
    global _turns
    while True:
        try:
            await q.get()
        except asyncio.CancelledError:
            return
        try:
            if not is_active():
                continue
            _turns += 1
            await _maybe_close()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"context_packs.introduction: {e!r}")


def start() -> None:
    """Watch `turn.completed` — the Susurro/actionmap pattern (zero coupling with the voice provider, and it
    covers BOTH channels for free, because `observer.turn_detail` is where a voice turn and a probe turn
    both close). Idempotent; never raises into the caller."""
    global _tasks
    if _tasks:
        return
    try:
        if not is_active():
            return                      # no phase running → nothing to watch, and no subscription to pay for
        import bus
        loop = asyncio.get_event_loop()
        _tasks = [loop.create_task(_consume_turns(bus.subscribe("turn.completed")))]
        logger.info("context_packs.introduction: phase OPEN — watching for when it is over")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"context_packs.introduction: watcher not started (conversation unaffected): {e!r}")


async def stop() -> None:
    global _tasks
    for t in _tasks:
        t.cancel()
    for t in _tasks:
        try:
            await t
        except (asyncio.CancelledError, Exception):  # noqa: B014
            pass
    _tasks = []


def install() -> None:
    from . import Pack, register
    register(Pack(id="introduction", title="Presentación", order=10, active=is_active, block=block))
