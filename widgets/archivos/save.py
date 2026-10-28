"""`save_document`: a TEXT becomes a file on a library shelf, and the card lands on it (V2-661).

Split out of `data.py`.
"""
from __future__ import annotations

from . import data as _d
from .local import _local_row, _relist_local

def _save_document(db: dict, payload: dict) -> dict:
    """`save_document {name, text, folderId?}` → a real file in the library, and the card lands on its shelf
    showing it. The caller gets `where` (the shelf label) and `path` (the absolute path on this machine — what
    a self-hosted operator can go and open) beside the entry; refusing an empty text names the fields."""
    from library import index as _idx
    name = _d._text(payload.get("name") or payload.get("title") or payload.get("filename"), 160)
    text = str(payload.get("text") or payload.get("body") or payload.get("content") or "")
    if not text.strip():
        return _d._err("no llegó ningún texto que guardar: manda `text` (el contenido) y `name` (el nombre del fichero)")
    fid = _d._text(payload.get("folderId") or payload.get("folder") or payload.get("shelf"), 40).lower()
    kind = fid.split(":", 1)[1] if fid.startswith("shelf:") else fid
    from library import paths as _paths
    kind = kind if kind in _paths.KINDS else "documents"
    res = _idx.save_text(name, text, kind=kind)
    if not res.get("ok"):
        return _d._err(res.get("error") or "no pude guardar el fichero")
    db["provider"] = "local"
    db["query"] = ""
    db = _relist_local(db, f"shelf:{kind}")
    rec = res.get("entry") or {}
    db["selected"] = _local_row(rec) if rec else None
    _d._save(db)
    return {"ok": True, "file": db["selected"], "where": _d._SHELF_LABEL.get(kind, kind), "folder_id": f"shelf:{kind}",
            "path": res.get("path") or "", "rel": res.get("rel") or ""}
