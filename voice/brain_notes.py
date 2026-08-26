#
# brain_notes.py — a tiny process-level mailbox for ONE-SHOT system notes to the brain's NEXT turn.
#
# WHY: some actions the brain triggers are async and fire-and-forget from its point of view — most notably
# building a widget ([[create]]/[[modify]] spawns a headless agent that takes ~1-2 min). The brain emits the tag
# and moves on with NO idea whether it succeeded, failed, or is still running; so it claims "hecho" prematurely
# and, in a later turn, references a widget id that never got built. This mailbox closes that loop: the completing
# action drops a short "[SISTEMA] …" note here, and the brain adapter (brains/*/…_processor.py) drains it and
# PREPENDS it to the next prompt — so the brain learns the real outcome and stops inventing / mis-claiming.
#
# Brain-agnostic on purpose: the queue lives in voice/ so any brain adapter can drain it; the widget layer (and any
# future async action) only needs push(). Best-effort, thread-safe, bounded — never raises into a caller.
#
import threading

from loguru import logger

_lock = threading.Lock()
_pending: list[tuple[str, str]] = []   # (llave, texto) — la llave es "" para la inmensa mayoría
_MAX = 20                              # bound the mailbox; drop the oldest if a burst piles up (never grow unbounded)


def push(text: str, key: str = "") -> None:
    """Queue a one-shot system note for the brain's next turn. No-op on empty text. Best-effort.

    `key` (V2-353) marca una nota RETRACTABLE: una que afirma algo sobre estado VIVO y que puede dejar de ser
    verdad antes de entregarse. Estas notas no se entregan al vuelo — esperan al siguiente turno del operador—,
    y ese hueco es real: medido en `search-buy-used-car` ronda 13, «El proceso lleva ya 18 minutos, ¿quieres que
    lo pare?» y «He parado el proceso: agotó su tiempo» llegaron al MISMO prompt, sobre la MISMA tarea. Una
    preguntaba si pararla y la otra decía que ya estaba parada. Un prompt que se contradice no tiene respuesta
    obediente. Con llave, quien mata la tarea retracta la pregunta.

    Una llave repetida SUSTITUYE a la anterior: dos avisos de «lleva N minutos» sobre la misma tarea son el
    mismo aviso con el número actualizado, no dos cosas que contar.
    """
    text = (text or "").strip()
    if not text:
        return
    key = (key or "").strip()
    with _lock:
        if key:
            _pending[:] = [(k, t) for k, t in _pending if k != key]
        _pending.append((key, text))
        if len(_pending) > _MAX:
            del _pending[: len(_pending) - _MAX]
    logger.info(f"brain-note queued: {text[:120]}")


def retract(key: str) -> int:
    """Quita las notas con esta LLAVE que aún no se han entregado. Devuelve cuántas. Best-effort (V2-353).

    Retractar NO es censurar: quien retracta es quien acaba de hacer FALSA la nota, y casi siempre empuja la
    suya justo después («la he parado»). Lo que se evita es que las dos lleguen juntas.
    """
    key = (key or "").strip()
    if not key:
        return 0
    with _lock:
        antes = len(_pending)
        _pending[:] = [(k, t) for k, t in _pending if k != key]
        fuera = antes - len(_pending)
    if fuera:
        logger.info(f"brain-note retractada ({fuera}): {key}")
    return fuera


def drain() -> list[str]:
    """Return all pending notes and clear the mailbox (call once per brain turn, before building the prompt)."""
    with _lock:
        if not _pending:
            return []
        out = [t for _k, t in _pending]
        _pending.clear()
    return out
