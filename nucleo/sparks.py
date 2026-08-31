"""nucleo/sparks.py — 🔥 sparks: spontaneous thought from the brain v2 (V2-005 · T73).

A spark is a thought that zaelar has on its own (resuming a pending task, a gentle reminder) — NOT a
response to an operator turn. The risk is NOISE: an annoying spark breaks trust. That is why the gate is
DELIBERATELY conservative and has TWO locks:

  1. **Frequency gate** (`SparkGate`): daily budget + minimum separation between sparks + low probability
     per tick. Even if the loop runs at 1 Hz, a spark is a rare event.
  2. **Utility gate** (`propose`): "does it help?". It only proposes when there is a REAL candidate (a
     pending journal task that has not been touched for some time). If there is nothing worth interrupting →
     returns None → is discarded. We start without model generation (zero latency/cost, zero hallucination);
     SlowBrain may enrich the sparks later (V2-007).

The entire clock/randomness interface is injectable → deterministically testable.
"""
from __future__ import annotations

import os
import random
import time

_DAY_S = 86400


class SparkGate:
    """Decides WHETHER a spark is allowed now (frequency). It does not decide the content (that is `propose`)."""

    def __init__(self, daily_max: int | None = None, min_gap_s: float | None = None,
                 prob: float | None = None, clock=None, rng=None):
        self.daily_max = int(os.getenv("ZAELAR_SPARK_DAILY_MAX", "6")) if daily_max is None else daily_max
        self.min_gap_s = float(os.getenv("ZAELAR_SPARK_MIN_GAP_S", "1800")) if min_gap_s is None else min_gap_s
        self.prob = float(os.getenv("ZAELAR_SPARK_PROB", "0.01")) if prob is None else prob
        self._clock = clock or time.time
        self._rng = rng or random.random
        self._day = None            # day (epoch // 86400) of the current count
        self._count = 0             # sparks emitted today
        self._last = 0.0            # epoch of the last spark

    def _roll_day(self, now: float) -> None:
        day = int(now // _DAY_S)
        if day != self._day:
            self._day = day
            self._count = 0

    def budget_left(self, now: float | None = None) -> int:
        now = self._clock() if now is None else now
        self._roll_day(now)
        return max(0, self.daily_max - self._count)

    def allow(self, now: float | None = None) -> bool:
        now = self._clock() if now is None else now
        self._roll_day(now)
        if self._count >= self.daily_max:
            return False
        if self._last and (now - self._last) < self.min_gap_s:
            return False
        return self._rng() < self.prob

    def record(self, now: float | None = None) -> None:
        now = self._clock() if now is None else now
        self._roll_day(now)
        self._count += 1
        self._last = now


# How long a journal task must remain "quiet" for it to be worth resurfacing as a spark.
_STALE_S = float(os.getenv("ZAELAR_SPARK_STALE_S", str(6 * 3600)))


def propose(now: float | None = None) -> str | None:
    """UTILITY gate: returns the text of a spark that is WORTH interrupting for, or None (→ discarded).

    Conservative candidate: a `pending` journal task (NOT a scheduled task — those already have their own
    trigger) that has gone `_STALE_S` without being updated. If there is none, it does not bother anyone."""
    now = time.time() if now is None else now
    try:
        from memory import journal
    except Exception:
        return None
    try:
        pend = journal.list_entries(status="pending")
    except Exception:
        return None
    for e in pend:
        d = e.get("detail") or {}
        if d.get("kind") == "scheduled":
            continue  # scheduled tasks have their own trigger; they are not spark material
        updated = e.get("updated") or 0
        if now - updated < _STALE_S:
            continue
        title = (e.get("title") or "").strip()
        if title:
            try:
                from voice.engine.core import langs
                return langs.current_language().spark_pending.format(title=title)
            except Exception:
                return f"Sigo con una cosa pendiente: {title}. ¿Lo retomamos?"
    return None
