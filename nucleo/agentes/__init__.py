"""nucleo/agentes/ — la constelación de agentes del SlowBrain tras la interfaz `CodeAgent`. V2-006.

`base.py` fija la interfaz `CodeAgent` (agnóstica del proveedor); `claude_code.py` la implementa sobre
Claude Code headless (`claude -p`), `codex.py` sobre Codex — intercambiables, **modelo por invocación**.
Sobre esta interfaz corren el agente de MEMORIA ★ (`nucleo/memory_agent.py`) y, desde V2-007, los agentes de
trabajo (web/código/otros).

`get_agent(provider)` es la SELECCIÓN POR CONFIG: sin argumento lee `config/v2 › code_agent.provider`
(gestionado por la UI; env `CODE_AGENT_PROVIDER` de fallback). Cambiar el proveedor NO toca al dispatcher.
"""
from __future__ import annotations

from functools import lru_cache

from .base import CodeAgent, RunResult, RunSpec, WorkResult  # noqa: F401 (re-export del contrato)

__all__ = ["CodeAgent", "RunSpec", "RunResult", "WorkResult", "get_agent", "AGENTS"]

# registro proveedor → clase (ampliable: un proveedor nuevo = una entrada + su módulo)
AGENTS: dict[str, type] = {}


def _register():
    from .claude_code import ClaudeCodeAgent
    from .codex import CodexAgent
    AGENTS.update({"claude_code": ClaudeCodeAgent, "codex": CodexAgent})


def get_agent(provider: str | None = None) -> CodeAgent:
    """Devuelve una instancia del `CodeAgent` seleccionado. `provider=None` → el de config/v2 (default
    `claude_code`). Un proveedor desconocido cae al default con un aviso (nunca revienta el dispatcher)."""
    if not AGENTS:
        _register()
    if provider is None:
        try:
            from config import v2 as _v2
            provider = (_v2.code_agent_spec() or {}).get("provider") or "claude_code"
        except Exception:
            provider = "claude_code"
    cls = AGENTS.get(provider)
    if cls is None:
        from loguru import logger
        logger.warning(f"slowbrain: proveedor de code-agent desconocido {provider!r} → claude_code")
        cls = AGENTS["claude_code"]
    return _instance(cls)


@lru_cache(maxsize=8)
def _instance(cls: type) -> CodeAgent:
    return cls()  # type: ignore[call-arg]
