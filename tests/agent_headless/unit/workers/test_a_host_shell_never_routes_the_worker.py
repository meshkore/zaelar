"""A worker's endpoint comes from its spec or the provider chain, never from the engine's inherited shell.

Measured 2026-09-28 (demo pass, A1): the engine was restarted from inside a Claude Code session, whose shell
exports `ANTHROPIC_BASE_URL=https://api.anthropic.com`. The spawn read that as «the caller pinned an endpoint»,
skipped the chain, asked Anthropic for `glm-5.3`, and every errand died in two seconds with «There's an issue
with the selected model» — the operator's monitor search, three relays, zero work.
"""
from nucleo.workers import claude_session as cs

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


def test_the_spawn_uses_the_scrubbed_environment():
    """The helper is only worth something if the spawn calls it before deciding whether an endpoint is pinned."""
    import inspect
    src = inspect.getsource(cs)
    at = src.index('env = _without_host_routing(dict(os.environ))')
    assert at < src.index('if "ANTHROPIC_BASE_URL" not in env:'), "scrub first, then read what is pinned"
