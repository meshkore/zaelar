"""Every worker backend names the session it opens (2026-10-14).

The operator gate recognises an ORPHANED worker process — `( curl … & )`, reparented to launchd/init, its
ancestry no longer naming the engine — only by its session id, and only if that session was remembered in
`nucleo/workers/spawned.py`. A backend that spawns around it is a worker whose orphans pass as his terminal, and
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

from nucleo.workers import spawned

ENGINE = Path(__file__).resolve().parents[4]
BACKENDS = ["nucleo/workers/claude_session.py", "nucleo/workers/codex_session.py",
            "nucleo/workers/grok_session.py"]


def _calls(tree, name):
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)
            and (getattr(n.func, "attr", None) == name or getattr(n.func, "id", None) == name)]


@pytest.mark.parametrize("path", BACKENDS)
def test_the_backend_spawns_through_the_registry(path):
    tree = ast.parse((ENGINE / path).read_text(encoding="utf-8"))
    assert not _calls(tree, "create_subprocess_exec"), f"{path}: a bare spawn leaves the worker's session unnamed"
    spawns = [c for c in _calls(tree, "spawn") if ast.unparse(c.func) == "_spawned.spawn"]
    assert spawns, f"{path}: the worker CLI is not spawned through spawned.spawn"
    assert all(any(k.arg == "start_new_session" for k in c.keywords) for c in spawns)


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
