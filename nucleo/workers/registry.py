"""nucleo/workers/registry.py — factoría AGNÓSTICA de backends de worker (V2-038).

`get_backend(spec)` elige el motor por CONFIG (por tipo de tarea, mezclable), sin que dispatch/FlashBrain conozcan
el CLI concreto. Es el único sitio que sabe qué clase instanciar → cambiar de motor = cambiar config; correr Claude
para web + Codex para código a la vez = instanciar dos clases distintas. (Evolución de `nucleo/agentes/get_agent`.)

Selección: env `WORKER_BACKEND` (global, para pruebas) → `config/v2.py §code_agent.provider[_<kind>]` → default
`claude_code`. Sin acoplar el import (lazy) para no arrastrar dependencias si un backend no se usa.
"""
from __future__ import annotations

import os

from .base import WorkerBackend, WorkerSpec

_BACKENDS = {"claude_code", "codex", "grok_build"}


def _provider_for(kind: str) -> str:
    env = (os.getenv("WORKER_BACKEND") or "").strip()
    if env:
        return env
    try:
        from config import v2 as _v2
        ca = _v2.get("code_agent") or {}
        # override por tipo (provider_web/provider_code/…) → provider global → claude_code
        prov = ca.get(f"provider_{kind}") or ca.get("provider") or ""
        prov = (prov or "").strip()
        if prov:
            return prov
    except Exception:
        pass
    return "claude_code"


def _is_widget_task(spec: "WorkerSpec") -> bool:
    """Una tarea `code` que es CREAR/MODIFICAR un widget → backend del generador (conserva contrato+validación,
    §v3·Q4). Lee el request de spec.env (lo pone dispatch). Architect u otro `code` → backend genérico."""
    if (spec.kind or "") != "code":
        return False
    req = (spec.env or {}).get("ZAELAR_TASK_REQUEST") or ""
    try:
        from nucleo.agentes import code as _code
        return bool(_code.is_widget_request(req) or _code._DELETE_RE.search(req)) \
            and not _code.is_architect_request(req)
    except Exception:
        # sin los helpers, cae a heurística mínima
        return "widget" in req.lower() or "tarjeta" in req.lower()


def get_backend(spec: "WorkerSpec") -> "WorkerBackend":
    """Devuelve una instancia NUEVA del backend para `spec` (una por sesión). Fail-safe a claude_code."""
    # tarea de widget → generador unificado (matable + validado), salvo override explícito de backend.
    if not (os.getenv("WORKER_BACKEND") or "").strip() and _is_widget_task(spec):
        from .generator_session import GeneratorBackend
        return GeneratorBackend()
    prov = _provider_for(spec.kind or "generic")
    if prov == "codex":
        # MEZCLABLE por CAPACIDAD, no solo por tipo de tarea (2026-08-12): Codex no sabe acotar sus herramientas
        # (solo tiene modos de sandbox), así que las dos tareas que EXISTEN para estar acotadas —entrada NO
        # confiable (V2-010) y el dev worker de un peer de cluster— van al backend que SÍ puede, aunque la config
        # diga Codex. La alternativa era fallar la tarea: peor, porque el operador elige un proveedor para su
        # trabajo normal y perdería a la vez las capacidades del cluster sin relación aparente. Se DICE en el log
        # (no es un silencio: es un enrutado por capacidad, y el invariante del escritor único manda sobre una
        # preferencia de config). `codex_session` conserva su rechazo fail-closed como defensa en profundidad.
        if spec.deny_tools or (spec.kind or "") == "dev":
            import logging
            logging.getLogger(__name__).info(
                "worker[%s]: kind=%s deny_tools=%s → claude_code (Codex no puede acotar sus tools)",
                spec.task_id or "?", spec.kind, spec.deny_tools)
        else:
            from .codex_session import CodexSession
            return CodexSession()
    if prov == "grok_build":
        # Grok Build NO necesita el desvío de arriba: acepta nuestras reglas `Bash(...)` y las APLICA (probado), así
        # que puede sostener el invariante del escritor único igual que Claude Code — incluida una tarea con
        # `deny_tools`, que arranca sin ninguna tool.
        from .grok_session import GrokSession
        return GrokSession()
    # default + fail-safe
    from .claude_session import ClaudeCodeSession
    return ClaudeCodeSession()


def available_backends() -> set[str]:
    return set(_BACKENDS)
