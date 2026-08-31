"""nucleo/agentes/ — the SlowBrain agent constellation behind the `CodeAgent` interface. V2-006.

`base.py` defines the provider-agnostic `CodeAgent` interface; `claude_code.py` implements it over
headless Claude Code (`claude -p`), and `codex.py` over Codex — interchangeable, **model per invocation**.
The MEMORY agent ★ (`nucleo/memory_agent.py`) and, since V2-007, work agents (web/code/other) run through this interface.

`get_agent(provider)` selects from configuration: without an argument it reads `config/v2 › code_agent.provider`
(managed by the UI; `CODE_AGENT_PROVIDER` is the fallback environment variable). Changing the provider does not affect the dispatcher.
"""
from __future__ import annotations

from functools import lru_cache

from .base import CodeAgent, RunResult, RunSpec, WorkResult  # noqa: F401 (re-export del contrato)

__all__ = ["CodeAgent", "RunSpec", "RunResult", "WorkResult", "get_agent", "AGENTS"]

# Provider-to-class registry (extensible: a new provider means one entry and its module).
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
