"""nucleo/notice_today.py — a notice asked for TODAY whose hour has already gone rings soon today, and is said.

Measured on `remember-and-remind-deadline` (ES + __us, Wednesday 2026-10-14 ~12:00): «Apúntame que el jueves
tengo que renovar el seguro del coche, y recuérdamelo el miércoles». Today WAS Wednesday and the default 09:00
had already passed. ES: the reply said «te aviso el miércoles 14 a las 9» while the model's tag, refused by the
scheduler as past, was «corrected» to 2026-10-21 09:00 — next week, six days AFTER the Thursday deadline. EN: the
agenda refused the asked notice twice («el instante ya pasó») while the reply had promised it.

The rule, for every door into the scheduler (the agenda's own notice and the model's `cron.create` tag):
  · a notice whose instant is TODAY and already gone, for something still ahead, rings at `soon(now)` — the next
    full hour at least `LEAD_S` away (12:00 → 13:00), or within `PROMPT_S` when the deadline is closer than that;
  · a day already behind us is not this module's: it schedules nothing and is said (`flash/reminder_year.py`);
  · every move is NOTED, so the reply reads back the instant actually scheduled (`flash/notice_readback.py`).

Pure arithmetic over epoch seconds plus a tiny in-process note; no IO. The clock is the caller's `now`.
"""
from __future__ import annotations

import threading
import time

LEAD_S = 15 * 60         # the notice never rings on the very next turn: at least this far ahead
PROMPT_S = 300           # when the deadline is closer than the next full hour
NOTE_TTL_S = 180.0       # a move belongs to the turn that made it
FMT = "%Y-%m-%d %H:%M"

_lock = threading.Lock()
_moves: list[dict] = []


def stamp(ts: float) -> str:
    return time.strftime(FMT, time.localtime(ts))


def _day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def gone_today(when: float, now: float) -> bool:
    """`when` is today and already behind us (a 09:00 asked at 12:00)."""
    return when <= now and _day(when) == _day(now)


def soon(now: float, before: float | None = None) -> float:
    """The next sensible instant today: the next full hour at least `LEAD_S` ahead, else `PROMPT_S` from now.

    The fallback is taken when that hour would fall on or after `before` (the deadline) or on another day."""
    t = time.localtime(now + LEAD_S)
    top = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour + 1, 0, 0, 0, 1, -1))
    if _day(top) != _day(now) or (before is not None and top >= before):
        return now + PROMPT_S
    return top


def moved(asked: float, at: float, now: float) -> float:
    """Note that the notice asked for `asked` will ring at `at` instead; returns `at`."""
    with _lock:
        _moves.append({"asked": stamp(asked), "at": stamp(at), "t": now})
        del _moves[:-8]
    return at


def ring_at(when: float, now: float, before: float | None = None) -> float:
    """`when`, or `soon(now)` (noted) when it is today and gone while the thing it announces is still ahead."""
    if gone_today(when, now) and (before is None or before > now):
        return moved(when, soon(now, before), now)
    return when


def take_move(now: float, within_s: float = NOTE_TTL_S) -> dict | None:
    """The latest move noted in the last `within_s` seconds, consumed — {asked, at} stamps — or None."""
    with _lock:
        fresh = [m for m in _moves if 0 <= now - m["t"] <= within_s]
        _moves.clear()
    return fresh[-1] if fresh else None
