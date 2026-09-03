#
# WORKSPACE ROOT (Phase 3 M0) — one mountable root for every per-tenant persistent path.
#
# The engine is coded as a single-tenant process (one operator, one machine) and stays that way —
# it must NEVER become multi-tenant-aware. What changes for the real cloud (1 Fly Machine + 1 Fly
# Volume per paying user, see the Phase 3 plan) is WHERE its own data lands: today every module
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


# THE PER-TENANT TREE (V2-562). `root()` alone is not enough: it answers "where", never "does it exist".
# On self-host the answer was free — the repo root ships `config/`, `i18n/`, `memory/` and `widgets/` in git, so
# every writer found its parent already there and no call site ever needed a `mkdir`. A cloud Machine mounts an
# EMPTY Volume, and there the same code writes into directories that were never created: measured on a real
# account 2026-09-03, `/data` held only `memory/` and `widgets/` (made by the two writers that happen to mkdir),
# while `config/`, `credentials/` and `i18n/` were simply absent.
#
# The failure mode is what makes this worth a module-level guarantee instead of seven local fixes: writing into a
# missing directory raises `FileNotFoundError` INSIDE code that treats persistence as best-effort, so it is caught,
# logged at WARNING and stepped over. Nothing breaks loudly. What the operator sees is a preference that will not
# stick — on that Machine the language onboarding ran again on EVERY cold boot, because `settings.json` could
# never be written, and the log line for it was one WARNING among two hundred INFO lines.
#
# `SUBDIRS` is the SINGLE declaration of that tree. `tests/agent_headless/unit/test_workspace_tree.py` reads the
# real call sites out of the source and fails if any module resolves a workspace path whose root is not listed
# here — so adding a new persistent path cannot silently reintroduce the same hole.
SUBDIRS = (
    "config",            # settings.json · v2.json · connectors.json · identity.json · meshkore.json
    "credentials",       # zaelar.env · meshkore_ed25519.pem
    "memory/_data",      # zaelar.db (memory + the durable event log)
    "widgets/_data",     # generated widgets, their state, _jobs.json, _system/hidden.json
    "i18n/generated",    # generated fillers + aliases
)


def ensure() -> Path:
    """Create the per-tenant tree if it is not there yet, and return the root. Idempotent and NEVER raises.

    Called once at boot (`server/__main__.py`) BEFORE anything reads or writes a persistent path. It is not a
    substitute for a writer creating its own parent — a directory can be removed while the process lives, and
    each writer still guards itself — it is the guarantee that a Machine's FIRST boot on an empty Volume starts
    with somewhere to put its data.

    Never raises on purpose: a read-only or exotic filesystem must not stop the agent from booting. A directory
    that could not be created shows up later as the same best-effort write failure it is today, not as a crash
    on a path nobody has exercised yet."""
    base = root()
    for rel in SUBDIRS:
        try:
            (base / rel).mkdir(parents=True, exist_ok=True)
        except Exception:      # noqa: BLE001 — see the docstring: booting beats persisting
            pass
    return base
