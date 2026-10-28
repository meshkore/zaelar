"""What the operator is answering: the last line WE said before his turn began (demo, 2026-10-22).

`brain._last_reply` is rewritten on every streamed chunk of the CURRENT reply, so a guard that runs during or
after the stream and reads it as «what we said before» reads our own answer instead. Measured live: «Want me to
start the trip plan again properly?» → «Yes» → the model escalated, and the fragment guard read the reply it was
streaming («I'm on it — a fresh five-day plan…», no question in it) and annulled the commission as a fragment.
Proactive questions never reach `_last_reply` at all: «…running for 15 minutes now. Want me to stop it or keep
going?» → «Yes, please» → the stop was refused as context-bleed.

The fix is one snapshot, taken when the turn's window is built — after the proactive lines we said on our own
are drained into it (`dialog.drain_spoken`) and before the model streams a word. Every reader that asks «did we
just ask him something?» reads THIS, never the live `_last_reply`.
"""
from __future__ import annotations

from loguru import logger


def snapshot(brain, window) -> str:
    """Freeze the last assistant line of the window as the line this turn answers. Returns it."""
    line = ""
    for m in reversed(list(window or [])):
        if isinstance(m, dict) and m.get("role") == "assistant":
            line = str(m.get("content") or "").strip()
            if line:
                break
    try:
        brain._prior_line = line
    except Exception as e:  # noqa: BLE001 — a brain without attributes still runs its turn
        logger.debug(f"prior_line: no snapshot on {type(brain).__name__}: {e}")
    return line


def of(brain) -> str:
    """The line this turn answers. Falls back to `_last_reply` only for a brain that never snapshotted (a test
    double, an old entry point) — the behaviour every reader had before."""
    v = getattr(brain, "_prior_line", None)
    if v is None:
        v = getattr(brain, "_last_reply", "") or ""
    return str(v or "")


def answers_our_question(brief, prior: str) -> bool:
    """The turn is his ANSWER to a question we put to him: our prior line asked something, and the brief does not
    say the line is something else (a question of his own, a comment, a complaint) — `answer` and `order` both
    reply. ONE definition, read by the fragment guard and by the stop. With no question of ours, nothing here.

    The label only EXCLUDES; the fact that licenses is our question (bank case 3a9a082c: «Yes. Do it.» over our
    «…or drop it — which do you want?» read as `order` at 0.53, and the guard annulled the errand he agreed to)."""
    try:
        from nucleo.flash import canvas_license as _lic
        from nucleo.turn import brief as _tb
        if not _lic.answered_an_offer(prior):
            return False
        kind, _info = _tb.read(brief, _tb.REQUEST_KEY, "")
        return bool(kind) and str(kind) not in ("question", "comment", "complaint")
    except Exception as e:  # noqa: BLE001 — a classifier may never break a turn
        logger.debug(f"prior_line: answer verdict unreadable: {e}")
        return False

