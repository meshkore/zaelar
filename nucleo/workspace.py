#
# WORKSPACE ROOT (Fase 3 M0) — one mountable root for every per-tenant persistent path.
#
# The engine is coded as a single-tenant process (one operator, one machine) and stays that way —
# it must NEVER become multi-tenant-aware. What changes for the real cloud (1 Fly Machine + 1 Fly
# Volume per paying user, see the Fase 3 plan) is WHERE its own data lands: today every module
# resolves its own path relative to `Path(__file__)` (repo root), which only works because there's
# exactly one tenant on one disk. This module gives every one of those call sites a single override
# knob instead of each inventing its own — set `ZAELAR_WORKSPACE=/data` (a mounted Fly Volume) and
# memory/widgets/config/credentials all land under that root; leave it unset and behavior is BYTE
# IDENTICAL to before this module existed (falls back to the repo root, today's default).
#
# Same shape as the existing `TG_SESSION_DIR`/`WA_SESSION_DIR` overrides in
# connectors/telegram/config.py and connectors/whatsapp/config.py — this generalizes that pattern
# to the whole engine instead of two one-off connectors.
#
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def root() -> Path:
    """The per-tenant data root. `ZAELAR_WORKSPACE` unset (self-host, the operator's own machine,
    every self-host install) → the repo root, today's exact behavior. Set (real cloud Machine,
    pointed at its own mounted Volume) → every persistent path below moves under it, with zero
    other code change needed at any call site beyond reading this instead of `Path(__file__)`."""
    env = (os.getenv("ZAELAR_WORKSPACE") or "").strip()
    return Path(env) if env else _REPO_ROOT
