# The dev worker's jail fails CLOSED, and its environment is an allowlist (V2-601 T-09, audit 2026-09-05).
#
# Two audited faults, both about the same worker — the only one a cluster PEER can drive:
#   · a settings-file write failure used to WARN and start the worker WITHOUT its PreToolUse jail. It starts
#     with ZERO tools now — confined to nothing instead of to everything — so every lifecycle seam stays intact
#     while the peer gets a worker that cannot touch the filesystem.
#   · `env = dict(os.environ)` handed the dev worker the operator's FULL environment: every API key `.env`
#     loads (DeepSeek, ElevenLabs, the cluster token…). Allowlist now: what is not named does not travel.
#
# Run: .venv/bin/pytest tests/agent_headless/unit/workers/test_dev_worker_jail_fails_closed.py -q
import re
from pathlib import Path

from nucleo.workers.claude_session import _DEV_ENV_KEEP, _dev_env_allowlist

ENGINE = Path(__file__).resolve().parents[4]


def _stripped(path: str) -> str:
    """Source with comments removed — a guard that can match its own explanation guards nothing (V2-573)."""
    src = (ENGINE / path).read_text(encoding="utf-8")
    return re.sub(r"(?m)#.*$", "", src)


def test_no_secret_survives_the_allowlist():
    env = {
        "DEEPSEEK_API_KEY": "sk-1", "ELEVENLABS_API_KEY": "el-1", "AIMLAPI_KEY": "ai-1",
        "MESHKORE_UC_TOKEN": "tok", "OPENAI_API_KEY": "sk-2", "GEMINI_API_KEY": "g-1",
        "PATH": "/bin", "HOME": "/Users/op", "PYTHONPATH": "/engine",
        "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic", "ANTHROPIC_AUTH_TOKEN": "tier-cred",
        "ZAELAR_TASK_ID": "7", "ZAELAR_TASK_TOKEN": "t", "ZAELAR_DEV_WORKER_ROOT": "/tmp/wd",
    }
    out = _dev_env_allowlist(env)
    for leaked in ("DEEPSEEK_API_KEY", "ELEVENLABS_API_KEY", "AIMLAPI_KEY", "MESHKORE_UC_TOKEN",
                   "OPENAI_API_KEY", "GEMINI_API_KEY"):
        assert leaked not in out, leaked
    # …and what the worker legitimately needs still travels: the CLI basics, its ONE tier credential, ZAELAR_*.
    for kept in ("PATH", "HOME", "PYTHONPATH", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN",
                 "ZAELAR_TASK_ID", "ZAELAR_TASK_TOKEN", "ZAELAR_DEV_WORKER_ROOT"):
        assert out.get(kept) == env[kept], kept


def test_the_allowlist_names_no_wildcard_secret_holder():
    """The list itself may never grow a catch-all: every entry is a specific name or the ZAELAR_ prefix."""
    for k in _DEV_ENV_KEEP:
        assert "*" not in k and "KEY" not in k.upper().replace("ANTHROPIC_AUTH_TOKEN", ""), k


def test_the_spawn_actually_filters_for_dev(monkeypatch):
    """Wiring, not just the pure function (V2-199): the filter must sit in the spawn path, keyed on the DEV
    kind — comment-stripped source, anchored on the call itself."""
    src = _stripped("nucleo/workers/claude_session.py")
    i = src.index('if spec.kind == "dev":\n            env = _dev_env_allowlist(env)')
    # …and it runs AFTER the tier credential landed in env, or the worker would start with no endpoint at all.
    assert "env_for_worker" in src[:i], "the filter must run after the tier credential is resolved"


def test_a_failed_jail_write_starts_the_worker_with_zero_tools():
    """dispatch.py's dev branch: on a settings-write failure the spec is built with tools=[] and
    deny_tools=True — never the old warn-and-run-unjailed. Comment-stripped source, anchored on the
    conditional that builds the spec."""
    src = _stripped("nucleo/dispatch.py")
    i = src.index("_dev_jail_ok = False")
    spec_zone = src[i:i + 900]
    assert '(_dev["tools"] if _dev_jail_ok else [])' in spec_zone
    assert "deny_tools=(not _dev_jail_ok)" in spec_zone
