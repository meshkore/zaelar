"""The `torrent` widget's backend — a DOWNLOAD MANAGER over the torrent connector (torrent-client redesign).

Like `archivos`/`youtube`/`fotos`, this widget IS a connector surface, so `data.py` reaches its connector
(`connectors.torrent.service`) instead of being stdlib-only — it is in `widgets/validator._STDLIB_EXEMPT` for
that reason, with the import DEFERRED so the widget catalog does not pay libtorrent on every prompt.

The operator's own framing settled the shape: two lists, like any torrent client — the files that are part of
the SEEDS (finished, still sharing back) on one side, the files still DOWNLOADING (or finished but not yet
reannounced as seeding) on the other — never one download taking the whole screen. This widget carries NO
video/audio element of its own: it never plays anything. Playing routes to whichever surface a file belongs on
— `youtube` for a playable video, `musica` for a finished playable audio track — through
`nucleo/torrent_router.py`, because a widget's own `apply_action` must never reach into a sibling's store
(widgets/AGENTS.md's isolation rule). This widget itself never lists more than what `connectors.torrent.
service.active()` already knows — no private bookkeeping of "my" downloads, because the client is a SYSTEM
tool any widget can start a download on (V2-638): a magnet started from here, from the youtube widget's own
`play_torrent`, or by voice, all show up on the same shelf.

The declared actions ARE the skills (V2-544): the FlashBrain drives them through the generic `widget_data`
tool, no bespoke model tool. `view_data` re-reads the LIVE download status on every render so the card shows
real progress; `poll` exists only to let `widget.js` force that re-read on a timer while a download runs.
"""
from __future__ import annotations

import time

from .. import store

WIDGET_ID = "torrent"
DB_VERSION = 2


def _seed() -> dict:
    # `titles` remembers what the OPERATOR asked for, keyed by id — the only bookkeeping this widget keeps,
    # and only a display nicety: before metadata resolves, the connector's own `name` is still empty, so a
    # row would otherwise show nothing to read while it is still finding sources.
    return {"titles": {}, "error": "", "updated": 0}


def _migrate(db: dict, from_v: int) -> dict:
    """v1 (the old single-download shape) → v2 (the manager's list-of-many shape). The single id it held, if
    any, still exists as a real handle on the connector, so it needs no migration of its own — `view_data`
    reads `service.active()` fresh, not this store."""
    if from_v < 2:
        title = db.pop("title", "") or ""
        old_id = db.pop("id", "")
        db.pop("query", None)
        db["titles"] = {old_id: title} if old_id and title else {}
    return db


def _load() -> dict:
    return store.load(WIDGET_ID, default=_seed(), version=DB_VERSION, migrate=_migrate)


def _svc():
    """Deferred so the catalog never imports libtorrent just to list this widget."""
    from connectors.torrent import service
    return service


def _stamp(db: dict) -> dict:
    db["updated"] = int(time.time())
    store.save(WIDGET_ID, db)
    return db


def _safe_available() -> bool:
    try:
        return bool(_svc().available())
    except Exception:  # noqa: BLE001
        return False


def _unavailable_reason() -> str:
    try:
        return _svc().unavailable_reason()
    except Exception:  # noqa: BLE001
        return "el cliente de descargas no está disponible en esta instalación"


def _live_status(rid: str) -> dict:
    if not rid:
        return {}
    try:
        st = _svc().status(rid)
    except Exception as e:  # noqa: BLE001 — a viewer never crashes on a status read
        return {"ok": False, "error": str(e)[:160]}
    return st if isinstance(st, dict) else {}


def _row(st: dict, titles: dict) -> dict:
    rid = st.get("id") or ""
    pct = int(round(float(st.get("progress") or 0) * 100))
    kind = st.get("kind") or ""
    playable = bool(st.get("playable"))
    complete = pct >= 100 or st.get("state") == "seeding"
    return {
        "id": rid,
        "title": st.get("name") or titles.get(rid) or "Buscando…",
        "kind": kind or "other",
        "file_name": st.get("file_name") or "",
        "playable": playable,
        "group": st.get("group") or ("seed" if st.get("state") == "seeding" else "download"),
        "state": st.get("state") or "",
        "progress": pct,
        "complete": complete,
        "download_rate": int(st.get("download_rate") or 0),
        "num_peers": int(st.get("num_peers") or 0),
        "downloaded": int(st.get("downloaded") or 0),
        "size": int(st.get("size") or 0),
        "streamable": bool(st.get("streamable")),
        # What the ▶ on this row would do: stream now (still filling or finished, still in the session),
        # or nothing until it is complete (a playable audio track, which only plays once filed).
        "can_stream": kind == "video" and playable,
        "can_play": (kind == "video" and playable) or (kind == "audio" and playable and complete),
    }


def view_data(q: str = "") -> dict:
    db = _load()
    avail = _safe_available()
    items: list[dict] = []
    if avail:
        titles = db.get("titles") or {}
        for st in _svc().active():
            if not st.get("ok"):
                continue
            items.append(_row(st, titles))
    seeds = [it for it in items if it["group"] == "seed"]
    downloads = [it for it in items if it["group"] != "seed"]
    return {
        "available": avail,
        "unavailable_reason": "" if avail else _unavailable_reason(),
        "error": db.get("error") or "",
        "seeds": seeds,
        "downloads": downloads,
    }


