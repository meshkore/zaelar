"""The agent's OWN library as Archivos' default provider: shelves, listing, search, open, and the local-only writes.

Split out of `data.py` (V2-658 behaviour unchanged). Shared helpers are read back through the `data` module.
"""
from __future__ import annotations

from . import data as _d

# ── local library ──────────────────────────────────────────────────────────────────────────────────────────
# `library/paths.py::KINDS` names FOLDERS ("images", "documents" — plural, genesis-facing) while
# `library/formats.py::kind_of()` classifies a FILE ("image", "document" — singular). The two vocabularies
# never had to meet before this widget: every other caller only ever filtered by "video"/"audio", where
# singular and plural happen to coincide. Mapped here rather than in `library/` itself — changing a shared
# module's contract for one caller is a bigger, riskier edit than translating at the one seam that needs it.
_FMT_KIND = {"video": "video", "audio": "audio", "documents": "document", "images": "image"}


def _shelf_listing(kind: str) -> list[dict]:
    """Everything ON a shelf. `downloads` is the one shelf that is a PLACE, not a classification (the torrent
    sandbox, V2-638) — `library/index.py::listing()` only filters by extension-derived kind, so it cannot
    answer "what's physically in this folder"; that one is walked directly instead."""
    from library import index as _idx
    if kind == "downloads":
        return _downloads_listing()
    return _idx.listing(kind=_FMT_KIND.get(kind, kind))


def _downloads_listing() -> list[dict]:
    import os
    from library import index as _idx, paths as _paths
    d = _paths.downloads_dir()
    out = []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        if n.startswith(".") or n.endswith(".part"):
            continue
        p = d / n
        if not p.is_file():
            continue
        rec = _idx.entry_for(_paths.rel_of(p))
        if rec:
            out.append(rec)
    return out


def _local_row(rec: dict) -> dict:
    modified = ""
    ts = int(rec.get("updated") or 0)
    if ts:
        try:
            from datetime import datetime, timezone
            modified = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except Exception:  # noqa: BLE001
            modified = ""
    return {"id": rec["rel"], "name": rec["name"], "kind": "file", "file_kind": rec["kind"],
            "mime": rec["mime"], "size": rec["size"], "modified": modified, "provider": "local",
            "playable": rec["playable"], "url": rec["url"], "download_url": rec["download_url"],
            "same_machine": _same_machine(), "shelf": _d._SHELF_OF_FMT.get(rec["kind"], "")}


def _shelf_rows() -> list[dict]:
    from library import paths as _paths
    rows = []
    for kind in _paths.KINDS:
        n = len(_shelf_listing(kind))
        rows.append({"id": f"shelf:{kind}", "name": _d._SHELF_LABEL.get(kind, kind), "kind": "folder",
                     "mime": "", "size": None, "modified": "", "provider": "local", "count": n})
    return rows


def _relist_local(db: dict, folder_id: str) -> dict:
    from library import paths as _paths
    db["query"] = ""
    db["error"] = ""
    db["reason"] = ""
    fid = str(folder_id or "").strip()
    if not fid:
        db["entries"] = _shelf_rows()
        db["trail"] = []
        db["folder_id"] = ""
        return db
    kind = fid.split(":", 1)[1] if fid.startswith("shelf:") else fid
    if kind not in _paths.KINDS:
        db["entries"] = []
        db["trail"] = []
        db["folder_id"] = ""
        from i18n import runtime as _rt
        db["error"] = _rt.text("widgets.archivos.err_no_folder", default="folder «{id}» does not exist").replace("{id}", fid)
        return db
    recs = _shelf_listing(kind)
    db["entries"] = [_local_row(r) for r in recs]
    db["trail"] = [{"id": f"shelf:{kind}", "name": _d._SHELF_LABEL.get(kind, kind)}]
    db["folder_id"] = f"shelf:{kind}"
    return db


def _local_search(q: str) -> list[dict]:
    from library import index as _idx
    ql = q.strip().lower()
    recs = _idx.listing()
    hits = [r for r in recs if ql in r["name"].lower()]
    return [_local_row(r) for r in hits[:200]]


def _open_local(rel: str) -> dict:
    from library import formats as _fmt, index as _idx
    rec = _idx.entry_for(rel)
    if not rec:
        return _d._err("no encuentro ese archivo en la biblioteca")
    fk = rec["kind"]
    if fk == "video":
        if not rec["playable"]:
            return _d._err(_fmt.refusal(rec["name"]), download_url=rec["download_url"])
        from nucleo import library_router
        return library_router.route_video(rel, rec["name"])
    if fk == "audio":
        if not rec["playable"]:
            return _d._err(_fmt.refusal(rec["name"]), download_url=rec["download_url"])
        from nucleo import library_router
        return library_router.route_audio(rel, rec["name"])
    if fk == "image" and rec["playable"]:
        return {"ok": True, "preview": {"kind": "image", "url": rec["url"], "name": rec["name"]}}
    if fk == "document" and rec["playable"]:
        return {"ok": True, "preview": {"kind": "document", "url": rec["url"], "name": rec["name"],
                                        "mime": rec["mime"]}}
    return _d._err(_fmt.refusal(rec["name"]), download_url=rec["download_url"])


