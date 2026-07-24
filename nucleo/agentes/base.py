"""nucleo/agentes/base.py — interfaz `CodeAgent` (agnóstica del proveedor). V2-006 · T77.

Costura estable que desacopla el SlowBrain del proveedor concreto de agente de código (Claude Code hoy,
Codex mañana): el dispatcher (`nucleo/dispatch.py`) habla SIEMPRE con esta interfaz, nunca con un CLI concreto.
Reglas duras que TODA implementación debe respetar (V2-010):
  - **Modelo POR INVOCACIÓN** (`run(prompt, spec=RunSpec)` con `spec.model`), NUNCA una env global de modelo
    (dos tareas concurrentes pueden querer modelos distintos sin pisarse).
  - **Sandbox**: `cwd`, `timeout` y política de tools (`spec.tools`) acotados; `deny_tools=True` para input NO
    confiable → NINGUNA tool (ni fichero ni terminal), el agente solo razona/redacta.
  - Salida pasa por `scan_outbound` (secretos/identidad) antes de volver al operador/peer (lo aplica el
    dispatcher en V2-007/V2-010, no cada adaptador).

El `prompt` se pasa como argumento posicional (no dentro del spec): un mismo `RunSpec` de política —modelo,
tools, cwd, timeout— sirve para varias invocaciones con prompts distintos.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunSpec:
    """Parámetros de una ejecución de agente. Modelo POR INVOCACIÓN.

    Campos (== el `spec = {prompt,model,tools,cwd,timeout}` del diseño; `prompt` va aparte, posicional):
      - `model`      — id del modelo, pasado por invocación (vacío = default del proveedor).
      - `tools`      — allowlist de herramientas (p. ej. `["Read"]`); `None` = política por defecto del adaptador.
                       IGNORADA si `deny_tools` (input no confiable → sin tools).
      - `cwd`        — directorio de trabajo aislado (None = raíz de zaelar).
      - `timeout`    — segundos máximos; al superarse el proceso se mata y `RunResult.ok=False`.
      - `deny_tools` — True = input NO confiable (V2-010): el agente corre SIN ninguna herramienta.
      - `env`        — variables de entorno extra para el subproceso.
    """
    model: str = ""
    tools: list[str] | None = None
    cwd: str | None = None
    timeout: float = 600.0
    deny_tools: bool = False               # True = input no confiable (V2-010)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class RunResult:
    ok: bool
    output: str = ""
    error: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkResult:
    """Resultado de un **agente de trabajo** del SlowBrain (web/código/genérico, V2-007). Una capa por encima
    de `RunResult`: no es la salida cruda de UN `CodeAgent`, sino lo que la tarea deja para el operador.

      - `ok`       — la tarea se resolvió (o arrancó, en el caso async del navegador).
      - `summary`  — texto operator-facing: lo que se dice por voz+UI y se guarda en memoria.
      - `deliver`  — ¿el dispatcher entrega `summary` por `proactive.notify` + `[SISTEMA]`? **False** para el
                     agente web: su tarjeta/owner reporta el resultado real cuando termina (async), no aquí.
      - `error`    — motivo si `ok=False` (para el brain, no necesariamente para el operador).
      - `meta`     — extras (id de widget/tarea creada, `needs_confirm`, …).
    """
    ok: bool
    summary: str = ""
    deliver: bool = True
    error: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


class CodeAgent(ABC):
    """Un agente de código headless. Implementaciones: `ClaudeCodeAgent`, `CodexAgent`."""

    name: str = "codeagent"

    @abstractmethod
    async def run(self, prompt: str, *, spec: "RunSpec") -> "RunResult":
        """Ejecuta `prompt` bajo `spec` (sandbox/cwd/timeout/deny_tools) y devuelve el resultado."""
        raise NotImplementedError
