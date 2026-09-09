"""The `torrent` widget's backend — a thin operator over the torrent connector (V2-637).

Like `archivos`/`youtube`/`fotos`, this widget IS a connector surface, so `data.py` reaches its connector
(`connectors.torrent.service`) instead of being stdlib-only — it is in `widgets/validator._STDLIB_EXEMPT` for
that reason, with the import DEFERRED so the widget catalog does not pay libtorrent on every prompt.

The declared actions ARE the skills (V2-544): the FlashBrain drives them through the generic `widget_data`
tool, no bespoke model tool. `view_data` re-reads the LIVE download status on every render so the card shows
real progress; `poll` exists only to let `widget.js` force that re-read on a timer while a download runs.
"""
from __future__ import annotations

import time

from .. import store

WIDGET_ID = "torrent"
DB_VERSION = 1


def _seed() -> dict:
    return {"id": "", "title": "", "query": "", "error": "", "updated": 0}


def _load() -> dict:
    return store.load(WIDGET_ID, default=_seed(), version=DB_VERSION)


def _svc():
    """Deferred so the catalog never imports libtorrent just to list this widget."""
    from connectors.torrent import service
    return service


def _stamp(db: dict) -> dict:
    db["updated"] = int(time.time())
    store.save(WIDGET_ID, db)
    return db


def _live_status(rid: str) -> dict:
    if not rid:
        return {}
    try:
        st = _svc().status(rid)
    except Exception as e:  # noqa: BLE001 — a viewer never crashes on a status read
        return {"ok": False, "error": str(e)[:160]}
    return st if isinstance(st, dict) else {}


def view_data(q: str = "") -> dict:
    db = _load()
    rid = db.get("id") or ""
    st = _live_status(rid)
    streamable = bool(st.get("streamable"))
    return {
        "id": rid,
        "title": db.get("title") or st.get("name") or "",
        "query": db.get("query") or "",
        "error": db.get("error") or (st.get("error") if not st.get("ok") else "") or "",
        "available": _svc().available() if _safe_available() else False,
        "status": st,
        "streamable": streamable,
        "stream_url": f"/api/torrent/stream/{rid}" if (rid and streamable) else "",
    }


def _safe_available() -> bool:
    try:
        return True if _svc() else False
    except Exception:  # noqa: BLE001
        return False


def prompt_digest() -> str:
    """What the operator is looking at, for the turn prompt — only while the card is open (V2-576)."""
    db = _load()
    rid = db.get("id") or ""
    if not rid:
        return "DESCARGAS: no hay ninguna descarga en curso."
    st = _live_status(rid)
    if not st.get("ok"):
        return f"DESCARGAS: «{db.get('title') or db.get('query')}» — {st.get('error') or 'sin estado'}."
    pct = int(round(float(st.get("progress") or 0) * 100))
    playing = "ya se puede reproducir" if st.get("streamable") else "aún no hay suficiente para reproducir"
    return (f"DESCARGAS: «{st.get('name') or db.get('title')}» — {pct}% descargado, "
            f"{st.get('num_peers') or 0} fuentes, {playing}.")


def apply_action(action: str, payload: dict = None) -> dict:
    payload = payload or {}
    if action == "search":
        query = str(payload.get("query") or "").strip()
        if not query:
            return {"ok": False, "error": "dime qué peli o vídeo busco"}
        res = _svc().search_and_play(query)
        db = _seed()
        db["query"] = query
        if res.get("ok"):
            db["id"], db["title"] = res["id"], res.get("title") or query
        else:
            db["error"] = res.get("error") or "no encontré nada para eso"
        _stamp(db)
        return res

    if action == "play":
        magnet = str(payload.get("magnet") or "").strip()
        res = _svc().add_magnet(magnet)
        db = _seed()
        if res.get("ok"):
            db["id"] = res["id"]
        else:
            db["error"] = res.get("error") or "no pude iniciar la descarga"
        _stamp(db)
        return res

    if action == "poll":
        return {"ok": True, **view_data()}

    if action == "stop":
        db = _load()
        rid = db.get("id") or ""
        res = _svc().remove(rid) if rid else {"ok": True}
        _stamp(_seed())
        return res

    return {"ok": False, "error": f"acción desconocida: {action}"}