def _safe_active_ids() -> set:
    try:
        return {str(it.get("id") or "") for it in _svc().active() if it.get("ok")}
    except Exception:  # noqa: BLE001
        return set()


def prompt_digest() -> str:
    """What the operator is looking at, for the turn prompt — only while the card is open (V2-576)."""
    if not _safe_available():
        return f"DESCARGAS: {_unavailable_reason()}."
    db = _load()
    titles = db.get("titles") or {}
    items = [_row(st, titles) for st in _svc().active() if st.get("ok")]
    if not items:
        return "DESCARGAS: no hay ninguna descarga ni ninguna semilla activa."
    downloading = [it for it in items if it["group"] != "seed"]
    seeding = [it for it in items if it["group"] == "seed"]
    parts = []
    if downloading:
        top = "; ".join(f"«{it['title']}» {it['progress']}%" for it in downloading[:3])
        parts.append(f"{len(downloading)} descargando ({top})")
    if seeding:
        parts.append(f"{len(seeding)} completadas, compartiendo como semilla")
    return "DESCARGAS: " + " · ".join(parts) + "."


def ref_index() -> list[dict]:
    """Live rows, for `widgets/refs.py` to resolve a spoken reference («cancela la peli X») to an id."""
    if not _safe_available():
        return []
    db = _load()
    titles = db.get("titles") or {}
    out = []
    for st in _svc().active():
        if not st.get("ok"):
            continue
        row = _row(st, titles)
        out.append({"id": row["id"], "label": row["title"], "field": "id"})
    return out


def _remember_title(db: dict, rid: str, title: str) -> None:
    if not (rid and title):
        return
    titles = db.setdefault("titles", {})
    titles[rid] = title
    # Bounded — a title for a download that no longer exists is dead weight, never useful (view_data reads
    # live status, not this dict, so a stale entry here would linger forever without this).
    active = _safe_active_ids()
    for k in list(titles.keys()):
        if k not in active and k != rid:
            titles.pop(k, None)


def apply_action(action: str, payload: dict = None) -> dict:
    payload = payload or {}

    if action == "search":
        query = str(payload.get("query") or "").strip()
        if not query:
            return {"ok": False, "error": "dime qué peli o vídeo busco"}
        keep = bool(payload.get("keep"))
        res = _svc().search_and_play(query, keep=keep)
        db = _load()
        if res.get("ok"):
            _remember_title(db, res.get("id") or "", res.get("title") or query)
            db["error"] = ""
        else:
            db["error"] = res.get("error") or "no encontré nada para eso"
        _stamp(db)
        return res

    if action == "add_magnet":
        magnet = str(payload.get("magnet") or "").strip()
        keep = bool(payload.get("keep"))
        res = _svc().add_magnet(magnet, keep=keep)
        db = _load()
        if res.get("ok"):
            _remember_title(db, res.get("id") or "", "")
            db["error"] = ""
        else:
            db["error"] = res.get("error") or "no pude iniciar la descarga"
        _stamp(db)
        return res

    if action == "open":
        rid = str(payload.get("id") or "").strip()
        if not rid:
            return {"ok": False, "error": "falta la descarga a reproducir"}
        st = _live_status(rid)
        if not st.get("ok"):
            return {"ok": False, "error": st.get("error") or "esa descarga ya no está activa"}
        db = _load()
        row = _row(st, db.get("titles") or {})
        if row["kind"] == "video":
            if not row["playable"]:
                from library import formats
                return {"ok": False, "error": formats.refusal(row["file_name"])}
            if not (row["streamable"] or row["complete"]):
                return {"ok": False, "error": "aún no hay suficiente descargado para empezar a verla"}
            from nucleo import torrent_router
            return torrent_router.route_video(rid, row["title"])
        if row["kind"] == "audio":
            if not row["playable"]:
                from library import formats
                return {"ok": False, "error": formats.refusal(row["file_name"])}
            if not row["complete"]:
                return {"ok": False, "error": "espera a que termine de descargarse para reproducirla"}
            from nucleo import torrent_router
            return torrent_router.route_audio(rid, row["title"])
        return {"ok": False, "error": "este fichero no se reproduce aquí — usa «Guardar» para descargarlo"}

    if action == "save":
        rid = str(payload.get("id") or "").strip()
        if not rid:
            return {"ok": False, "error": "falta la descarga a guardar"}
        res = _svc().file_it(rid)
        if res.get("ok"):
            db = _load()
            (db.get("titles") or {}).pop(rid, None)
            _stamp(db)
        return res

    if action == "remove":
        rid = str(payload.get("id") or "").strip()
        if not rid:
            return {"ok": False, "error": "falta la descarga a eliminar"}
        res = _svc().remove(rid)
        db = _load()
        (db.get("titles") or {}).pop(rid, None)
        _stamp(db)
        return res

    if action == "poll":
        return {"ok": True, **view_data()}

    return {"ok": False, "error": f"acción desconocida: {action}"}
