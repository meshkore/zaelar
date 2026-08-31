"""voice/trace.py — TRACEABILITY text → action → rail → session → events (V2-044).

Every STIMULUS entering the system (an operator phrase via voice/chat, a probe turn, a cron trigger,
a proactive notice) starts with a **trace id**; everything derived from it—tool calls, canvas tags, rail runs,
worker sessions, browser steps, memory writes, notify—is sealed with that id in every observer event
(`voice/observer.py::emit` attaches it automatically). This lets observability answer the system-quality
question: did this phrase enter the correct rail and result in the corresponding set of events?

Design (initiative `.meshkore/roadmap/initiatives/V2-044-trazabilidad-texto-accion-rail.md`):

- **ContextVar** `(trace_id, span)`: travels ONLY through `asyncio.create_task` and `asyncio.to_thread` (both copy the
  context) → most of the turn is traced for FREE. Loop/thread crossings that do NOT copy context
  (`run_coroutine_threadsafe`, `call_soon_threadsafe`, dedicated threads such as the memory writer, an owner-backed
  mailbox) are stitched manually: capture `current()` when enqueuing and `adopt()` when executing.
- **`span`** = level-2 ACTOR in the Traces view tree (`worker:<id>`, `web:<task>`, `rail:<kind>`,
  `gen:<widget>`, `memoria`). The root (level 1) is the phrase; events (level 3) hang from its span.
- **Cost**: reading a ctxvar takes nanoseconds; the only new event per stimulus is the root (`kind="trace"`).
  The voice hot path (V2-011) remains intact.

No dependencies (stdlib only) — imported by `voice/observer.py`, which in turn is imported by everything.
"""
from __future__ import annotations

import contextvars
import itertools
import time
import uuid
from contextlib import contextmanager

# (trace_id, span) of the current execution context. "" = no trace (startup events, background noise).
_ctx: contextvars.ContextVar[tuple[str, str]] = contextvars.ContextVar("zaelar_trace", default=("", ""))

# The counter is routed through the process-identity owner (F5, 2026-08-23) but keeps THIS module's contract
# untouched: per-SESSION numbering (reset by `observer.rotate_session`) with a random suffix so two sessions'
# T1 never collide. No boot stamp composed on purpose — the suffix already carries the uniqueness.
from nucleo.runtime_ids import next_seq as _next_seq, reset_seq as _reset_named_seq

# ── `active()` — the current trace for callers that CANNOT inherit it from the ContextVar (2026-08-16) ───────────
# Source audit (operator: "fix it in the flash brain... where events are generated"): several handlers
# de `voice/engine/pipeline/agent.py` (el estado del pipeline, el VAD, las métricas de TTS/STT, el transcript del
# propio zaelar) corren en tareas de LiveKit que son HERMANAS —nunca DESCENDIENTES— de la tarea donde
# `NucleoLLMStream._run_inner` fija el trace del turno (confirmado contra el código fuente de livekit-agents
# 1.6.6: `AgentActivity._pipeline_reply_task`/`AudioRecognition._stt_consumer_atask` existen ANTES de que el
# turno empiece a procesarse). `asyncio.create_task` copia el ContextVar solo hacia HIJOS — nunca hacia una tarea
# hermana ni hacia atrás en el tiempo — así que ningún truco de propagación arregla esto: no es un fallo, es cómo
# funciona `contextvars` por diseño. La sesión real que lo probó: de 17 transcripciones, 13 llegaban con
# `corr_id: null`; VAD, nunca ninguna.
#
# `active()` is the answer: an EXPLICIT pointer (not a ContextVar), kept current by `begin()`/`adopt()`, and
# deliberately read by those handlers instead of trusting the ambient ContextVar. It expires (`max_age_s`, by
# defecto 3s): un evento que llega mucho después de que el último trace se fijara no se le cuelga a un turno que
# probablemente ya cerró —eso reabriría en el master un flujo "cerrado" con actividad fantasma, justo el bug que
# `_maybe_close_flow`/`drain_pending_flow_closes` (mismo día) arreglaron por el otro lado— y cae al trace GENERAL
# de la sesión (`_general`, fijado por el kickoff) en su lugar: "se atribuye a la charla general, bienvenida, etc"
# es literalmente lo que pidió el operador para lo que no tiene tarea propia, no un cajón sin fondo — sigue
# acotado en el tiempo y sigue siendo un flujo normal que algún día cierra.
#
# Deliberately NOT used for the operator's FINAL transcript or fragments: that text causes
# de que el turno empiece, así que en el instante en que se emite el trace del turno TODAVÍA no existe —
# adjuntarle `active()` ahí le pegaría el trace del turno ANTERIOR, que es peor que no llevar ninguno. Ese caso
# se resuelve en el master, en lectura (`cloud/backoffice/src/flowAttribution.js::attributeOrphans`), que sí
# conoce ambos lados de la ventana temporal y por eso puede decidir bien.
_active: str = ""
_active_at: float = 0.0
_general: str = ""   # el trace de "charla general" (el kickoff) — suelo de active() una vez arrancada la sesión


def active(max_age_s: float = 3.0) -> str:
    """The current trace for a reader that cannot inherit it from the ContextVar. Never invents one if the session
    has not started yet (the kickoff has not run) — returns "", like `current()` without a trace."""
    if _active and (time.monotonic() - _active_at) <= max_age_s:
        return _active
    return _general


def reset_seq() -> None:
    """Vuelve a numerar los traces desde T1. La llama el arranque de una SESIÓN NUEVA (`observer.rotate_session`):
    si el contador siguiera subiendo, una sesión que empieza en blanco abriría en «T34», que le dice al operador que
    está mirando la continuación de algo — justo lo contrario de lo que es. El id sigue llevando su sufijo
    aleatorio, así que dos sesiones distintas nunca colisionan aunque las dos tengan un T1."""
    _reset_named_seq("voice.trace")


