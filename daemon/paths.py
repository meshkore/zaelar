"""Where the daemon keeps its own state — resolved WITHOUT importing the engine.

The daemon has to work in two worlds that do not overlap:

  IN-REPO (`python -m daemon` next to the engine, self-host and development). It must land where the engine
  expects, which means honouring `ZAELAR_WORKSPACE` exactly like `nucleo/workspace.py` does — unset → the repo
  root, set → a mounted Volume. Copying those four lines instead of importing them is deliberate: importing
  `nucleo.workspace` would drag the engine's `sys.path` and its 1.7 GB venv into a binary that must ship alone.

  INSTALLED (a onefile build on a machine with no repo). There is no repo root to fall back to, so state goes to
  the platform's user-data directory.

Everything the daemon owns lives under ONE directory (`state_dir()`): its config, its audit log, and later the
browser profile. In-repo that directory is `config/daemon/` — a subdirectory of `config/`, which is already
declared in `workspace.SUBDIRS`, so `tests/agent_headless/unit/test_workspace_tree.py` stays satisfied and a
fresh cloud Volume gets the parent created for it at boot like everything else.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# `daemon/paths.py` → `daemon/` → the engine repo root. Only meaningful when running from a source tree.
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _frozen() -> bool:
    """True when running from a PyInstaller onefile bundle (P4). `sys.frozen` is the attribute PyInstaller sets;
    checking it here rather than at the call sites keeps the packaging knowledge in one place."""
    return bool(getattr(sys, "frozen", False))


def _install_root() -> Path | None:
    """`<prefix>` when this process is an INSTALLED daemon, recognised by living in `<prefix>/bin/`.

    This is what makes "install it somewhere else" work with no environment variable, no plist entry and no
    scheduled-task wrapper: the state sits beside the program, so moving the folder moves everything. At the
    default location it resolves to exactly where the state has always been, so nothing moves for anybody who
    did not ask.

    The `bin` check is the whole guard. Without it, a binary somebody ran straight out of `~/Downloads` would
    claim `~` as its root — and, worse, an in-repo `python -m daemon` would resolve `sys.executable` to
    `.venv/bin/python` and take the VIRTUALENV for its prefix."""
    if _frozen():
        program = Path(sys.executable).resolve()
    elif _REPO_ROOT.is_file():
        # A zipapp: `__file__` lives inside the archive, so `_REPO_ROOT` IS the archive rather than a directory.
        program = _REPO_ROOT
    else:
        return None
    parent = program.parent
    return parent.parent if parent.name == "bin" else None


def workspace_root() -> Path:
    """The per-tenant data root, with the SAME semantics as `nucleo.workspace.root()`.

    Kept byte-compatible with the engine's rule on purpose: a self-host user who sets `ZAELAR_WORKSPACE` for the
    engine and not for the daemon would otherwise end up with two different config trees and no way to tell.

    ⚠️ `_frozen()` USED TO BE THE ONLY TEST FOR "installed", and a zipapp is not frozen. Measured 2026-09-15:
    an installed `.pyz` resolved its state to `…/zaelar-daemon.pyz/config/daemon` — a path INSIDE the archive
    file, so the directory could never be created. Every write failed, silently and by design (this module
    never raises), which meant a fresh random token on every start and a folder allowlist that did not survive
    a restart. The daemon answered `/health` and looked perfectly healthy while forgetting everything. The
    archive is the fallback that exists so there is always a way to ship, so the failure hid where nobody was
    looking."""
    env = (os.getenv("ZAELAR_WORKSPACE") or "").strip()
    if env:
        return Path(env)
    install = _install_root()
    if install is not None:
        return install
    # Installed somewhere unusual, or run straight from a download: the platform's user-data directory. Only an
    # actual source tree — a real directory with the package in it — keeps the repo-root behaviour.
    if _frozen() or _REPO_ROOT.is_file() or not (_REPO_ROOT / "daemon" / "__init__.py").is_file():
        return Path(_user_data_dir())
    return _REPO_ROOT


def _user_data_dir() -> Path:
    """Per-OS user-data directory, for the installed daemon that has no repo to live in."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Zaelar"
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        return (Path(base) if base else home / "AppData" / "Local") / "Zaelar"
    return Path(os.getenv("XDG_DATA_HOME") or (home / ".local" / "share")) / "zaelar"


def state_dir() -> Path:
    """The single directory the daemon owns. Created on demand; never raises here, because a daemon that cannot
    persist should still be able to answer `/health` and tell the user why.

    0700 because of what is in it: the API token, and a log of every path the agent opened. The files inside are
    0600 on their own, but a directory anyone can LIST still tells them the daemon is here, when it last ran and
    how big its log has grown — and it is one careless `open(..., "w")` away from telling them more."""
    d = workspace_root() / "config" / "daemon"
    try:
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)      # no-op on Windows, where the ACL inherited from LOCALAPPDATA is per-user
    except Exception:       # noqa: BLE001 — reported through /health, not by refusing to boot
        pass
    return d


def config_file() -> Path:
    """`daemon.json`: the port, the folder allowlist, and the API token."""
    return state_dir() / "daemon.json"


def audit_file() -> Path:
    """Append-only JSONL of every file operation the daemon performed, so "what did the agent read?" has an
    answer that does not depend on remembering. One line per operation, allowed or refused."""
    return state_dir() / "audit.jsonl"


def default_documents() -> Path | None:
    """The one folder the daemon may read before the user has chosen anything (decision: Documents only).

    Returns None when there is no such folder — a Linux box with a non-English or absent XDG setup is a real
    case, and inventing `~/Documents` there would create an empty directory the user never asked for."""
    home = Path.home()
    candidates = [home / "Documents"]
    # XDG systems can put it anywhere and localize the name; `user-dirs.dirs` is the file that knows.
    xdg = Path(os.getenv("XDG_CONFIG_HOME") or (home / ".config")) / "user-dirs.dirs"
    try:
        for line in xdg.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("XDG_DOCUMENTS_DIR="):
                raw = line.split("=", 1)[1].strip().strip('"')
                candidates.insert(0, Path(raw.replace("$HOME", str(home))))
    except Exception:       # noqa: BLE001 — the file is optional on every platform
        pass
    for c in candidates:
        try:
            if c.is_dir():
                return c.resolve()
        except Exception:   # noqa: BLE001
            continue
    return None
