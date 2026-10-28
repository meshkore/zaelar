"""Every worker backend names the session it opens (2026-10-14).

The operator gate recognises an ORPHANED worker process — `( curl … & )`, reparented to launchd/init, its
ancestry no longer naming the engine — only by its session id, and only if that session was remembered in
`nucleo/workers/providers/spawned.py`. A backend that spawns around it is a worker whose orphans pass as his terminal, and
nothing else would fail. So: every backend spawns its CLI through `spawned.spawn(..., start_new_session=True)`
and never through a bare `create_subprocess_exec`; `spawn` remembers the pid, and refuses a spawn without a
session of its own rather than leave it unmarked.
"""
from __future__ import annotations

import ast
import asyncio
import os
import sys
from pathlib import Path

import pytest

from nucleo.workers.providers import spawned

ENGINE = Path(__file__).resolve().parents[4]
#: The provider PACKAGE, not a list of files: a backend split into several modules is still covered, and a backend
#: added later is covered without anyone remembering to list it (refactor2710-09).
PROVIDERS = ENGINE / "nucleo" / "workers" / "providers"
BACKENDS = ["claude", "codex", "grok"]


def _calls(tree, name):
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)
            and (getattr(n.func, "attr", None) == name or getattr(n.func, "id", None) == name)]


def _family(backend: str) -> list:
    """The backend's module and the modules split out of it (`claude.py`, `claude_start.py`…)."""
    return [p for p in sorted(PROVIDERS.glob("*.py")) if p.stem == backend or p.stem.startswith(backend + "_")]


def test_no_provider_module_spawns_bare():
    for p in sorted(PROVIDERS.glob("*.py")):
        if p.stem == "spawned":
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        assert not _calls(tree, "create_subprocess_exec"), f"{p.name}: a bare spawn leaves the worker's session unnamed"


@pytest.mark.parametrize("backend", BACKENDS)
def test_the_backend_spawns_through_the_registry(backend):
    files = _family(backend)
    assert files, f"no module for the {backend} backend"
    spawns = [c for p in files for c in _calls(ast.parse(p.read_text(encoding="utf-8")), "spawn")
              if ast.unparse(c.func).endswith("_spawned.spawn")]
    assert spawns, f"{backend}: the worker CLI is not spawned through spawned.spawn"
    assert all(any(k.arg == "start_new_session" for k in c.keywords) for c in spawns)


def test_the_claude_worker_opens_its_own_session(monkeypatch):
    """At the door: the real `start` of the Claude Code worker spawns with a session of its own."""
    from tests.agent_headless.unit.workers.claude_spawn import spawn_of
    assert spawn_of(monkeypatch)["kw"].get("start_new_session") is True


@pytest.fixture
def _clean():
    spawned.forget_all()
    yield
    spawned.forget_all()


@pytest.mark.skipif(not hasattr(os, "getsid"), reason="POSIX sessions")
def test_spawn_remembers_the_session_it_opens(_clean):
    async def go():
        p = await spawned.spawn(sys.executable, "-c", "pass", start_new_session=True)
        await p.wait()
        return p.pid
    pid = asyncio.run(go())
    assert pid in spawned.sessions(), "kept after it exited: an orphan outlives its worker"


def test_spawn_refuses_a_worker_without_its_own_session(_clean):
    with pytest.raises(ValueError):
        asyncio.run(spawned.spawn(sys.executable, "-c", "pass"))
    assert not spawned.sessions()


def test_the_registry_ignores_junk(_clean):
    spawned.remember(None)
    spawned.remember(-1)
    assert not spawned.sessions()
