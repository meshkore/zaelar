"""A worker's endpoint comes from its spec or the provider chain, never from the engine's inherited shell.

Measured 2026-09-28 (demo pass, A1): the engine was restarted from inside a Claude Code session, whose shell
exports `ANTHROPIC_BASE_URL=https://api.anthropic.com`. The spawn read that as «the caller pinned an endpoint»,
skipped the chain, asked Anthropic for `glm-5.3`, and every errand died in two seconds with «There's an issue
with the selected model» — the operator's monitor search, three relays, zero work.
"""
from nucleo.workers.providers import claude as cs

HOST = {"PATH": "/usr/bin", "HOME": "/h", "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
        "ANTHROPIC_AUTH_TOKEN": "host-token", "CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "x",
        "CLAUDE_CODE_CHILD_SESSION": "1", "CLAUDE_AGENT_SDK_VERSION": "1", "DEEPSEEK_API_KEY": "k"}


def test_the_host_sessions_routing_does_not_reach_the_worker():
    env = cs._without_host_routing(dict(HOST))
    for gone in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "CLAUDECODE", "CLAUDE_CODE_SESSION_ID",
                 "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_AGENT_SDK_VERSION"):
        assert gone not in env, gone


def test_everything_else_travels():
    env = cs._without_host_routing(dict(HOST))
    assert env["PATH"] == "/usr/bin" and env["HOME"] == "/h" and env["DEEPSEEK_API_KEY"] == "k"


def test_the_spawn_uses_the_scrubbed_environment(monkeypatch):
    """At the spawn door: an engine started from inside a Claude Code session still gives the worker the CHAIN's
    endpoint, never the host shell's — the helper only counts if the spawn scrubs before it reads what is pinned."""
    from tests.agent_headless.unit.workers.claude_spawn import spawn_of
    out = spawn_of(monkeypatch, host_env={k: v for k, v in HOST.items() if k not in ("PATH", "HOME")},
                   chain_env={"ANTHROPIC_BASE_URL": "https://chain.example.test", "ANTHROPIC_AUTH_TOKEN": "tier"},
                   tier={"name": "rung-1", "base_url": "https://chain.example.test"})
    env = out["env"]
    assert env["ANTHROPIC_BASE_URL"] == "https://chain.example.test", env.get("ANTHROPIC_BASE_URL")
    assert env["ANTHROPIC_AUTH_TOKEN"] == "tier"
    assert not {"CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_AGENT_SDK_VERSION"} & set(env)
