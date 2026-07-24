#
# personalizado-reproduzca-video — reproductor de YouTube EMBEBIDO dedicado en exclusiva al gol de la
# "Mano de Dios" de Maradona: a diferencia del widget genérico `youtube`, este NO admite cargar otro vídeo,
# solo controlar la reproducción del suyo (play/pausa/volumen/silencio/reinicio). data.py es servidor puro
# (stdlib) — nunca toca el reproductor; el cliente (widget.js) aplica los comandos por postMessage.
#
from .. import store

WID = "personalizado-reproduzca-video"

# Fijo: el gol de la "Mano de Dios" de Maradona (Argentina 2-1 Inglaterra, México 86).
_VIDEO_ID = "uq6IJTtsz_Q"
_TITLE = "Gol de la Mano de Dios — Maradona (Argentina 2-1 Inglaterra, México 86)"

_SEED = {
    "videoId": _VIDEO_ID,
    "title": _TITLE,
    "url": "https://www.youtube.com/watch?v=" + _VIDEO_ID,
    "volume": 70,
    "muted": True,      # el autoplay del navegador exige empezar en silencio; "quita el silencio" para oírlo
    "paused": False,    # listo para reproducirse en cuanto se abre la tarjeta
    "last_cmd": "load",
    "cmd_seq": 0,
}


def _load() -> dict:
    db = store.load(WID, dict(_SEED))
    for k, v in _SEED.items():                          # normaliza campos ausentes (store antiguo)
        db.setdefault(k, v)
    db["videoId"] = _VIDEO_ID                            # vídeo fijo: nunca lo cambia un store viejo
    db["title"] = _TITLE
    db["url"] = _SEED["url"]
    return db


def view_data(q: str = "") -> dict:
    try:
        return _load()
    except Exception as e:
        return {**_SEED, "error": str(e)[:120]}


def _bump(db: dict, cmd: str) -> dict:
    db["last_cmd"] = cmd
    db["cmd_seq"] = int(db.get("cmd_seq") or 0) + 1
    store.save(WID, db)
    return {"ok": True, "cmd": cmd, "videoId": db.get("videoId"), "title": db.get("title"),
            "volume": db.get("volume"), "muted": db.get("muted"), "paused": db.get("paused")}


def apply_action(action: str, payload: dict = None) -> dict:
    p = payload or {}
    db = _load()

    if action == "play":
        db["paused"] = False
        return _bump(db, "play")
    if action == "pause":
        db["paused"] = True
        return _bump(db, "pause")
    if action == "mute":
        db["muted"] = True
        return _bump(db, "mute")
    if action == "unmute":
        db["muted"] = False
        return _bump(db, "unmute")
    if action == "volume_up":
        db["volume"] = min(100, int(db.get("volume") or 70) + 15)
        db["muted"] = False
        return _bump(db, "volume_up")
    if action == "volume_down":
        db["volume"] = max(0, int(db.get("volume") or 70) - 15)
        return _bump(db, "volume_down")
    if action == "set_volume":
        try:
            lvl = int(p.get("level"))
        except (TypeError, ValueError):
            return {"ok": False, "error": "bad_level", "message": "Dime un nivel entre 0 y 100."}
        db["volume"] = max(0, min(100, lvl))
        db["muted"] = db["volume"] == 0
        return _bump(db, "set_volume")
    if action == "restart":
        db["paused"] = False
        return _bump(db, "restart")

    return {"ok": False, "error": "unknown_action", "action": action}
