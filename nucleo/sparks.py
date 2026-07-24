"""nucleo/sparks.py — 🔥 chispas: pensamiento espontáneo del cerebro v2 (V2-005 · T73).

Una chispa es un pensamiento que zaelar tiene por su cuenta (retomar una tarea pendiente, un recordatorio
suave) — NO una respuesta a un turno del operador. El riesgo es el RUIDO: una chispa molesta rompe la
confianza. Por eso el gate es DELIBERADAMENTE conservador y tiene DOS candados:

  1. **Gate de frecuencia** (`SparkGate`): presupuesto diario + separación mínima entre chispas + probabilidad
     baja por tick. Aunque el loop corra a 1 Hz, una chispa es un suceso raro.
  2. **Gate de utilidad** (`propose`): "¿aporta?". Solo propone si hay un candidato REAL (una tarea pendiente
     del journal que lleva tiempo sin tocarse). Si no hay nada que merezca interrumpir → devuelve None → se
     descarta. Empezamos sin generación por modelo (cero latencia/coste, cero alucinación); el SlowBrain podrá
     enriquecer las chispas más adelante (V2-007).

Todo el reloj/azar es inyectable → testeable de forma determinista.
"""
from __future__ import annotations

import os
import random
import time

_DAY_S = 86400


class SparkGate:
    """Decide SI se permite una chispa ahora (frecuencia). No decide el contenido (eso es `propose`)."""

    def __init__(self, daily_max: int | None = None, min_gap_s: float | None = None,
                 prob: float | None = None, clock=None, rng=None):
        self.daily_max = int(os.getenv("ZAELAR_SPARK_DAILY_MAX", "6")) if daily_max is None else daily_max
        self.min_gap_s = float(os.getenv("ZAELAR_SPARK_MIN_GAP_S", "1800")) if min_gap_s is None else min_gap_s
        self.prob = float(os.getenv("ZAELAR_SPARK_PROB", "0.01")) if prob is None else prob
        self._clock = clock or time.time
        self._rng = rng or random.random
        self._day = None            # día (epoch // 86400) del recuento actual
        self._count = 0             # chispas emitidas hoy
        self._last = 0.0            # epoch de la última chispa

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


# Cuánto debe llevar "quieta" una tarea del journal para que valga la pena resurgirla como chispa.
_STALE_S = float(os.getenv("ZAELAR_SPARK_STALE_S", str(6 * 3600)))


def propose(now: float | None = None) -> str | None:
    """Gate de UTILIDAD: devuelve el texto de una chispa que MERECE interrumpir, o None (→ se descarta).

    Candidato conservador: una tarea `pending` del journal (NO una tarea programada — esas ya tienen su propio
    disparo) que lleva `_STALE_S` sin actualizarse. Si no hay ninguna, no molesta."""
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
            continue  # las programadas tienen su propio disparo; no son material de chispa
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
