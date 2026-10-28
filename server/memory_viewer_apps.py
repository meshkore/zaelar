"""The «apps» card of the memory viewer: each widget's own data dir, walked in the background (a browser profile is
100k+ files) — from `server/memory_viewer_api.py`, refactor2710-13 T-03, which imports it back."""
import json
import os
import threading
import time

#: A browser widget's PROFILE is its browsing session (cookies, sign-ins, cache), not data it keeps for him.
_NOT_APP_DATA = ("profile",)
_DIRS_TTL_S = 600.0

_lock = threading.Lock()
_dirs: dict = {"at": 0.0, "rows": None, "running": False}


def _note(what: str, e: Exception) -> None:
    from voice.observer import emit
    emit("memory", f"viewer: {what} failed", text=str(e)[:160], extra={"module": "server.memory_viewer_api"})


def _widgets_root() -> str:
    from widgets import store
    return store.DATA_DIR


def _walk(path: str) -> tuple[int, int, int]:
    files = size = newest = 0
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            it = list(os.scandir(d))
        except OSError as e:
            _note("walking a data dir", e)
            continue
        for e in it:
            if e.is_dir(follow_symlinks=False):
                if not e.name.startswith(_NOT_APP_DATA):
                    stack.append(e.path)
            elif e.is_file(follow_symlinks=False):
                st = e.stat(follow_symlinks=False)
                files += 1; size += st.st_size; newest = max(newest, int(st.st_mtime))
    return files, size, newest


def _measure_dirs() -> None:
    try:
        root = _widgets_root()
        groups: dict[str, dict] = {}
        for e in (os.scandir(root) if os.path.isdir(root) else []):
            if not e.is_dir(follow_symlinks=False) or e.name.startswith((".", "_")) or e.name == "mensajeria":
                continue
            base = "results" if e.name.startswith("results") else e.name.split("--")[0]
            f, b, m = _walk(e.path)
            g = groups.setdefault(base, {"key": base, "files": 0, "bytes": 0, "mtime": 0, "sheets": 0})
            g["files"] += f; g["bytes"] += b; g["mtime"] = max(g["mtime"], m); g["sheets"] += 1
        for g in groups.values():
            g["title"] = _widget_title(g["key"])
            if g["key"] != "results":
                g.pop("sheets")
        rows = sorted(groups.values(), key=lambda g: -g["bytes"])
        with _lock:
            _dirs.update(at=time.monotonic(), rows=rows)
    except Exception as e:  # noqa: BLE001
        _note("measuring the app folders", e)
    finally:
        with _lock:
            _dirs["running"] = False


def _widget_title(wid: str) -> str:
    """The manifest's title — the client prefers its own translated name and falls back to this."""
    import widgets
    p = os.path.join(os.path.dirname(widgets.__file__), wid, "manifest.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            return str(json.load(fh).get("title") or "")
    return ""


def _dir_rows() -> list[dict] | None:
    """The measured app folders, or None while the first walk is still running (it starts here)."""
    with _lock:
        fresh = _dirs["rows"] is not None and time.monotonic() - _dirs["at"] < _DIRS_TTL_S
        if not fresh and not _dirs["running"]:
            _dirs["running"] = True
            threading.Thread(target=_measure_dirs, name="memory-viewer-dirs", daemon=True).start()
        return _dirs["rows"]
