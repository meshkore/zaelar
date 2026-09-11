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


# Directories a library must never be planted in. Refusing by NAME is not a boundary (the daemon's own
# security doc says so: "home is the machine minus a list"), which is why the checks that actually carry
# weight are separate and absolute — the chosen path may not BE the filesystem root, may not BE the
# operator's home, and must be WRITABLE by this process. This list is the third, cheaper layer: places where
# a folder full of downloads is obviously a mistake.
#
# ⚠️ `/var` is deliberately NOT here, and the first version of this list had it. On macOS `/var` resolves to
# `/private/var`, and the per-user temp directory (`$TMPDIR`) lives underneath it — so banning the prefix
# refused a perfectly ordinary writable folder belonging to the person choosing (measured: every `tmp_path`
# in the test suite). On Linux `/var` is root-owned, so the writability check already refuses it for a normal
# process, which is the check that was doing the work anyway. A prefix list that over-refuses is not "extra
# safety": it is a rule nobody can predict, and the rule it replaces is stronger.
_FORBIDDEN_PREFIXES = ("/etc", "/usr", "/bin", "/sbin", "/dev", "/proc", "/sys", "/boot",
                       "/System", "/Library", "/private/etc",
                       "C:\\Windows", "C:\\Program Files")


def check_base(raw: str) -> dict:
    """Validate a folder the OPERATOR chose as the place to keep Zaelar's files (V2-672).

    `resolve()` exists because paths arrive here from magnet payloads, model output and query strings. This
    one answers a different question with a different provenance: a directory the person running the engine
    picked, once, for their own machine. So it accepts an ABSOLUTE path — which `resolve()` never may — and
    pays for that with a validator that refuses instead of repairing:

      · it must be absolute, exist, be a directory and be WRITABLE — "I'll create it for you" turns a typo
        into a folder tree in a place nobody meant;
      · never the filesystem root and never HOME itself: both are "the whole machine", and a library that
        broad makes the boundary `resolve()` enforces meaningless;
      · never inside a system directory;
      · the check is made on the RESOLVED path, so a symlink cannot smuggle one of those past it.

    Returns `{"ok": bool, "path": str, "reason": str}`. The reason is named, because a refusal the person
    cannot act on reads as a broken product (V2-559).
    """
    txt = str(raw or "").strip()
    if not txt:
        return {"ok": False, "path": "", "reason": "empty"}
    try:
        p = Path(os.path.expanduser(txt))
        if not p.is_absolute():
            return {"ok": False, "path": txt, "reason": "not_absolute"}
        real = p.resolve()
    except Exception:  # noqa: BLE001
        return {"ok": False, "path": txt, "reason": "unreadable"}
    if not real.exists():
        return {"ok": False, "path": str(real), "reason": "missing"}
    if not real.is_dir():
        return {"ok": False, "path": str(real), "reason": "not_a_directory"}
    if real.parent == real:
        return {"ok": False, "path": str(real), "reason": "filesystem_root"}
    try:
        if real == Path.home().resolve():
            return {"ok": False, "path": str(real), "reason": "home_itself"}
    except Exception:  # noqa: BLE001
        pass
    low = str(real)
    if any(low == pre or low.startswith(pre + os.sep) for pre in _FORBIDDEN_PREFIXES):
        return {"ok": False, "path": str(real), "reason": "system_directory"}
    if not os.access(real, os.W_OK):
        return {"ok": False, "path": str(real), "reason": "not_writable"}
    return {"ok": True, "path": str(real), "reason": ""}


def base() -> Path:
    """WHERE the library tree lives. The workspace root unless the operator chose somewhere else.

    Re-validated on every read rather than trusted from the store: the chosen folder can be an unplugged
    external disk or a deleted directory by the time the engine next boots, and silently writing to a stale
    absolute path is worse than falling back to the place that always exists.
    """
    from nucleo import workspace as _ws
    chosen = str(_overrides().get("base") or "").strip()
    if chosen:
        got = check_base(chosen)
        if got["ok"]:
            return Path(got["path"])
    return _ws.root()


def root() -> Path:
    """The library root: a folder NAME (never a path — see `_safe_segment`) under `base()`.

    The NAME stays a single segment even when the base is the operator's own folder, and that is deliberate:
    the five kind-folders land inside `<chosen>/Zaelar/`, not scattered across the folder he picked.
    """
    name = _safe_segment(_overrides().get("root") or _genesis().get("root") or "library", "library")
    return base() / name


def folders() -> dict:
    """kind → folder name, genesis defaults with the operator's renames layered on top."""
    # `names`, not `base`: since V2-672 `base()` is a module-level function and a local of the same name
    # here would shadow it — harmless today, a NameError the day this function needs the real one.
    names = dict(_genesis().get("folders") or {})
    over = _overrides().get("folders")
    if isinstance(over, dict):
        names.update({k: v for k, v in over.items() if k in KINDS})
    return {k: _safe_segment(names.get(k) or k, k) for k in KINDS}


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
    if "base" in patch:
        # The one field that is a PATH and not a name: it goes through the validator, never straight to
        # disk. An empty value is the way back to the default, so it is accepted as a clear.
        raw = str(patch.get("base") or "").strip()
        if not raw:
            cur.pop("base", None)
        else:
            got = check_base(raw)
            if not got["ok"]:
                return {"ok": False, "error": f"base: {got['reason']}", "reason": got["reason"]}
            cur["base"] = got["path"]
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cur, ensure_ascii=False, indent=2))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:160]}
    _ov_cache.update(path=None, mtime=None, data={})    # force a re-read on the next call
    return {"ok": True, "rules": rules()}


def rules() -> dict:
    """Everything the operator (or the brain) needs to know about how files are organized."""
    return {"root": str(root()), "base": str(base()), "folders": folders(), "guide": guide(),
            "browser_playable_only": browser_playable_only()}
