#
# hidden.py — "deleted" SHIPPED widgets (V2-515). Engine source is never removed from disk: deleting a
# widget whose folder is repo source (or whose fork shadowed one) HIDES the id instead. One small json
# under the widget data dir; the catalog filters hidden ids, so the brain, identify() and the registry
# stop knowing the widget exactly as if the folder were gone — but the files stay, the next engine
# update still reaches them, and `lifecycle.restore_widget` can bring the widget back. Per-tenant state:
# lives under the workspace, like every other piece of widget DATA.
#
import json
import os
import threading

from nucleo import workspace as _workspace

_lock = threading.Lock()
_cache = {"path": "", "mtime": None, "ids": frozenset()}


def _path() -> str:
    # Resolved per call, not at import — the workspace is an env knob (same rule as widgets/paths.py).
    return os.path.join(str(_workspace.root()), "widgets", "_data", "_system", "hidden.json")


def ids() -> frozenset:
    """The hidden widget ids. Cached by file mtime: this runs inside the catalog signature, i.e. on every
    identify() call, so it must cost a stat — not a read — in the steady state."""
    p = _path()
    try:
        m = os.path.getmtime(p)
    except OSError:
        m = None
    if p == _cache["path"] and m == _cache["mtime"]:
        return _cache["ids"]
    out = frozenset()
    if m is not None:
        try:
            raw = json.load(open(p, encoding="utf-8"))
            out = frozenset(str(x).strip().lower() for x in raw if str(x).strip())
        except Exception:
            out = frozenset()
    _cache.update(path=p, mtime=m, ids=out)
    return out


def _write(cur: set) -> None:
    p = _path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(cur), f, ensure_ascii=False, indent=0)
    os.replace(tmp, p)
    _cache["mtime"] = None            # force the next ids() to re-read


def hide(widget_id: str) -> None:
    wid = (widget_id or "").strip().lower()
    if not wid:
        return
    with _lock:
        cur = set(ids())
        if wid not in cur:
            cur.add(wid)
            _write(cur)


def unhide(widget_id: str) -> None:
    wid = (widget_id or "").strip().lower()
    if not wid:
        return
    with _lock:
        cur = set(ids())
        if wid in cur:
            cur.discard(wid)
            _write(cur)
