"""nucleo/workers/base.py — contrato AGNÓSTICO de los Brain Workers (V2-038).

Un **Brain Worker** es una sesión de trabajo VIVA, interactiva y bidireccional (conducir el navegador, crear/
modificar un widget, hacer un estudio…), orquestada por el FlashBrain. El motor concreto (Claude Code hoy; Codex,
Cursor o Hermes mañana, incluso mezclados) es un **backend SUSTITUIBLE por config**. El resto del sistema —dispatch,
FlashBrain, ESTADO, UI— habla SIEMPRE este contrato, NUNCA un CLI concreto. Esa es la agnosticidad (objetivo O1).

Tres piezas:
  - `WorkerEvent`  — el vocabulario NORMALIZADO que todo backend traduce desde su protocolo nativo (§5 del diseño).
  - `WorkerSpec`   — parámetros de una sesión (modelo POR INVOCACIÓN, tools, token de bridges, límites de cadena…).
  - `WorkerBackend`— la interfaz de sesión interactiva: start / send (↓ inyectar) / events (↑) / stop (kill cortés).

Diseño canónico: `.meshkore/roadmap/initiatives/V2-038-brain-workers-interactivos.md`.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator

# Versión del contrato de eventos. Sube si cambia la SEMÁNTICA de un tipo/campo — así pueden convivir adaptadores
# de generaciones distintas (§REVISIÓN v2·F). No subir por añadir un tipo nuevo (es aditivo).
EVENT_CONTRACT_V = 1

# Vocabulario de tipos de evento (§5). `data` lleva el payload concreto de cada tipo → aditivo, no rediseñar el
# dataclass para añadir un campo (objetivo O7 "no modificar más").
#   phase    data={label}                          progreso (etiqueta breve). → registro RAM (fase) + chip.
#   say      data={text}                            decir algo al usuario (EXPLÍCITO, no derivado). → voz+UI.
#   ask      data={question, options?, corr_id}     preguntar y ESPERAR respuesta. → plano request/response.
#   act      data={action, payload, corr_id?}       pedir una acción mediada (use_tool/read_widget/…). → política.
#   result   data={summary, ok, data?}              entregable final. → voz+UI + memoria.
#   progress data={pct?, note?}                      avance cuantitativo. → chip.
#   error    data={message, fatal}                  fallo (fatal cierra la sesión).
#   done     data={}                                 la sesión terminó.
#   spawned  data={native_session_id?}               la sesión nació (init del backend). → captura session_id (Q6).
EVENT_TYPES = ("phase", "say", "ask", "act", "result", "progress", "error", "done", "spawned")


@dataclass
class WorkerEvent:
    """Un evento NORMALIZADO emitido por un backend. `data` es libre por tipo (extensible sin tocar el contrato)."""
    task_id: str
    type: str
    data: dict = field(default_factory=dict)
    v: int = EVENT_CONTRACT_V
    backend: str = ""
    ts: float = 0.0

    def __post_init__(self):
        if not self.ts:
            self.ts = time.time()


@dataclass
class WorkerSpec:
    """Parámetros de una sesión de worker. Modelo POR INVOCACIÓN (jamás env global, regla dura del cerebro)."""
    kind: str = "generic"                  # 'web' | 'code' | 'memory' | 'research' | 'generic'
    model: str = ""                        # id del modelo (vacío = default del proveedor)
    tools: list[str] | None = None         # allowlist; None = política por defecto del backend
    cwd: str | None = None
    deny_tools: bool = False               # input NO confiable (V2-010) → SIN tools NI bridges (§REVISIÓN v3·P)
    env: dict = field(default_factory=dict)
    trusted: bool = True
    task_id: str = ""                      # id de sesión (bridges/estado/kill)
    resume_sid: str = ""                    # V2-049: session_id NATIVO a REANUDAR (`--resume`) — continúa el
                                            # razonamiento de un worker anterior de la MISMA gestión (no de cero)
    # ── V2-038 §REVISIÓN v3·O ──
    token: str = ""                        # auth por-tarea de los bridges (aleatorio, verificado en /api/worker/*)
    parent_task_id: str = ""               # cadena (act spawn)
    depth: int = 0                         # profundidad de cadena (acota fork-bomb)
    budget: dict = field(default_factory=dict)   # topes tokens/tiempo por worker (fallback a tiempo sin `usage`)


class WorkerBackend(ABC):
    """Sesión de trabajo interactiva sobre un motor concreto. Traduce el protocolo nativo a `WorkerEvent`.

    Ciclo: `start(prompt, spec)` arranca la sesión VIVA (no bloquea hasta el fin) → `events()` emite el stream ↑ →
    `send(text)` inyecta un turno ↓ → `stop(grace)` cierra con cortesía. `alive` refleja si el proceso vive.
    `native_session_id()` devuelve el id de sesión del motor (para `--resume` futuro, §REVISIÓN v2·E·Q6)."""

    name: str = "base"

    @abstractmethod
    async def start(self, prompt: str, *, spec: "WorkerSpec") -> None:
        raise NotImplementedError

    @abstractmethod
    async def send(self, text: str) -> None:
        """Inyecta una instrucción/turno nuevo (↓). NB: en motores de turno largo, stdin se encola hasta que el
        turno cierra — por eso la vía PRINCIPAL de inyección es el piggyback en bridges (dispatch), y esto es la
        vía secundaria (§REVISIÓN v2·A)."""
        raise NotImplementedError

    @abstractmethod
    def events(self) -> AsyncIterator["WorkerEvent"]:
        """Async iterator del stream de eventos normalizados hasta `done`/`error(fatal)`."""
        raise NotImplementedError

    @abstractmethod
    async def stop(self, *, grace: float = 3.0) -> None:
        """Cierre con cortesía: fin de entrada → SIGTERM al GRUPO → espera `grace` → SIGKILL al grupo. Nunca lanza."""
        raise NotImplementedError

    @property
    @abstractmethod
    def alive(self) -> bool:
        raise NotImplementedError

    def native_session_id(self) -> str:
        """Id de sesión NATIVO del motor (para `--resume`). Vacío si el backend no lo expone."""
        return ""

    # ── V2-065 (2026-07-23, petición del operador) ──────────────────────────────────────────────────────────
    # PAUSAR ≠ matar: el operador quiere un botón que congele el trabajo en curso SIN destruirlo — a diferencia
    # de `stop()` (cortesía→SIGTERM→SIGKILL, irreversible) o de `nucleo/reset.py::reset_all()` (mata de verdad).
    # CONCRETAS con default no-op (no abstractas): un backend que no puede pausar de verdad simplemente no hace
    # nada — nunca rompe el contrato agnóstico. `claude_session` las sobreescribe con SIGSTOP/SIGCONT reales.
    def pause(self) -> bool:
        """Best-effort: congela el proceso en el sitio (sin matarlo) — `resume()` lo continúa exactamente donde
        estaba. Devuelve False si este backend no soporta pausar de verdad (no-op, nunca lanza)."""
        return False

    def resume(self) -> bool:
        """Reanuda un backend pausado. Devuelve False si no había nada que reanudar o el backend no lo soporta."""
        return False

    @property
    def paused(self) -> bool:
        return False