def begin(text: str, origin: str = "turno") -> str:
    """Nace un trace: id corto legible (`T<seq>·<hex4>`), se fija en el contexto y se emite el EVENTO RAÍZ
    (kind="trace", root=True) con la frase/motivo que lo inicia — es la raíz del árbol en la vista Trazas.
    Llamar en el punto de ENTRADA del estímulo (turno de voz/chat, probe, cron, proactivo). Devuelve el id."""
    global _active, _active_at, _general
    tid = f"T{_next_seq('voice.trace')}·{uuid.uuid4().hex[:4]}"
    _ctx.set((tid, ""))
    # `cluster`/`pulso` son OTRO subsistema (el puente MeshKore, connectors/meshkore/bridge.py) corriendo en el
    # mismo proceso — dejarlos tocar `_active` colgaría eventos del pipeline de VOZ (VAD, TTS, estado) del trace
    # de una conversación de cluster que no tiene nada que ver, la próxima vez que ese puente hiciera un tick.
    if origin not in ("cluster", "pulso"):
        _active, _active_at = tid, time.monotonic()
        if origin == "kickoff":
            _general = tid
    try:
        from voice.observer import emit
        # Cluster mesh housekeeping (peer heartbeat nudges, `connectors/meshkore/bridge.py`) is background
        # plumbing, not a user turn — same family as any other `cluster`-kind event (`_CAT["cluster"]="system"`
        # in observer.py). Without this override the root trace event inherits `cat="flash"` from `kind="trace"`
        # regardless of origin, and `stamp_identity()`'s "background noise never fabricates a session" guard
        # (observer.py, 2026-08-15) only checks `cat in ("system","pulse")` — so a cluster heartbeat firing
        # after the operator stopped the agent (⏻) self-opened a brand-new "live" session, the same bug that
        # guard was meant to close, one `origin` short of complete. "pulso" (2026-08-16) is the SAME family —
        # the heartbeat/evaluator checking in on an idle conversation on its own timer, not a fresh peer message
        # (see bridge.py::_brain_turn) — and gets the identical treatment.
        extra = {"trace": tid, "root": True, "origin": origin}
        if origin in ("cluster", "pulso"):
            extra["cat"] = "system"
        emit("trace", origin, text=(text or "")[:300], role="user" if origin in ("turno", "probe") else "system",
             extra=extra)
    except Exception:
        pass
    return tid


def _seq_of(tid: str) -> int:
    """El número de orden dentro del id ('T29·593e' → 29). 0 si no se puede leer — nunca debe bloquear un merge,
    solo decidir quién es más viejo cuando sí se puede."""
    try:
        return int(str(tid or "").split("·")[0].lstrip("T"))
    except Exception:
        return 0


def merge(a: str, b: str) -> str:
    """Dos traces resultan ser la MISMA tarea (operador, 2026-08-16: "por la segunda o tercera frase nos demos
    cuenta que los dos turnos son el mismo... dejaría esa feature disponible"). El MÁS ANTIGUO (seq más bajo,
    comparación numérica del propio id — nace secuencial, no hace falta guardar timestamps aparte) se queda como
    TITULAR; el más nuevo se funde EN él, nunca al revés — así una tarea larga con varias fusiones converge
    siempre al mismo id, el primero, en vez de ir saltando de titular en cada fusión sucesiva.

    NO reescribe nada ya escrito — el archivo de eventos es append-only a propósito (ver `bus/log.py`: "un JSON
    por línea... se lee con grep/jq diez años después"). En su lugar emite un MARCADOR (`kind="trace",
    label="merge"`, sellado con el trace NUEVO vía `extra={"trace": ...}` — nunca ambiente, para que el marcador
    aparezca bajo el id que se está fundiendo, no bajo el titular) que el lector resuelve: ver
    `cloud/backoffice/src/flowAttribution.js::resolveMerges` (local) y su equivalente en `observability/
    flows.py` para sesiones de nube. Best-effort, nunca lanza. Devuelve el id TITULAR."""
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b or a == b:
        return a or b
    older, newer = (a, b) if _seq_of(a) <= _seq_of(b) else (b, a)
    try:
        from voice.observer import emit
        emit("trace", "merge", role="system", extra={"trace": newer, "merge_into": older})
    except Exception:
        pass
    return older


def current() -> str:
    """Trace id of the current context ("" if none). `observer.emit` reads it on every event — it must be cheap."""
    return _ctx.get()[0]


def current_span() -> str:
    return _ctx.get()[1]


def adopt(tid: str, span: str = "") -> None:
    """Rejoin a trace from ANOTHER context (server loop, writer thread, HTTP handler of a bridge CLI).
    `span` labels the ACTOR ('worker:5', 'web:t2', 'memoria'…) for level 2 of the tree. Best-effort."""
    tid = (tid or "").strip()
    _ctx.set((tid, (span or "").strip()))
    if tid:
        global _active, _active_at
        _active, _active_at = tid, time.monotonic()


@contextmanager
def scope(tid: str, span: str = ""):
    """`with trace.scope(tid, 'memoria'): …` — adopts the trace ONLY during the block (threads that process items
    from different traces in a loop, such as the memory-queue writer)."""
    tid = (tid or "").strip()
    if tid:
        global _active, _active_at
        _active, _active_at = tid, time.monotonic()
    tok = _ctx.set((tid, (span or "").strip()))
    try:
        yield
    finally:
        try:
            _ctx.reset(tok)
        except Exception:
            pass
