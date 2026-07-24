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
_pending: list[str] = []
_MAX = 20                              # bound the mailbox; drop the oldest if a burst piles up (never grow unbounded)


def push(text: str) -> None:
    """Queue a one-shot system note for the brain's next turn. No-op on empty text. Best-effort."""
    text = (text or "").strip()
    if not text:
        return
    with _lock:
        _pending.append(text)
        if len(_pending) > _MAX:
            del _pending[: len(_pending) - _MAX]
    logger.info(f"brain-note queued: {text[:120]}")


def drain() -> list[str]:
    """Return all pending notes and clear the mailbox (call once per brain turn, before building the prompt)."""
    with _lock:
        if not _pending:
            return []
        out = _pending[:]
        _pending.clear()
    return out
