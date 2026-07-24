"""nucleo/workers/ — Brain Workers interactivos (V2-038). Sustrato AGNÓSTICO del motor de agente.

Contrato (`base`): `WorkerBackend` (sesión viva: start/send/events/stop) + `WorkerEvent` (vocabulario normalizado)
+ `WorkerSpec`. Backends: `claude_session.ClaudeCodeSession` (stream-json), `codex_session.CodexSession` (stub).
Selección por config: `registry.get_backend(spec)`. Diseño: initiatives/V2-038-brain-workers-interactivos.md.
"""
from .base import EVENT_CONTRACT_V, EVENT_TYPES, WorkerBackend, WorkerEvent, WorkerSpec
from .registry import available_backends, get_backend

__all__ = [
    "WorkerBackend", "WorkerEvent", "WorkerSpec", "EVENT_TYPES", "EVENT_CONTRACT_V",
    "get_backend", "available_backends",
]
