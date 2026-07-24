"""nucleo/flash/escalate.py — escalado FlashBrain → SlowBrain (V2-004 · T64; escalado REAL cerrado en V2-007 · T87).

Cuando un turno necesita memoria/tools/razonamiento, el FlashBrain llama a esta costura (por function-calling,
no por texto-tag — agnóstico del idioma; ver `router.py`). Registra la intención (para que el estado vivo pueda
decir "sigo con ello, dame un poco") y **publica un evento `escalate.requested` en el `bus/`**. Desde V2-007 el
circuito está CERRADO: `nucleo/dispatch.run_listener` consume ese evento, despacha la tarea a los agentes de
trabajo (web/código/genérico) async y ENTREGA el resultado por `voice/proactive` (voz+UI) + nota `[SISTEMA]`
(`voice/brain_notes`) — mismo circuito de siempre —, luego llama a `finish()`. NO corre Hermes (Hermes se
entierra en V2-009).
"""
from __future__ import annotations

import time

_tasks: dict[int, dict] = {}      # id → {request, started_at, done, summary}
_seq = 0
_MAX = 12                          # mantén los más recientes; descarta los viejos (nunca crece sin límite)


def _emit_bus(topic: str, payload: dict) -> None:
    """Publica en el sistema nervioso de forma loop-agnóstica (el FlashBrain corre en el job-thread de LiveKit)."""
    try:
        import bus
        bus.emit_sync(topic, payload)
    except Exception:
        pass


def escalate_to_slowbrain(request: str, *, context: dict | None = None) -> int:
    """Encola la INTENCIÓN de un turno de SlowBrain para `request`. Devuelve un id de tarea. STUB en V2-004:
    registra + publica `escalate.requested`; el SlowBrain lo ejecuta async a partir de V2-006/V2-007."""
    global _seq
    req = (request or "").strip()
    _seq += 1
    tid = _seq
    _tasks[tid] = {"request": req[:200], "started_at": time.time(), "done": False, "summary": ""}
    if len(_tasks) > _MAX:
        for k in sorted(_tasks)[: len(_tasks) - _MAX]:
            del _tasks[k]
    ctx = dict(context or {})
    # TRAZABILIDAD (V2-044): el bus NO copia el contexto asyncio → el trace del turno que escala viaja EN el
    # payload; dispatch lo sella en la SessionRecord y todo el ciclo del worker queda encadenado a la frase.
    if "trace" not in ctx:
        try:
            from voice import trace as _trace
            _t = _trace.current()
            if _t:
                ctx["trace"] = _t
        except Exception:
            pass
    _emit_bus("escalate.requested", {"id": tid, "request": req, "context": ctx, "ts": time.time()})
    return tid


def finish(tid: int, summary: str = "") -> None:
    """Marca una escalada como resuelta (lo llamará el retorno del SlowBrain en V2-007)."""
    t = _tasks.get(tid)
    if t:
        t["done"] = True
        t["summary"] = (summary or "").strip()[:160]
        _emit_bus("escalate.done", {"id": tid, "summary": t["summary"]})


def pending() -> list[dict]:
    """Escaladas en vuelo (no resueltas), más antigua primero, con segundos transcurridos."""
    now = time.time()
    return [{"id": tid, "request": _tasks[tid]["request"], "secs": int(now - _tasks[tid]["started_at"])}
            for tid in sorted(_tasks) if not _tasks[tid]["done"]]


def summary_line() -> str:
    """Una línea compacta para el bloque de estado vivo del FlashBrain, o '' si nada está en vuelo."""
    p = pending()
    if not p:
        return ""
    bits = [f'«{t["request"][:60]}» (llevas {t["secs"]}s)' for t in p]
    return ("TAREAS DE FONDO EN CURSO (el cerebro profundo las está resolviendo; si el operador pregunta, dilo "
            "con naturalidad, NO reinicies ni digas que ya está): " + "; ".join(bits))


def reset() -> None:
    """Limpia el registro (tests)."""
    global _seq
    _tasks.clear()
    _seq = 0
