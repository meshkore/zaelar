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
import time
import uuid
from contextlib import contextmanager

# (trace_id, span) del contexto de ejecución actual. "" = sin traza (eventos de arranque, ruido de fondo).
_ctx: contextvars.ContextVar[tuple[str, str]] = contextvars.ContextVar("zaelar_trace", default=("", ""))

_seq = itertools.count(1)

# ── `active()` — el trace vigente para quien NO PUEDE heredarlo del ContextVar (2026-08-16) ──────────────────────
# Auditoría de fuente (operador: "arréglalo en el flash brain... donde se generan los eventos"): varios handlers
# de `voice/engine/pipeline/agent.py` (el estado del pipeline, el VAD, las métricas de TTS/STT, el transcript del
# propio zaelar) corren en tareas de LiveKit que son HERMANAS —nunca DESCENDIENTES— de la tarea donde
# `NucleoLLMStream._run_inner` fija el trace del turno (confirmado contra el código fuente de livekit-agents
# 1.6.6: `AgentActivity._pipeline_reply_task`/`AudioRecognition._stt_consumer_atask` existen ANTES de que el
# turno empiece a procesarse). `asyncio.create_task` copia el ContextVar solo hacia HIJOS — nunca hacia una tarea
# hermana ni hacia atrás en el tiempo — así que ningún truco de propagación arregla esto: no es un fallo, es cómo
# funciona `contextvars` por diseño. La sesión real que lo probó: de 17 transcripciones, 13 llegaban con
# `corr_id: null`; VAD, nunca ninguna.
#
# `active()` es la respuesta: un puntero EXPLÍCITO (no ContextVar), que `begin()`/`adopt()` mantienen al día, y
# que esos handlers leen a propósito en vez de fiarse del ContextVar ambiente. Caduca solo (`max_age_s`, por
# defecto 3s): un evento que llega mucho después de que el último trace se fijara no se le cuelga a un turno que
# probablemente ya cerró —eso reabriría en el master un flujo "cerrado" con actividad fantasma, justo el bug que
# `_maybe_close_flow`/`drain_pending_flow_closes` (mismo día) arreglaron por el otro lado— y cae al trace GENERAL
# de la sesión (`_general`, fijado por el kickoff) en su lugar: "se atribuye a la charla general, bienvenida, etc"
# es literalmente lo que pidió el operador para lo que no tiene tarea propia, no un cajón sin fondo — sigue
# acotado en el tiempo y sigue siendo un flujo normal que algún día cierra.
#
# Deliberadamente NO se usa para el transcript FINAL del operador ni para sus fragmentos: ese texto es la causa
# de que el turno empiece, así que en el instante en que se emite el trace del turno TODAVÍA no existe —
# adjuntarle `active()` ahí le pegaría el trace del turno ANTERIOR, que es peor que no llevar ninguno. Ese caso
# se resuelve en el master, en lectura (`cloud/backoffice/src/flowAttribution.js::attributeOrphans`), que sí
# conoce ambos lados de la ventana temporal y por eso puede decidir bien.
_active: str = ""
_active_at: float = 0.0
_general: str = ""   # el trace de "charla general" (el kickoff) — suelo de active() una vez arrancada la sesión


def active(max_age_s: float = 3.0) -> str:
    """El trace vigente para un lector que no puede heredarlo del ContextVar. Nunca inventa uno si la sesión
    todavía no ha arrancado (kickoff no ha corrido) — devuelve "", igual que `current()` sin traza."""
    if _active and (time.monotonic() - _active_at) <= max_age_s:
        return _active
    return _general


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
    global _active, _active_at, _general
    tid = f"T{next(_seq)}·{uuid.uuid4().hex[:4]}"
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
    """Trace id del contexto actual ("" si no hay). Lo lee `observer.emit` en cada evento — debe ser barato."""
    return _ctx.get()[0]


def current_span() -> str:
    return _ctx.get()[1]


def adopt(tid: str, span: str = "") -> None:
    """Re-unirse a un trace desde OTRO contexto (loop del server, hilo del writer, handler HTTP de un CLI puente).
    `span` etiqueta el ACTOR ('worker:5', 'web:t2', 'memoria'…) para el nivel 2 del árbol. Best-effort."""
    tid = (tid or "").strip()
    _ctx.set((tid, (span or "").strip()))
    if tid:
        global _active, _active_at
        _active, _active_at = tid, time.monotonic()


@contextmanager
def scope(tid: str, span: str = ""):
    """`with trace.scope(tid, 'memoria'): …` — adopta el trace SOLO durante el bloque (hilos que procesan items
    de distintas trazas en bucle, como el writer de la cola de memoria)."""
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
