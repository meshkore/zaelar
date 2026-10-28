"""Run `ClaudeCodeSession.start` up to its spawn, and hand back what it WOULD launch (refactor2710-09).

The guards on the Claude Code spawn used to read the source of `start` — which ordering, which line follows which.
A split of the backend moves those lines and leaves the guards reading nothing. This is the door instead: the real
`start` runs with the process spawn captured (no CLI, no network), so a guard asserts on the argv and the
environment the worker would actually get.
"""
from __future__ import annotations

import asyncio

from nucleo.workers import providers as prov
from nucleo.workers.base import WorkerSpec
from nucleo.workers.providers import claude as C


class _Stdin:
    def write(self, data):
        pass

    async def drain(self):
        pass


class _Proc:
    stdin = _Stdin()
    pid = 0
    returncode = None


def spawn_of(monkeypatch, *, spec: WorkerSpec | None = None, host_env: dict | None = None,
             chain_env: dict | None = None, tier: dict | None = None) -> dict:
    """`{"argv": [...], "env": {...}, "kw": {...}}` of the one spawn `start` makes. `host_env` is set on the engine's
    own environment (what the worker would inherit); `chain_env` is what the provider chain resolves."""
    for k, v in (host_env or {}).items():
        monkeypatch.setenv(k, v)
    captured: dict = {}

    async def _spawn(*argv, **kw):
        captured.update(argv=list(argv), env=dict(kw.pop("env", {}) or {}), kw=kw)
        return _Proc()

    async def _no_pump(self):
        return None

    monkeypatch.setattr(C._spawned, "spawn", _spawn)
    monkeypatch.setattr(C, "_find_claude", lambda: "/opt/fake/claude")
    monkeypatch.setattr(C.ClaudeCodeSession, "_pump", _no_pump)
    monkeypatch.setattr(prov, "env_for_worker", lambda *a, **k: dict(chain_env or {}))
    monkeypatch.setattr(prov, "pick", lambda *a, **k: tier)
    monkeypatch.setattr(prov, "vision_env", lambda *a, **k: {})
    monkeypatch.setattr(prov, "_is_container", lambda: False)

    async def go():
        s = C.ClaudeCodeSession()
        await s.start("hola", spec=spec or WorkerSpec(task_id="t-spawn"))
        if s._reader_task:
            await s._reader_task
    asyncio.run(go())
    assert captured, "start() never reached the spawn"
    return captured


def grok_spawn_of(monkeypatch, *, spec: WorkerSpec | None = None) -> dict:
    """The same door for the Grok Build worker: `{"argv", "env", "kw", "prompt"}`, where `prompt` is what the
    worker reads from its `--prompt-file` (the file is read at the spawn, before anything removes it)."""
    from nucleo.workers.providers import grok as G
    captured: dict = {}

    async def _spawn(*argv, **kw):
        argv = list(argv)
        captured.update(argv=argv, env=dict(kw.pop("env", {}) or {}), kw=kw)
        if "--prompt-file" in argv:
            with open(argv[argv.index("--prompt-file") + 1], encoding="utf-8") as fh:
                captured["prompt"] = fh.read()
        return _Proc()

    async def _no_pump(self):
        return None

    monkeypatch.setattr(G._spawned, "spawn", _spawn)
    monkeypatch.setattr(G, "find_grok", lambda: "/opt/fake/grok")
    monkeypatch.setattr(G.GrokSession, "_pump", _no_pump)

    async def go():
        s = G.GrokSession()
        await s.start("busca carpinteros", spec=spec or WorkerSpec(task_id="t-grok"))
        if getattr(s, "_reader_task", None):
            await s._reader_task
    asyncio.run(go())
    assert captured, "start() never reached the spawn"
    return captured


def flag(argv: list, name: str) -> str | None:
    """The value after `name` in an argv, or None when the flag is absent."""
    return argv[argv.index(name) + 1] if name in argv else None
