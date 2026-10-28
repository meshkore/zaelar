"""The operator's connected cloud drives as an Archivos provider: status fold, listing and navigation (V2-557).
The connector itself is reached through `data._svc()` by the caller.
"""
from __future__ import annotations

import time

from . import data as _d

# ── cloud drives ───────────────────────────────────────────────────────────────────────────────────────────
def _sync_status(db: dict, svc) -> dict:
    """Fold connection state AND the provider catalog into ONE `providers` list — never touches `provider`
    itself, which only the operator's `set_provider` action (or a connector picked by voice) may change."""
    st = svc.status()
    live = {p.get("id"): p for p in (st.get("providers") or [])}
    merged = []
    for cat in (svc.providers_public() or []):
        row = dict(cat)
        row.update(live.get(cat.get("id"), {}) or {})
        merged.append(row)
    for pid, row in live.items():
        if not any(m.get("id") == pid for m in merged):
            merged.append(dict(row))
    db["providers"] = merged
    db["connected"] = bool(st.get("connected"))
    db["providers_updated"] = int(time.time())
    return db


def _relist_cloud(db: dict, svc, folder_id: str) -> dict:
    res = svc.list_folder(db.get("provider") or "", folder_id or "")
    db["query"] = ""
    db["error"] = "" if res.get("ok") else _d._text(res.get("error"), 300)
    db["reason"] = _d._text(res.get("reason"), 300)
    db["entries"] = res.get("entries") or []
    db["next"] = res.get("next") or ""
    db["folder_id"] = folder_id or ""
    if res.get("provider"):
        db["provider"] = res["provider"]
    crumb = svc.breadcrumb(folder_id or "", db.get("provider") or "")
    db["trail"] = crumb.get("trail") or []
    return db


def _handle_cloud_nav(db: dict, svc, act: str, payload: dict) -> dict:
    if act == "open_file":
        fid = _d._text(payload.get("fileId") or payload.get("id"), 200)
        if not fid:
            return _d._err("dime QUÉ archivo abro: pásame su fileId (o su nombre)")
        res = svc.item(fid, db.get("provider") or "")
        if not res.get("ok"):
            return _d._err(res.get("error") or "no pude abrir ese archivo")
        entry = res.get("entry") or {}
        db["selected"] = entry
        _d._save(db)
        return {"ok": True, "file": {k: entry.get(k) for k in
                                     ("id", "name", "kind", "mime", "size", "modified", "web_url")}}

    if act == "search_files":
        q = _d._text(payload.get("query") or payload.get("q"), 200)
        if not q:
            return _d._err("dime qué busco dentro de tus archivos")
        res = svc.search(q, db.get("provider") or "")
        db["query"] = q
        db["folder_id"] = db.get("folder_id") or ""
        db["trail"] = []
        db["entries"] = res.get("entries") or []
        db["next"] = ""
        db["selected"] = None
        db["error"] = "" if res.get("ok") else _d._text(res.get("error"), 300)
        db["reason"] = _d._text(res.get("reason"), 300)
        _d._save(db)
        if db["error"]:
            return _d._err(db["error"])
        return {"ok": True, "query": q, "count": len(db["entries"]),
                "reason": db.get("reason") or "", "matches": _d._matches(db["entries"])}

    if act == "clear_search":
        db = _relist_cloud(db, svc, db.get("folder_id") or "")
        _d._save(db)
        return {"ok": True, "count": len(db["entries"])}

    if act == "go_home":
        target = ""
    elif act == "open_folder":
        target = _d._text(payload.get("folderId") or payload.get("id"), 200)
        if not target:
            return _d._err("dime QUÉ carpeta abro: pásame su folderId (o su nombre, y lo resuelvo con lo "
                        "que hay en pantalla)")
    elif act == "go_up":
        trail = db.get("trail") or []
        target = str(trail[-2]["id"]) if len(trail) >= 2 else ""
    else:                                                  # refresh
        target = db.get("folder_id") or ""
        if db.get("query"):
            res = svc.search(db["query"], db.get("provider") or "")
            db["entries"] = res.get("entries") or []
            db["error"] = "" if res.get("ok") else _d._text(res.get("error"), 300)
            db["reason"] = _d._text(res.get("reason"), 300)
            _d._save(db)
            return {"ok": True, "query": db["query"], "count": len(db["entries"]),
                    "matches": _d._matches(db["entries"])}
    db = _relist_cloud(db, svc, target)
    db["selected"] = None
    _d._save(db)
    if db.get("error"):
        return _d._err(db["error"])
    return {"ok": True, "folder_id": db["folder_id"], "count": len(db["entries"]),
            "where": _d._where(db), "reason": db.get("reason") or "", "entries": _d._matches(db["entries"])}
