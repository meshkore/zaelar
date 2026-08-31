#
# brain_notes.py — a tiny process-level mailbox for ONE-SHOT system notes to the brain's NEXT turn.
#
# WHY: some actions the brain triggers are async and fire-and-forget from its point of view — most notably
# building a widget ([[create]]/[[modify]] spawns a headless agent that takes ~1-2 min). The brain emits the tag
# and moves on with NO idea whether it succeeded, failed, or is still running; so it claims "done" prematurely
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
_pending: list[tuple[str, str]] = []   # (key, text) — the key is "" for the vast majority
_MAX = 20                              # bound the mailbox; drop the oldest if a burst piles up (never grow unbounded)


def push(text: str, key: str = "") -> None:
    """Queue a one-shot system note for the brain's next turn. No-op on empty text. Best-effort.

    `key` (V2-353) marks a RETRACTABLE note: one that makes a claim about LIVE state and may stop being
    true before delivery. These notes are not delivered in flight — they wait for the operator's next turn—,
    and that gap is real: measured in `search-buy-used-car` round 13, «The process has been running for 18 minutes,
    do you want to stop it?» and «I stopped the process: it timed out» reached the SAME prompt, about the SAME task.
    One asked whether to stop it and the other said it had already been stopped. A self-contradictory prompt has no
    obedient response. With a key, whoever kills the task retracts the question.

    A repeated key REPLACES the previous one: two notices saying «has been running for N minutes» about the same task
    are the same notice with the updated number, not two things to count.
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
    """Remove notes with this KEY that have not yet been delivered. Return how many. Best-effort (V2-353).

    Retracting is NOT censorship: the person retracting is the one who has just made the note FALSE, and almost always
    pushes their own note immediately afterward («I stopped it»). What is avoided is having both arrive together.
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
