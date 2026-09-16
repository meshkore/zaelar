"""nucleo/workers/reports.py — what the worker REPORTS about itself lands on its record (V2-059).

One cohesive family, moved out of `dispatch.py` byte for byte under the architecture ratchet: the setters
`hbnote` drives through `/api/agent/report`, plus the percentage derived from them. The Brain Worker opens a
session whose work is opaque, and these are how it becomes visible in a controlled way — a readable phase, a
declared plan, progress against it, and the BREADTH of an investigation (`considered`/`kept`, which is what
separates a defensible selection from the first three search-result rows).

`session_goal` (V2-707 F2 — how success will be MEASURED) is the newest member of this family and lives in
`workers/goal.py` instead, beside the rule that reads it.

⚠️ `_SESSIONS` is read through the `dispatch` MODULE on every call, never bound at import. That registry is
rebound by `monkeypatch` in 26 tests, so a module holding its own reference would silently keep the old dict
— the same trap `dispatch_confirm.py` documents about its own move.
"""
from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:                      # runtime import would be circular; the annotation is a string
    from .session import SessionRecord


def _dispatch():
    from nucleo import dispatch
    return dispatch


def session_phase(tid, phase: str) -> None:
    """Compat V2-036: reporte of fase EXPLÍCITO of the worker (hbnote). Actualiza the record RAM."""
    r = _dispatch()._SESSIONS.get(str(tid))
    if r is not None:
        _p = (phase or "").strip()
        r.phase = _p or r.phase
        r.last_event_at = time.time()
        _dispatch().record_phase(tid, _p)   # V2-358: `sheets.record_phase` marca la afirmación sin respaldo
    try:
        from voice.observer import emit
        extra = {"id": str(tid)}
        # V2-044: the handler HTTP of the CLI (hbnote) no has contexto of trace → sellar the of the session.
        if r is not None and r.trace_id:
            extra["trace"] = r.trace_id
            extra["span"] = f"worker:{tid}"
        emit("task", "phase", text=(phase or "").strip(), extra=extra)
    except Exception:
        pass


def session_alive(tid) -> str:
    """A LATIDO: the same fase, diciendo how much lleva. No touches the record (V2-227 ambito B2).

    Una tarjeta congelada in «recorriendo the pagina» durante noventa segundos es indistinguible of a worker
    dead, and esa ambiguedad es justo it that the operator pidio quitar: the silencio is reads como averia. Pero the
    remedio no can ser reescribir `r.phase` with the texto decorado — the latido siguiente decoraria the
    decoracion («… lleva 1 min — lleva 2 min»). Asi that is EMITE and no is guarda: the record preserves the fase
    limpia and the carril lleva the version with the time.

    Devuelve it emitido (or "" if no habia nothing that latir), that es it that does esto comprobable without a bus.
    """
    r = _dispatch()._SESSIONS.get(str(tid))
    if r is None or r.status not in _dispatch().LIVE_SESSION_STATES or r.paused:
        return ""
    try:
        from nucleo.workers import progress as _prog
        said = _prog.still_alive(r.phase or _dispatch()._default_label(r.kind), int(time.time() - (r.last_event_at or r.started)))
    except Exception:  # noqa: BLE001
        return ""
    try:
        from voice.observer import emit
        extra = {"id": str(tid)}
        if r.trace_id:
            extra["trace"] = r.trace_id
            extra["span"] = f"worker:{tid}"
        emit("task", "alive", text=said, extra=extra)
    except Exception:
        pass
    return said


def session_plan(tid, steps) -> None:
    """V2-059: the worker DECLARA su lista of tasks al empezar (`hbnote plan "a|b|c"`). Observabilidad estructurada:
    is ve the plan + cuantos pasos lleva → progreso real (no only a fase coarse)."""
    r = _dispatch()._SESSIONS.get(str(tid))
    if r is None:
        return
    if isinstance(steps, str):
        steps = [s.strip() for s in re.split(r"[|\n]", steps) if s.strip()]
    r.plan = [str(s)[:80] for s in (steps or [])][:12]
    r.done = 0
    r.last_event_at = time.time()
    r.last_step_at = r.last_event_at      # V2-354: el reloj del avance arranca AL DECLARAR el plan
    try:
        from voice.observer import emit
        extra = {"id": str(tid), "plan": r.plan}
        if r.trace_id:
            extra.update(trace=r.trace_id, span=f"worker:{tid}")
        emit("task", "plan", text=f"{len(r.plan)} pasos: " + " · ".join(r.plan)[:160], extra=extra)
    except Exception:
        pass


def session_progress(tid, note: str = "", done: int | None = None, pct: int | None = None) -> None:
    """V2-059: the worker reporta PROGRESO (`hbnote progress "..." --done N` / `--pct P`). Actualiza done/pct/note
    of the record → ESTADO/prompt of the FlashBrain + /api/tasks + observabilidad. Fail-soft."""
    r = _dispatch()._SESSIONS.get(str(tid))
    if r is None:
        return
    if note.strip():
        r.note = note.strip()[:200]
    if done is not None:
        try:
            _nuevo = max(0, int(done))
            if _nuevo != r.done:
                r.last_step_at = time.time()    # V2-354: el reloj del AVANCE, no el de la señal
            r.done = _nuevo
        except (TypeError, ValueError):
            pass
    if pct is not None:
        try:
            r.pct = max(0, min(100, int(pct)))
        except (TypeError, ValueError):
            pass
    r.last_event_at = time.time()
    try:
        from voice.observer import emit
        extra = {"id": str(tid), "done": r.done, "total": len(r.plan), "pct": _progress_pct(r)}
        if r.trace_id:
            extra.update(trace=r.trace_id, span=f"worker:{tid}")
        emit("task", "progress", text=(r.note or f"{r.done}/{len(r.plan)}")[:160], extra=extra)
    except Exception:
        pass


def session_considered(tid, considered: int | None = None, kept: int | None = None) -> None:
    """AMPLITUD reportada by the worker (`hbnote considered N --kept M`): cuantos candidatos ha evaluado of truth.

    Existe for that the SELECCIÓN sea auditable. Sin this dato, «te he encontrado the 3 mejores» es indistinguible
    of «te he copiado the 3 primeras that salieron», and ni the operator ni the cerebro can juzgar if conviene continue
    buscando. Con el, the cerebro can ofrecer the continuacion with a number concreto delante."""
    r = _dispatch()._SESSIONS.get(str(tid))
    if r is None:
        return
    for attr, val in (("considered", considered), ("kept", kept)):
        if val is None:
            continue
        try:
            setattr(r, attr, max(0, int(val)))
        except (TypeError, ValueError):
            pass
    r.last_event_at = time.time()
    try:
        from voice.observer import emit
        extra = {"id": str(tid), "considered": r.considered, "kept": r.kept}
        if r.trace_id:
            extra.update(trace=r.trace_id, span=f"worker:{tid}")
        emit("task", "considered", text=f"{r.considered} candidatos evaluados"
                                       + (f" · {r.kept} finalistas" if r.kept >= 0 else ""), extra=extra)
    except Exception:
        pass


def _progress_pct(r: "SessionRecord") -> int:
    """% of progreso: the explicito if it there is; if no, done/len(plan); -1 if desconocido."""
    if getattr(r, "pct", -1) >= 0:
        return r.pct
    if r.plan:
        return int(100 * min(r.done, len(r.plan)) / len(r.plan))
    return -1
