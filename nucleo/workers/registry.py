"""nucleo/workers/registry.py — AGNOSTIC factory for worker backends (V2-038).

`get_backend(spec)` chooses the engine from CONFIG (by task type, mixable), without dispatch/FlashBrain knowing
the specific CLI. It is the only place that knows which class to instantiate → changing the engine = changing config;
running Claude for web + Codex for code at the same time = instantiating two different classes. (Evolution of
`nucleo/agentes/get_agent`.)

Selection: env `WORKER_BACKEND` (global, for tests) → `config/v2.py §code_agent.provider[_<kind>]` → default
`claude_code`. Keep the import decoupled (lazy) so dependencies are not pulled in if a backend is not used.
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
        # per-type override (provider_web/provider_code/…) → global provider → claude_code
        prov = ca.get(f"provider_{kind}") or ca.get("provider") or ""
        prov = (prov or "").strip()
        if prov:
            return prov
    except Exception:
        pass
    return "claude_code"


def _is_widget_task(spec: "WorkerSpec") -> bool:
    """A `code` task that CREATES/MODIFIES a widget → generator backend (preserves contract+validation,
    §v3·Q4). Reads the request from spec.env (dispatch puts it there). Architect or another `code` task → generic backend."""
    if (spec.kind or "") != "code":
        return False
    req = (spec.env or {}).get("ZAELAR_TASK_REQUEST") or ""
    try:
        from nucleo.agentes import code as _code
        return bool(_code.is_widget_request(req) or _code._DELETE_RE.search(req)) \
            and not _code.is_architect_request(req)
    except Exception:
        # without the helpers, fall back to a minimal heuristic
        return "widget" in req.lower() or "tarjeta" in req.lower()


def get_backend(spec: "WorkerSpec") -> "WorkerBackend":
    """Returns a NEW backend instance for `spec` (one per session). Fail-safe to claude_code."""
    # widget task → unified generator (killable + validated), unless there is an explicit backend override.
    if not (os.getenv("WORKER_BACKEND") or "").strip() and _is_widget_task(spec):
        from .generator_session import GeneratorBackend
        return GeneratorBackend()
    prov = _provider_for(spec.kind or "generic")
    if prov == "codex":
        # MIXABLE by CAPABILITY, not only by task type (2026-08-12): Codex cannot restrict its tools
        # (it only has sandbox modes), so the two tasks that MUST be restricted —UNTRUSTED input
        # (V2-010) and a cluster peer's dev worker— go to the backend that CAN, even if the config
        # says Codex. The alternative was to fail the task: worse, because the operator chooses a provider for normal
        # work and would simultaneously lose the cluster capabilities for no apparent reason. It is STATED in the log
        # (this is not silent: it is capability-based routing, and the single-writer invariant takes precedence over a
        # config preference). `codex_session` retains its fail-closed rejection as defense in depth.
        if spec.deny_tools or (spec.kind or "") == "dev":
            import logging
            logging.getLogger(__name__).info(
                "worker[%s]: kind=%s deny_tools=%s → claude_code (Codex no puede acotar sus tools)",
                spec.task_id or "?", spec.kind, spec.deny_tools)
        else:
            from .codex_session import CodexSession
            return CodexSession()
    if prov == "grok_build":
        # Grok Build does NOT need the redirect above: it accepts our `Bash(...)` rules and ENFORCES them (tested), so
        # it can uphold the single-writer invariant just like Claude Code — including a task with
        # `deny_tools`, which starts without any tool.
        from .grok_session import GrokSession
        return GrokSession()
    # default + fail-safe
    from .claude_session import ClaudeCodeSession
    return ClaudeCodeSession()


def available_backends() -> set[str]:
    return set(_BACKENDS)
