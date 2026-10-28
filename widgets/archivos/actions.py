"""Archivos' action handlers — one function per action (or per family sharing one body), dispatched by
`data.ACTIONS`.

Split out of `data.py`, which keeps the contract and the table. Every handler opens with `_begin`: the prelude
the old single dispatch ran for every action (load, seed the torrents section, bring the Biblioteca to the front
for a library verb). Shared helpers are read back through the `data` module, so a test that patches one there
(`_svc`) is honoured here too.
"""
from __future__ import annotations

from . import data as _d
from . import torrents as _tor
from .cloud import _handle_cloud_nav, _relist_cloud, _sync_status
from .local import _handle_local_nav, _handle_local_write, _relist_local
from .save import _save_document


def _begin(act: str) -> dict:
    db = _d._load()
    _tor.state(db)                 # the torrents section is seeded on every action, as the torrent dispatch did
    # Any library verb brings the Biblioteca back in front: «abre la carpeta de vídeo» while looking at the
    # torrents means the library.
    if act in _d._LIBRARY_VERBS:
        db["section"] = "biblioteca"
    return db


def _torrent(act: str, payload: dict) -> dict:
    # V2-764 — the Torrents section (and the section switch itself) live in `torrents.py`.
    db = _d._load()
    res = _tor.handle(db, act, payload)
    if res is None:
        return _d._unknown(act)
    _d._save(db)
    return res


def _a_sync_providers(act: str, payload: dict) -> dict:
    # Cheap, read-only-feeling refresh of the header's provider chips — the icon row must be able to show
    # "Drive"/"OneDrive" BEFORE the operator ever opens the connect wizard. Mirrors `youtube`'s own
    # `sync_platforms` (V2-597): the card asks once when stale, `view_data` never touches the network.
    db = _begin(act)
    svc = _d._svc()
    if svc is None:
        return {"ok": True, "providers": []}
    db = _sync_status(db, svc)
    _d._save(db)
    return {"ok": True, "providers": db["providers"]}


def _a_set_view(act: str, payload: dict) -> dict:
    db = _begin(act)
    mode = _d._text(payload.get("mode"), 12).lower()
    if mode not in _d._MODES:
        return _d._err(f"vista desconocida: «{mode}». Usa list o grid")
    db["mode"] = mode
    _d._save(db)
    return {"ok": True, "mode": mode}


def _a_set_provider(act: str, payload: dict) -> dict:
    db = _begin(act)
    want = _d._text(payload.get("provider"), 40).lower() or "local"
    if want == "local":
        db["provider"] = "local"
        db = _relist_local(db, "")
        _d._save(db)
        return {"ok": True, "provider": "local", "count": len(db["entries"])}
    svc = _d._svc()
    if svc is None:
        return _d._err("el conector de archivos no está disponible en esta instalación")
    db = _sync_status(db, svc)
    connected = [p["id"] for p in (db.get("providers") or []) if p.get("connected")]
    if want not in connected:
        return _d._err(f"«{want}» no está conectado. Conectados ahora mismo: "
                       f"{', '.join(connected) or 'ninguno'}")
    db["provider"] = want
    db = _relist_cloud(db, svc, "")
    _d._save(db)
    return {"ok": True, "provider": want, "count": len(db["entries"])}


def _local_write(act: str, payload: dict) -> dict:
    db = _begin(act)
    provider = db.get("provider") or "local"
    if provider != "local":
        return _d._err(f"«{provider}» no permite modificar archivos desde aquí — solo se puede navegar, "
                       f"buscar y abrir")
    return _handle_local_write(db, act, payload)


def _a_save_document(act: str, payload: dict) -> dict:
    # V2-661 — a TEXT becomes a file ON A SHELF, whatever the provider on screen: the library is the one
    # place a file the operator asks for can land (a worker wrote the Declaration into the browser
    # widget's data dir — the only path it knew — and then watched this card not show it).
    return _save_document(_begin(act), payload)


def _nav(act: str, payload: dict) -> dict:
    db = _begin(act)
    if (db.get("provider") or "local") == "local":
        return _handle_local_nav(db, act, payload)
    svc = _d._svc()
    if svc is None:
        return _d._err("el conector de archivos no está disponible en esta instalación")
    db = _sync_status(db, svc)
    if not db.get("connected"):
        return _d._err("no hay ningún servicio de archivos conectado: se conecta en la sección Conectores "
                       "(show_panel panel='conectores', connector='gdrive' u 'onedrive')")
    return _handle_cloud_nav(db, svc, act, payload)
