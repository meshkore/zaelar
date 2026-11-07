"""Which architecture piece an event comes from (`piece`), derived from the code that emitted it.

The canonical map (`.meshkore/docs/architecture/zaelar-architecture-map.json`) names every piece with the
`paths` that implement it. Every representation (the web, the session player, this stream) is aligned to that
map; an event that only carried `kind` + `label` left each reader to GUESS its box from the words. So the event
names its piece itself, by construction:

- the emitting module is read ONCE from the call stack (the first frame that is engine code and not a relay
  of the stream: the observer, the bus, this module), never tagged by hand at a thousand call sites;
- its path is matched against the map: the `emitters` table's exact file first (a module that hosts several
  pieces is routed there by kind), then a piece's own `paths` file, then the deepest folder of either; when a file
  belongs to several pieces, the one whose `emits` lists the event's kind wins, then the first that emits
  anything (a store box never speaks);
- a module that hosts several pieces passes `piece=` explicitly (`observer.emit(..., piece="w_tools")`);
- a module the map does not draw says so: `piece="unmapped"` and `piece_src=<its path>` — never a guess.

Cost: one stack walk per event, cached by code file (a dict read after the first event of each file). If the map
cannot be read, no piece is stamped at all (absent = unknown, honestly).
"""
from __future__ import annotations

import json
import os
import sys
import threading

UNMAPPED = "unmapped"

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
MAP_PATH = os.path.join(ROOT, ".meshkore", "docs", "architecture", "zaelar-architecture-map.json")

# Relays of the stream: an event passes through them, it is never FROM them. The first frame outside these is the
# emitter. Paths are relative to the engine root.
RELAYS = frozenset({
    "voice/observer.py",
    "bus/__init__.py",
    "bus/sse.py",
    "bus/log.py",
    "observability/pieces.py",
})

_lock = threading.Lock()
_index: dict | None = None          # {"files": {rel: [piece…]}, "dirs": [(rel_dir, [piece…])], "emits": {id: set}}
_rel_cache: dict[str, str | None] = {}   # co_filename → engine-relative path (None = outside the engine)
_piece_cache: dict[tuple, str] = {}      # (rel, kind) → piece


def _load() -> dict | None:
    global _index
    if _index is not None:
        return _index or None
    with _lock:
        if _index is not None:
            return _index or None
        try:
            with open(MAP_PATH, encoding="utf-8") as f:
                m = json.load(f)
        except Exception:  # noqa: BLE001 — no map, no stamp; the stream never breaks over it
            _index = {}
            return None
        files: dict[str, list] = {}       # a piece's own file → [piece…] (a file can be drawn in several boxes)
        dirs: dict[str, object] = {}      # folder → [piece…] (from paths) or an emitters value
        emits: dict[str, set] = {}
        for p in m.get("pieces") or []:
            pid = p.get("id")
            if not pid:
                continue
            emits[pid] = set(p.get("emits") or [])
            for path in p.get("paths") or []:
                path = str(path).strip("/")
                if path.endswith(".py"):
                    files.setdefault(path, []).append(pid)
                else:
                    dirs.setdefault(path, []).append(pid)
        routes: dict[str, object] = {}    # emitters' exact files
        for path, val in (m.get("emitters") or {}).items():
            if path.startswith("_"):
                continue
            path = str(path).strip("/")
            if path.endswith(".py"):
                routes[path] = val
            else:
                dirs[path] = val          # the emitters table speaks for a folder over a piece's sample path
        _index = {"files": files, "routes": routes,
                  "dirs": sorted(dirs.items(), key=lambda kv: -len(kv[0])),   # deeper folder first
                  "emits": emits}
        return _index


def known(piece: str) -> bool:
    idx = _load()
    return bool(idx) and piece in idx["emits"]


def _choose(val, kind: str) -> str | None:
    """One entry → a piece: an emitters value (id or {kind: id, '*': id}) or a list of pieces drawing the file."""
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get(kind) or val.get("*")
    if isinstance(val, list) and val:
        emits = (_load() or {}).get("emits", {})
        return (next((c for c in val if kind and kind in emits.get(c, ())), None)
                or next((c for c in val if emits.get(c)), None)
                or val[0])
    return None


def _entry(rel: str):
    idx = _load()
    if not idx:
        return None
    if rel in idx["routes"]:
        return idx["routes"][rel]
    if rel in idx["files"]:
        return idx["files"][rel]
    for d, val in idx["dirs"]:
        if rel == d or rel.startswith(d + "/"):
            return val
    return None


def piece_for(rel: str, kind: str = "") -> str:
    """The piece of an event of `kind` emitted from engine file `rel` (`UNMAPPED` when the map does not draw it).

    Order: the emitters table's exact file, then a piece's own file, then the deepest folder of either."""
    key = (rel, kind)
    hit = _piece_cache.get(key)
    if hit is not None:
        return hit
    out = _choose(_entry(rel), kind) or UNMAPPED
    _piece_cache[key] = out
    return out


_code_cache: dict = {}                  # code object → engine-relative path, or "" (a relay / not engine code)


def _classify(filename: str) -> str:
    """A code file → its engine-relative path, or "" when it is a relay of the stream or not engine code."""
    out = _rel_cache.get(filename)
    if filename not in _rel_cache:
        if filename and not filename.startswith("<"):
            real = os.path.realpath(filename)
            if real.startswith(ROOT + os.sep):
                out = real[len(ROOT) + 1:].replace(os.sep, "/")
        _rel_cache[filename] = out
    return "" if (out is None or out in RELAYS or out.startswith(".venv/")) else out


def emitter() -> str | None:
    """Engine-relative path of the code that emitted, walking up past the stream's relays and non-engine frames.

    Cheap on purpose (it runs on the publishing thread, often the voice one): one dict read per frame, keyed by
    the code object."""
    f = sys._getframe(1)
    cache = _code_cache
    while f is not None:
        code = f.f_code
        r = cache.get(code)
        if r is None:
            r = cache[code] = _classify(code.co_filename)
        if r:
            return r
        f = f.f_back
    return None


def stamp(ev: dict, piece: str | None = None, kind: str | None = None) -> dict:
    """Write `piece` (and `piece_src` when unmapped) on an event dict. Idempotent: a piece already there stays.

    `piece` given explicitly wins (a module hosting several pieces names its own); otherwise it is derived from
    the emitting module. `kind` = the observer kind it will be read as, when the dict's own `kind` means something
    else (a `memory.updated` payload's `kind` is the memory's kind). Never raises."""
    try:
        if ev.get("piece"):
            return ev
        if not _load():
            return ev
        if piece:
            ev["piece"] = piece if known(piece) else UNMAPPED
            if ev["piece"] == UNMAPPED:
                ev["piece_src"] = f"piece={piece}"
            return ev
        rel = emitter()
        if rel is None:
            ev["piece"] = UNMAPPED
            ev["piece_src"] = "?"
            return ev
        ev["piece"] = piece_for(rel, str(kind if kind is not None else (ev.get("kind") or "")))
        if ev["piece"] == UNMAPPED:
            ev["piece_src"] = rel
    except Exception:  # noqa: BLE001 — the stream never breaks over a stamp
        pass
    return ev


def reset_cache() -> None:
    """Forget the map and the caches (tests that swap the map)."""
    global _index
    with _lock:
        _index = None
        _rel_cache.clear()
        _piece_cache.clear()
        _code_cache.clear()
