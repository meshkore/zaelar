"""voice/trace.py — TRAZABILIDAD texto → acción → rail → sesión → eventos (V2-044).

Cada ESTÍMULO que entra al sistema (una frase del operador por voz/chat, un turno del probe, un disparo de cron,
un aviso proactivo) nace con un **trace id**; todo lo que derive de él —tool calls, tags de canvas, runs de rail,
sesiones de worker, pasos del navegador, escrituras de memoria, notify— queda sellado con ese id en cada evento
del observador (`voice/observer.py::emit` lo adjunta solo). Con eso la observabilidad puede responder la pregunta
de calidad del sistema: ¿esta frase cayó en el rail correcto y desembocó en el set de eventos que corresponde?

Diseño (iniciativa `.meshkore/roadmap/initiatives/V2-044-trazabilidad-texto-accion-rail.md`):

- **ContextVar** `(trace_id, span)`: viaja SOLO por `asyncio.create_task` y `asyncio.to_thread` (ambos copian el
  contexto) → el grueso del turno se traza GRATIS. Los cruces de loop/hilo que NO copian contexto
  (`run_coroutine_threadsafe`, `call_soon_threadsafe`, hilos propios como el writer de memoria, el mailbox de un
  owner backed) se cosen a mano: capturan `current()` al encolar y `adopt()` al ejecutar.
- **`span`** = ACTOR de nivel 2 del árbol de la vista Trazas (`worker:<id>`, `web:<task>`, `rail:<kind>`,
  `gen:<widget>`, `memoria`). La raíz (nivel 1) es la frase; los eventos (nivel 3) cuelgan de su span.
- **Coste**: leer un ctxvar son nanosegundos; el único evento nuevo por estímulo es la raíz (`kind="trace"`).
  El hot path de voz (V2-011) queda intacto.

Sin dependencias (solo stdlib) — lo importa `voice/observer.py`, que a su vez lo importa todo el mundo.
"""
from __future__ import annotations

import contextvars
import itertools
import uuid
from contextlib import contextmanager

# (trace_id, span) del contexto de ejecución actual. "" = sin traza (eventos de arranque, ruido de fondo).
_ctx: contextvars.ContextVar[tuple[str, str]] = contextvars.ContextVar("zaelar_trace", default=("", ""))

_seq = itertools.count(1)


def reset_seq() -> None:
    """Vuelve a numerar los traces desde T1. La llama el arranque de una SESIÓN NUEVA (`observer.rotate_session`):
    si el contador siguiera subiendo, una sesión que empieza en blanco abriría en «T34», que le dice al operador que
    está mirando la continuación de algo — justo lo contrario de lo que es. El id sigue llevando su sufijo
    aleatorio, así que dos sesiones distintas nunca colisionan aunque las dos tengan un T1."""
    global _seq
    _seq = itertools.count(1)


def begin(text: str, origin: str = "turno") -> str:
    """Nace un trace: id corto legible (`T<seq>·<hex4>`), se fija en el contexto y se emite el EVENTO RAÍZ
    (kind="trace", root=True) con la frase/motivo que lo inicia — es la raíz del árbol en la vista Trazas.
    Llamar en el punto de ENTRADA del estímulo (turno de voz/chat, probe, cron, proactivo). Devuelve el id."""
    tid = f"T{next(_seq)}·{uuid.uuid4().hex[:4]}"
    _ctx.set((tid, ""))
    try:
        from voice.observer import emit
        # Cluster mesh housekeeping (peer heartbeat nudges, `connectors/meshkore/bridge.py`) is background
        # plumbing, not a user turn — same family as any other `cluster`-kind event (`_CAT["cluster"]="system"`
        # in observer.py). Without this override the root trace event inherits `cat="flash"` from `kind="trace"`
        # regardless of origin, and `stamp_identity()`'s "background noise never fabricates a session" guard
        # (observer.py, 2026-08-15) only checks `cat in ("system","pulse")` — so a cluster heartbeat firing
        # after the operator stopped the agent (⏻) self-opened a brand-new "live" session, the same bug that
        # guard was meant to close, one `origin` short of complete.
        extra = {"trace": tid, "root": True, "origin": origin}
        if origin == "cluster":
            extra["cat"] = "system"
        emit("trace", origin, text=(text or "")[:300], role="user" if origin in ("turno", "probe") else "system",
             extra=extra)
    except Exception:
        pass
    return tid


def current() -> str:
    """Trace id del contexto actual ("" si no hay). Lo lee `observer.emit` en cada evento — debe ser barato."""
    return _ctx.get()[0]


def current_span() -> str:
    return _ctx.get()[1]


def adopt(tid: str, span: str = "") -> None:
    """Re-unirse a un trace desde OTRO contexto (loop del server, hilo del writer, handler HTTP de un CLI puente).
    `span` etiqueta el ACTOR ('worker:5', 'web:t2', 'memoria'…) para el nivel 2 del árbol. Best-effort."""
    _ctx.set(((tid or "").strip(), (span or "").strip()))


@contextmanager
def scope(tid: str, span: str = ""):
    """`with trace.scope(tid, 'memoria'): …` — adopta el trace SOLO durante el bloque (hilos que procesan items
    de distintas trazas en bucle, como el writer de la cola de memoria)."""
    tok = _ctx.set(((tid or "").strip(), (span or "").strip()))
    try:
        yield
    finally:
        try:
            _ctx.reset(tok)
        except Exception:
            pass
