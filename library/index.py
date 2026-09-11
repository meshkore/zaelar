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


def save_text(name: str, text: str, *, kind: str = "documents") -> dict:
    """Write a TEXT the agent produced (a transcript, a report, notes) into the library as a file (V2-661).

    Measured need (session 1cdcb08e, 2026-09-11): asked to save the Declaration of Independence «en mis
    archivos», a worker wrote a perfect `.md` — into the browser widget's data directory, the only path it
    knew — then watched the `archivos` card not show it and spent four minutes trying to download a PDF instead.
    A file the operator can find lives HERE, on its shelf, and nowhere else. The name is reduced to one safe
    leaf (no separators — a name cannot relocate the file), a text with no extension becomes `.md`, and a
    collision is suffixed rather than overwritten, like `file_into_place`."""
    body = str(text or "")
    if not body.strip():
        return {"ok": False, "error": "no hay texto que guardar"}
    leaf = os.path.basename(str(name or "").strip().replace("\\", "/")) or "documento"
    leaf = "".join(c for c in leaf if c.isalnum() or c in " ._-()áéíóúñÁÉÍÓÚÑüÜçÇ").strip(" .") or "documento"
    stem, ext = os.path.splitext(leaf)
    if formats.kind_of(leaf) != "document":
        stem, ext = leaf, ".md"          # «(EE. UU.)» is not an extension — the whole name is the stem
    dest_dir = paths.dir_for(kind if kind in paths.KINDS else "documents")
    dest = dest_dir / f"{stem}{ext}"
    n = 1
    while dest.exists():
        dest = dest_dir / f"{stem} ({n}){ext}"
        n += 1
    try:
        dest.write_text(body, encoding="utf-8")
    except OSError as e:
        return {"ok": False, "error": str(e)[:160]}
    rel = paths.rel_of(dest)
    return {"ok": True, "rel": rel, "path": str(dest), "entry": entry_for(rel)}


def rename(rel: str, new_name: str) -> dict:
    """Rename a file IN PLACE — same folder, a different leaf name. Collisions are refused rather than
    overwritten (losing a namesake file to a rename is not recoverable); the extension is not enforced, so
    the operator can fix a stray one, but the target still has to resolve inside the library."""
    src = paths.resolve(rel)
    if src is None or not src.is_file():
        return {"ok": False, "error": "no encuentro ese fichero en la biblioteca"}
    name = "".join(c for c in str(new_name or "").strip() if c not in "/\\").strip()
    if not name:
        return {"ok": False, "error": "hace falta un nombre nuevo"}
    dest = src.parent / name
    if dest.resolve() == src.resolve():
        return {"ok": True, "rel": paths.rel_of(src), "entry": entry_for(paths.rel_of(src))}
    if dest.exists():
        return {"ok": False, "error": f"ya hay un fichero llamado «{name}» ahí"}
    try:
        src.rename(dest)
    except OSError as e:
        return {"ok": False, "error": str(e)[:160]}
    return {"ok": True, "rel": paths.rel_of(dest), "entry": entry_for(paths.rel_of(dest))}


def duplicate(rel: str) -> dict:
    """A copy of a file, next to the original, suffixed `(copia)`/`(copia 2)`/… until a free name is found."""
    import shutil
    src = paths.resolve(rel)
    if src is None or not src.is_file():
        return {"ok": False, "error": "no encuentro ese fichero en la biblioteca"}
    stem, ext = os.path.splitext(src.name)
    dest = src.parent / f"{stem} (copia){ext}"
    n = 2
    while dest.exists():
        dest = src.parent / f"{stem} (copia {n}){ext}"
        n += 1
    try:
        shutil.copy2(src, dest)
    except OSError as e:
        return {"ok": False, "error": str(e)[:160]}
    return {"ok": True, "rel": paths.rel_of(dest), "entry": entry_for(paths.rel_of(dest))}


def delete(rel: str) -> dict:
    """Remove a file from disk — irreversible, the caller's job to confirm before calling this."""
    p = paths.resolve(rel)
    if p is None or not p.is_file():
        return {"ok": False, "error": "no encuentro ese fichero en la biblioteca"}
    try:
        p.unlink()
    except OSError as e:
        return {"ok": False, "error": str(e)[:160]}
    return {"ok": True}


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
