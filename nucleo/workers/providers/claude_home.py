"""The config home a headless Claude Code process runs with: the engine's, never the host user's.

Without this, every Claude Code the engine spawns (a Brain Worker, the widget generator, the atomic code agent)
reads the host user's own configuration: their user-level `CLAUDE.md`, their auto-memory, their settings, hooks
and MCP servers. All of it rides in the worker's first request, to whatever provider the chain picked (V2-851
§15e measured 1.8k chars of it in every worker prompt).

The mechanism, measured against the installed CLI (2.1.318) with a capture endpoint:
  · `--setting-sources project,local` drops the user source — user settings AND the user-level `CLAUDE.md`;
  · `--strict-mcp-config` with no `--mcp-config` → no MCP server from anywhere;
  · `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` → no per-project auto-memory;
  · a routed tier (an explicit `ANTHROPIC_BASE_URL`, its credential in the env) also gets `CLAUDE_CONFIG_DIR` = the
    engine's own worker home, so nothing under the user's config dir is even opened. Stable across tasks on purpose:
    a native session is resumed by id (V2-851 §15e) and the CLI looks it up in its config dir.
The local licence tier (no base URL) keeps the default config dir: its login lives there and is the only thing it
takes from it — the flags above still keep everything else out.
"""
from __future__ import annotations

import os
import tempfile

SETTING_SOURCES = "project,local"
#: The env keys the engine itself sets here — a guard against the HOST's `CLAUDE_CODE_*` must not count these.
ENGINE_KEYS = ("CLAUDE_CODE_DISABLE_AUTO_MEMORY", "CLAUDE_CONFIG_DIR")


def home() -> str:
    """The engine's worker config home (created 0700). `ZAELAR_WORKER_CONFIG_DIR` overrides it."""
    path = (os.environ.get("ZAELAR_WORKER_CONFIG_DIR") or "").strip() or os.path.join(
        tempfile.gettempdir(), "zaelar-worker-home")
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
    except OSError:
        pass
    return path


def isolate(cmd: list, env: dict) -> list:
    """Mutate a Claude Code argv and env so the process loads none of the host user's configuration; returns argv."""
    if "--setting-sources" not in cmd:
        cmd += ["--setting-sources", SETTING_SOURCES]
    if "--strict-mcp-config" not in cmd:
        cmd.append("--strict-mcp-config")
    env[ENGINE_KEYS[0]] = "1"
    if (env.get("ANTHROPIC_BASE_URL") or "").strip():
        env[ENGINE_KEYS[1]] = home()
    return cmd
