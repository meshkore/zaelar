"""The agent's OWN filesystem: one root, a folder per kind, and a boundary nothing crosses (V2-638).

The operator's directive: Zaelar keeps its own files — a paper the `documento` widget fetched, a track the
music widget downloaded, a film the video widget is streaming — in ONE place with a sensible structure, so
every widget reads the same paths instead of each inventing a private corner. Cloud Machines get the same
tree on their Volume; a self-host install gets it in the repo root. The layout ships in `nucleo/genesis.json`
and the operator overrides any of it (rename a folder, move the root) — the override lands in
`<workspace>/config/library.json`, mtime-cached, exactly like the style policy of V2-633.

**The boundary is the security seam, not a convenience.** Paths reaching this module come from magnet
payloads, model output and HTTP query strings — all untrusted. `resolve()` is the ONLY way to turn a relative
name into a real path, and it answers `None` for anything that leaves the root: absolute paths, `..`, and —
the one that a naive prefix check misses — a symlink INSIDE the library pointing outside it, which is why the
check is made against the REAL path after resolution, not against the string.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_GENESIS_PATH = Path(__file__).resolve().parent.parent / "nucleo" / "genesis.json"

KINDS = ("video", "audio", "documents", "images", "downloads")

_genesis_cache: dict | None = None
_ov_cache: dict = {"path": None, "mtime": None, "data": {}}


def _genesis() -> dict:
    global _genesis_cache
    if _genesis_cache is None:
        try:
            _genesis_cache = dict(json.loads(_GENESIS_PATH.read_text()).get("library") or {})
        except Exception:  # noqa: BLE001 — a broken genesis must not stop the engine booting
            _genesis_cache = {}
    return dict(_genesis_cache)


def _overrides_path() -> Path:
    from nucleo import workspace as _ws
    return _ws.root() / "config" / "library.json"


def _overrides() -> dict:
    """Per-install overrides, mtime-cached (one os.stat per call, a parse only when the file changed)."""
    p = _overrides_path()
    try:
        mtime = p.stat().st_mtime_ns
    except OSError:
        if _ov_cache["path"] == str(p):
            _ov_cache.update(mtime=None, data={})
        return {}
    if _ov_cache["path"] == str(p) and _ov_cache["mtime"] == mtime:
        return _ov_cache["data"]
    try:
        data = json.loads(p.read_text())
        data = data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        data = {}
    _ov_cache.update(path=str(p), mtime=mtime, data=data)
    return data


def _safe_segment(name: str, fallback: str) -> str:
    """A folder NAME the operator chose. One segment, no separators, no dots — a rename must not be able to
    relocate the whole library by containing a slash or a `..`."""
    cleaned = "".join(c for c in str(name or "") if c.isalnum() or c in " -_").strip()
    return cleaned or fallback


def root() -> Path:
    """The library root. Under the workspace root, so a cloud Machine's Volume carries it unchanged."""
    from nucleo import workspace as _ws
    name = _safe_segment(_overrides().get("root") or _genesis().get("root") or "library", "library")
    return _ws.root() / name


def folders() -> dict:
    """kind → folder name, genesis defaults with the operator's renames layered on top."""
    base = dict(_genesis().get("folders") or {})
    over = _overrides().get("folders")
    if isinstance(over, dict):
        base.update({k: v for k, v in over.items() if k in KINDS})
    return {k: _safe_segment(base.get(k) or k, k) for k in KINDS}


def dir_for(kind: str) -> Path:
    """The directory for a kind, created on demand. An unknown kind lands in `documents` rather than at the
    root — an unfiled file in the root is how a tidy tree stops being tidy."""
    k = kind if kind in KINDS else "documents"
    d = root() / folders()[k]
    d.mkdir(parents=True, exist_ok=True)
    return d


def downloads_dir() -> Path:
    """The torrent client's SANDBOX. It writes here and nowhere else (operator's rule) — a finished file is
    filed into its kind folder afterwards, by us, never by the client."""
    return dir_for("downloads")


def dir_for_file(name: str) -> Path:
    """Where a file of this name belongs, by what it IS."""
    from . import formats
    kind = formats.kind_of(name)
    return dir_for({"video": "video", "audio": "audio", "image": "images"}.get(kind, "documents"))


def ensure() -> Path:
    """Create the whole tree. Idempotent, never raises (a read-only disk must not stop the agent booting)."""
    for k in KINDS:
        try:
            dir_for(k)
        except Exception:  # noqa: BLE001
            pass
    return root()


def resolve(rel: str) -> Path | None:
    """Turn an untrusted relative path into a real path INSIDE the library, or `None`.

    The only door. Rejects absolutes and `..`, and re-checks the RESOLVED path against the resolved root, so
    a symlink planted inside the library cannot be used to read the rest of the disk."""
    raw = str(rel or "").strip()
    s = raw.replace("\\", "/")
    # An absolute path is REFUSED, never silently reinterpreted as a relative one. Stripping the leading slash
    # would map "/etc/passwd" to "<library>/etc/passwd" — safe, because it stays inside the root, but it
    # answers a question nobody asked and hides the caller's real (wrong) intent behind a plausible path.
    if not s or s.startswith("/") or s.startswith("~") or os.path.isabs(raw) or ":" in s.split("/")[0]:
        return None
    base = root()
    try:
        base_real = base.resolve()
        target = (base / s).resolve()
    except Exception:  # noqa: BLE001
        return None
    try:
        target.relative_to(base_real)
    except ValueError:
        return None                      # escaped the root — symlinks included, because both are resolved
    return target


def rel_of(path) -> str:
    """The library-relative form of a path, or "" if it is not inside the library."""
    try:
        return str(Path(path).resolve().relative_to(root().resolve())).replace("\\", "/")
    except Exception:  # noqa: BLE001
        return ""


def guide() -> str:
    """The one-line structure guide — genesis, or the operator's own wording if he changed it."""
    return str(_overrides().get("guide") or _genesis().get("guide") or "").strip()


def browser_playable_only() -> bool:
    """The default download policy: only bring home what the page can play. Operator-overridable."""
    v = _overrides().get("browser_playable_only")
    if isinstance(v, bool):
        return v
    v = _genesis().get("browser_playable_only")
    return True if not isinstance(v, bool) else v


def set_overrides(patch: dict) -> dict:
    """Persist an operator override (a renamed folder, a moved root, the policy). Merges, never replaces —
    changing one folder's name must not silently reset the other four to genesis."""
    p = _overrides_path()
    cur = dict(_overrides())
    patch = patch if isinstance(patch, dict) else {}
    if isinstance(patch.get("folders"), dict):
        merged = dict(cur.get("folders") or {})
        merged.update({k: v for k, v in patch["folders"].items() if k in KINDS})
        cur["folders"] = merged
    for k in ("root", "guide", "browser_playable_only"):
        if k in patch:
            cur[k] = patch[k]
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cur, ensure_ascii=False, indent=2))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:160]}
    _ov_cache.update(path=None, mtime=None, data={})    # force a re-read on the next call
    return {"ok": True, "rules": rules()}


def rules() -> dict:
    """Everything the operator (or the brain) needs to know about how files are organized."""
    return {"root": str(root()), "folders": folders(), "guide": guide(),
            "browser_playable_only": browser_playable_only()}
