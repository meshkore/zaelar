"""A worker's Claude Code runs with the engine's config home, never the host user's (V2-851 F3, §15e).

Measured 2026-11-05: the host user's own user-level `CLAUDE.md` rode in every worker's first request, to every
provider of the chain. The guard is at the spawn door: the argv and env the worker would really get. Proved against
the installed CLI with a capture endpoint — `--setting-sources project,local` (or an isolated `CLAUDE_CONFIG_DIR`)
removes the block from the first request.
"""
import os

from nucleo.workers.base import WorkerSpec
from tests.agent_headless.unit.workers.claude_spawn import flag, spawn_of

_ROUTED = {"ANTHROPIC_BASE_URL": "https://chain.example.test", "ANTHROPIC_AUTH_TOKEN": "tier"}
_TIER = {"name": "rung-1", "base_url": "https://chain.example.test"}


def _user_config_dir() -> str:
    return os.path.realpath(os.path.expanduser("~/.claude"))


def _no_user_source(argv: list) -> None:
    sources = flag(argv, "--setting-sources")
    assert sources and "user" not in sources.split(","), sources
    assert "--strict-mcp-config" in argv
    assert not any(_user_config_dir() in os.path.realpath(str(a)) for a in argv if str(a).startswith("/")), argv


def test_a_routed_worker_gets_the_engines_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_WORKER_CONFIG_DIR", str(tmp_path / "home"))
    out = spawn_of(monkeypatch, chain_env=_ROUTED, tier=_TIER)
    env = out["env"]
    home = os.path.realpath(env.get("CLAUDE_CONFIG_DIR", ""))
    assert home == os.path.realpath(str(tmp_path / "home")), env.get("CLAUDE_CONFIG_DIR")
    assert not home.startswith(_user_config_dir())
    assert env.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY") == "1"
    _no_user_source(out["argv"])


def test_the_licence_worker_keeps_its_login_but_not_the_users_config(monkeypatch):
    out = spawn_of(monkeypatch, chain_env={}, tier=None)
    assert "CLAUDE_CONFIG_DIR" not in out["env"] or not out["env"]["CLAUDE_CONFIG_DIR"].startswith(
        _user_config_dir())
    assert out["env"].get("CLAUDE_CODE_DISABLE_AUTO_MEMORY") == "1"
    _no_user_source(out["argv"])


def test_a_dev_worker_keeps_the_isolation_after_its_env_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_WORKER_CONFIG_DIR", str(tmp_path / "home"))
    out = spawn_of(monkeypatch, spec=WorkerSpec(task_id="t-dev", kind="dev"), chain_env=_ROUTED, tier=_TIER)
    assert out["env"].get("CLAUDE_CONFIG_DIR") and out["env"].get("CLAUDE_CODE_DISABLE_AUTO_MEMORY") == "1"
    _no_user_source(out["argv"])
