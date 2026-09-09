"""What is in the library, described the way a widget needs it (V2-638).

One normalized shape for every file, whatever produced it — a torrent that finished, a document a worker
wrote, a track downloaded from somewhere. The two fields that matter to a player are `url` (where to fetch
the bytes) and `playable` (whether it can be played at all, so a widget never mounts a `<video>` over a file
the browser will refuse). Everything is read from disk on demand: this is a directory listing, not a database
to keep in sync with one.
"""
from __future__ import annotations

import os
import time
from urllib.parse import quote

from . import formats, paths

MAX_ENTRIES = 500


def entry_for(rel: str) -> dict | None:
    """The normalized record for one library-relative path, or None if it is not a file inside the library."""
    p = paths.resolve(rel)
    if p is None or not p.is_file():
        return None
    rel = paths.rel_of(p)
    name = p.name
    try:
        stat = p.stat()
        size, mtime = int(stat.st_size), int(stat.st_mtime)
    except OSError:
        size, mtime = 0, 0
    playable = formats.browser_playable(name)
    return {
        "rel": rel,
        "name": name,
        "kind": formats.kind_of(name),
        "size": size,
        "updated": mtime,
        "playable": playable,
        "mime": formats.mime_of(name),
        # A file the browser cannot play still gets a download url — that is the operator's pendrive case,
        # and offering nothing at all is how a legitimate file looks like a broken one.
        "url": stream_url(rel) if playable else "",
        "download_url": download_url(rel),
    }


def stream_url(rel: str) -> str:
    return "/api/library/stream?path=" + quote(str(rel or ""), safe="")


def download_url(rel: str) -> str:
    return "/api/library/download?path=" + quote(str(rel or ""), safe="")


def listing(kind: str = "", *, limit: int = MAX_ENTRIES, playable_only: bool = False) -> list[dict]:
    """Everything in the library, newest first. `kind` filters by shelf (video/audio/image/document)."""
    root = paths.root()
    out: list[dict] = []
    if not root.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if fn.startswith(".") or fn.endswith(".part"):
                continue                      # a half-written torrent piece file is not a library item
            rec = entry_for(paths.rel_of(os.path.join(dirpath, fn)))
            if not rec:
                continue
            if kind and rec["kind"] != kind:
                continue
            if playable_only and not rec["playable"]:
                continue
            out.append(rec)
            if len(out) >= limit * 4:         # bounded walk; sorted and trimmed below
                break
    out.sort(key=lambda r: r.get("updated") or 0, reverse=True)
    return out[:limit]


def file_into_place(src_path, *, name: str = "") -> dict:
    """Move a finished download out of the sandbox and onto its shelf, by what it IS.

    The torrent client writes ONLY into `downloads/` (the operator's isolation rule); filing is OUR move, made
    after the fact, so the client never needs a path outside its sandbox. A name collision is resolved by
    suffixing rather than overwriting — losing somebody's file to a same-named download is not recoverable."""
    src = paths.resolve(paths.rel_of(src_path)) if paths.rel_of(src_path) else None
    if src is None or not src.is_file():
        return {"ok": False, "error": "no encuentro ese fichero en la biblioteca"}
    dest_dir = paths.dir_for_file(name or src.name)
    base = name or src.name
    dest = dest_dir / base
    stem, ext = os.path.splitext(base)
    n = 1
    while dest.exists():
        dest = dest_dir / f"{stem} ({n}){ext}"
        n += 1
    try:
        src.replace(dest)
    except OSError as e:
        return {"ok": False, "error": str(e)[:160]}
    return {"ok": True, "rel": paths.rel_of(dest), "entry": entry_for(paths.rel_of(dest))}


def summary() -> dict:
    """Counts and bytes per shelf — what the brain says when asked «¿qué tengo guardado?»."""
    per: dict = {}
    total = 0
    for rec in listing(limit=MAX_ENTRIES):
        k = rec["kind"]
        row = per.setdefault(k, {"count": 0, "bytes": 0})
        row["count"] += 1
        row["bytes"] += rec["size"]
        total += rec["size"]
    return {"ok": True, "shelves": per, "bytes": total, "at": int(time.time())}
