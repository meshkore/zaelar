"""A worker with no routed tier inside a container fails LOUD instead of spawning `claude` unrouted (V2-778 F5-40).

In a container the licence rung is dropped and keyless rungs are skipped, so when the chain is exhausted
`env_for_worker()` answers `{}` — and the session used to launch the CLI anyway, with no endpoint and no login,
to die later with an error that named nothing. It now says why, as an `alert` the operator's view and the
Master can see, and the session ends as an error before any process starts. Off a container nothing changes:
`{}` there means the local licence, which is a real rung.
"""
from __future__ import annotations

import asyncio

from nucleo.workers import claude_session as cs
from nucleo.workers import providers


def _drain(q) -> list:
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


def test_no_tier_in_a_container_is_an_error_before_any_process(monkeypatch):
    from voice import observer
    seen = []
    monkeypatch.setattr(observer, "emit", lambda *a, **k: seen.append((a, k)))
    monkeypatch.setattr(cs, "_find_claude", lambda: "/usr/bin/claude")
    monkeypatch.setattr(providers, "env_for_worker", lambda: {})
    monkeypatch.setattr(providers, "pick", lambda: None)
    monkeypatch.setattr(providers, "_is_container", lambda: True)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    async def _no_spawn(*a, **k):
        raise AssertionError("a process was started with no routed tier")
    monkeypatch.setattr(cs.asyncio, "create_subprocess_exec", _no_spawn)
    s = cs.ClaudeCodeSession()
    spec = type("S", (), {"task_id": "t1", "model": "", "resume_sid": "", "deny_tools": True, "tools": [],
                          "env": {}, "read_dirs": [], "extra_args": [], "kind": "generic", "token": "",
                          "cwd": ""})()
    asyncio.run(s.start("hola", spec=spec))
    evs = _drain(s._q)
    errs = [e for e in evs if e.type == "error"]
    assert errs and errs[0].data.get("fatal") and "contenedor" not in "" , evs
    assert "a process was started" not in str(errs[0].data.get("message")), "it must stop BEFORE spawning"
    assert any(len(a) > 0 and a[0] == "alert" for a, _ in seen), "the operator's view and the Master hear why"
