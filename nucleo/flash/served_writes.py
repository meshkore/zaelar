"""nucleo/flash/served_writes.py — a sentence whose write already LANDED is not an errand to hand a worker (2026-10-14).

Measured on `what-does-my-week-look-like` ES (report 20261014-005411): «Apúntame dos cosas: dentista el 24 de
octubre… y cena con Laura dos días después…» wrote both appointments through `widget_data` in turn 0. Three turns
later «Perfecto, con eso me apaño. Gracias.» was answered with the onboarding offer («Si quieres, otro día te
cuento… buscarte algo concreto…»), the reply-promise reader called that a promise (`act`, 0.51), and the promise
backstop went looking for the request it belonged to: `escalate_goal_from_window` walked back, found turn 0 —
which `_needs_real_work` reads as work — and a Brain Worker spent two minutes writing two appointments that were
already in the calendar. The window lookback (V2-132) exists for a request zaelar asked a detail about and never
started; it could not tell that this one had been done.

Both channels pass every landed data-op through `circuit.compose.remember`, so that is where a WRITE (an action the
manifest does not declare as a view) is noted with the sentence it came from. `served(content)` answers whether a
window message is one of those sentences. Bounded: a short TTL and a small ring, in-process like the rest of the
turn's short memory.
"""
from __future__ import annotations

import time

TTL_S = 1800.0
_MAX = 32

_seen: list[tuple[str, float]] = []


def _fold(text: str) -> str:
    from nucleo.circuit.compose import _fold as _f
    return _f(text)


def _is_view(wid: str, action: str) -> bool:
    try:
        from widgets import runtime
        spec = ((runtime.get(str(wid or "").split("::", 1)[0]) or {}).get("actions") or {}).get(action)
        return bool(isinstance(spec, dict) and spec.get("view"))
    except Exception:  # noqa: BLE001 — unreadable manifest: not noted, today's lookback stands
        return True


def note(wid: str, action: str, text: str, res, *, now: float | None = None) -> None:
    """After a data-op: remember the sentence when the op was a WRITE that landed."""
    if not isinstance(res, dict) or res.get("ok") is False or res.get("error") or _is_view(wid, action):
        return
    folded = _fold(text)
    if not folded:
        return
    _seen.append((folded, time.time() if now is None else now))
    del _seen[:-_MAX]


def served(content: str, *, now: float | None = None) -> bool:
    """Is this operator message one whose write already landed? (its words are inside a noted sentence)"""
    c = _fold(content)
    if not c:
        return False
    now = time.time() if now is None else now
    return any(now - at <= TTL_S and f" {c} " in f" {s} " for s, at in _seen)


def reset() -> None:
    _seen.clear()
