"""The widget agent never inherits the host's Claude Code session (V2-781 T532, 2026-10-10).

build-workout-tracker-widget, both languages: the widget agent's `claude` died on «401 … Your api key: ****2wAA is
invalid» and then «****SgAA» — keys that are in no credential store: the host Claude Code session's own routing
(`CLAUDECODE`, `CLAUDE_CODE_*`, `ANTHROPIC_BASE_URL`) rode into the child env and the CLI authenticated with it.
The Brain Workers strip exactly that (`claude_session._without_host_routing`); the generator copied `os.environ`
whole. Same strip now — the chain's own `ANTHROPIC_*` is what the agent gets.
"""
from __future__ import annotations

import subprocess


def test_the_spawn_env_carries_the_chain_and_not_the_host(monkeypatch, tmp_path):
    from widgets import generator as G
    from nucleo.workers import providers as P
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_SCOPES", "host")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://host.example")
    monkeypatch.setattr(P, "env_for_worker", lambda: {"ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
                                                      "ANTHROPIC_AUTH_TOKEN": "chain-token"})
    monkeypatch.setattr(P, "pick", lambda: {"name": "z.ai", "model": "glm-x"})
    seen = {}

    class _P:
        returncode = 0
        def __init__(self, cmd, **kw):
            seen.update(kw.get("env") or {})
        def communicate(self, *a, **k):
            return ("{}", "")
    monkeypatch.setattr(subprocess, "Popen", _P)
    try:
        G._run_agent_once("make a widget", "tok", target=str(tmp_path))
    except Exception:  # noqa: BLE001 — only the env handed to the spawn is under test
        pass
    assert seen, "the spawn was reached"
    assert seen.get("ANTHROPIC_BASE_URL") == "https://api.z.ai/api/anthropic"
    assert seen.get("ANTHROPIC_AUTH_TOKEN") == "chain-token"
    assert "CLAUDECODE" not in seen and not any(k.startswith("CLAUDE_CODE_") for k in seen), sorted(seen)