def _handle_local_nav(db: dict, act: str, payload: dict) -> dict:
    from library import paths as _paths

    if act == "open_file":
        fid = _d._text(payload.get("fileId") or payload.get("id"), 400)
        if not fid:
            return _d._err("dime QUÉ archivo abro")
        return _open_local(fid)

    if act == "search_files":
        q = _d._text(payload.get("query") or payload.get("q"), 200)
        if not q:
            return _d._err("dime qué busco dentro de tu biblioteca")
        matches = _local_search(q)
        db["query"] = q
        db["trail"] = []
        db["entries"] = matches
        db["selected"] = None
        db["error"] = ""
        db["reason"] = ""
        _d._save(db)
        return {"ok": True, "query": q, "count": len(matches), "matches": _d._matches(matches)}

    if act == "clear_search":
        target = db.get("folder_id") or ""
    elif act == "go_home":
        target = ""
    elif act == "open_folder":
        target = _d._text(payload.get("folderId") or payload.get("id"), 200)
        if not target:
            return _d._err("dime QUÉ carpeta abro: elige video, audio, documents, images o downloads")
        if target in _paths.KINDS:
            target = f"shelf:{target}"
    elif act == "go_up":
        target = ""                                       # one level deep by design — see the module docstring
    else:                                                  # refresh
        if db.get("query"):
            matches = _local_search(db["query"])
            db["entries"] = matches
            _d._save(db)
            return {"ok": True, "query": db["query"], "count": len(matches), "matches": _d._matches(matches)}
        target = db.get("folder_id") or ""

    db = _relist_local(db, target)
    db["selected"] = None
    _d._save(db)
    if db.get("error"):
        return _d._err(db["error"])
    return {"ok": True, "folder_id": db["folder_id"], "count": len(db["entries"]),
            "where": _d._where(db), "entries": _d._matches(db["entries"])}


def _same_machine() -> bool:
    """Is the browser reading this card on the SAME machine the engine runs on? Self-host: yes, always — the
    engine process already IS the operator's own computer, so opening a Finder/Explorer window on it shows
    the operator something real. A container deployment: no — there is no local disk of the operator's to reveal, and
    trying would open a window on a remote, usually headless, server nobody is looking at."""
    try:
        from nucleo.cloud_account import is_cloud_account
        return not is_cloud_account()
    except Exception:  # noqa: BLE001 — an unreadable signal must default to the SAFE answer: offer nothing
        return False


def _reveal_in_os(path) -> bool:
    """Best-effort: ask the OS to show this file in its native file manager. Never raises — a desktop-less
    self-host (a headless Linux box someone still chose to run natively) simply reports it could not."""
    import subprocess
    import sys
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", str(path)], check=False, timeout=3)
        elif sys.platform.startswith("win"):
            subprocess.run(["explorer", "/select,", str(path)], check=False, timeout=3)
        else:
            subprocess.run(["xdg-open", str(path.parent)], check=False, timeout=3)
        return True
    except Exception:  # noqa: BLE001
        return False


def _handle_local_write(db: dict, act: str, payload: dict) -> dict:
    from library import index as _idx
    fid = _d._text(payload.get("fileId") or payload.get("id"), 400)
    if not fid:
        return _d._err("dime QUÉ archivo")
    if act == "reveal_local_file":
        # Read-only from the LIBRARY's point of view (never touches the file) — kept in the "write" gate
        # anyway because, like the others, it makes no sense for a cloud provider (V2-658: the operator
        # caught a real duplicate — double-clicking an unplayable local file downloaded a SECOND copy into
        # his Mac's own Downloads folder, when the file already sat on that same Mac's disk in Zaelar's own
        # library). Local + self-host: reveal it in place. Anything else: nothing to reveal.
        if not _same_machine():
            return _d._err("el agente está en la nube: aquí no hay una carpeta local que abrir — descarga el "
                        "archivo si lo quieres en este ordenador")
        from library import paths as _paths
        p = _paths.resolve(fid)
        if p is None or not p.is_file():
            return _d._err("no encuentro ese archivo en la biblioteca")
        opened = _d._reveal_in_os(p)   # read back through data: a test patches it there
        return {"ok": True, "path": str(p), "opened": opened}
    if act == "rename_file":
        name = _d._text(payload.get("name") or payload.get("newName"), 200)
        if not name:
            return _d._err("dime el nombre nuevo")
        res = _idx.rename(fid, name)
    elif act == "copy_file":
        res = _idx.duplicate(fid)
    else:                                                  # delete_file
        res = _idx.delete(fid)
    if not res.get("ok"):
        return _d._err(res.get("error") or "no pude completar la operación")
    db = _relist_local(db, db.get("folder_id") or "")
    _d._save(db)
    out = {"ok": True, "count": len(db["entries"])}
    if "rel" in res:
        out["rel"] = res["rel"]
    return out
