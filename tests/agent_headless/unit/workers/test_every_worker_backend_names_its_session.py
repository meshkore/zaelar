"""Every worker backend names the session it opens (2026-10-14).

The operator gate recognises an ORPHANED worker process — `( curl … & )`, reparented to launchd/init, its
ancestry no longer naming the engine — only by its session id, and only if the backend that spawned the worker
told `nucleo/workers/spawned.py` about it. A backend that forgets is a worker whose orphans pass as his terminal,
and nothing else would fail. So each backend is read: in the function that runs `create_subprocess_exec(...,
start_new_session=True)`, the spawned pid has to be remembered after it.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from nucleo.workers import spawned

ENGINE = Path(__file__).resolve().parents[4]
BACKENDS = ["nucleo/workers/claude_session.py", "nucleo/workers/codex_session.py",
            "nucleo/workers/grok_session.py"]


def _calls(node, name):
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)
            and (getattr(n.func, "attr", None) == name or getattr(n.func, "id", None) == name)]


@pytest.mark.parametrize("path", BACKENDS)
def test_the_backend_remembers_the_session_it_spawns(path):
    tree = ast.parse((ENGINE / path).read_text(encoding="utf-8"))
    spawners = [f for f in ast.walk(tree) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                and _calls(f, "create_subprocess_exec")]
    assert spawners, f"{path}: no spawn found — the backend changed shape, re-read it"
    for fn in spawners:
        spawn = _calls(fn, "create_subprocess_exec")[0]
        assert any(k.arg == "start_new_session" for k in spawn.keywords), "the session id is the worker's pid"
        remembers = [c for c in _calls(fn, "remember")
                     if c.lineno > spawn.lineno and "self._proc.pid" in ast.unparse(c)]
        assert remembers, f"{path}::{fn.name} spawns a worker and never names its session"


def test_the_registry_keeps_dead_sessions_and_ignores_junk():
    spawned.forget_all()
    try:
        spawned.remember(4242)
        spawned.remember(None)
        spawned.remember(-1)
        assert spawned.sessions() == frozenset({4242}), "an orphan outlives its worker: kept until the cap"
    finally:
        spawned.forget_all()
