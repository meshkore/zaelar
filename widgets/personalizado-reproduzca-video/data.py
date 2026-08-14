#
# personalizado-reproduzca-video — EMBEDDED YouTube player dedicated exclusively to Maradona's
# "Hand of God" goal: unlike the generic `youtube` widget, this one does NOT allow loading another video,
# only controlling its own playback (play/pause/volume/mute/restart). data.py is pure server code
# (stdlib) — it never touches the player; the client (widget.js) applies commands through postMessage.
#
from .. import store

WID = "personalizado-reproduzca-video"

# Fixed: Maradona's "Hand of God" goal (Argentina 2-1 England, Mexico 86).
_VIDEO_ID = "uq6IJTtsz_Q"
_TITLE = "Gol de la Mano de Dios — Maradona (Argentina 2-1 Inglaterra, México 86)"

_SEED = {
    "videoId": _VIDEO_ID,
    "title": _TITLE,
    "url": "https://www.youtube.com/watch?v=" + _VIDEO_ID,
    "volume": 70,
    "muted": True,      # browser autoplay requires starting muted; "unmute" to hear it
    "paused": False,    # ready to play as soon as the card opens
    "last_cmd": "load",
    "cmd_seq": 0,
}


def _load() -> dict:
    db = store.load(WID, dict(_SEED))
    for k, v in _SEED.items():                          # normalize missing fields (old store)
        db.setdefault(k, v)
    db["videoId"] = _VIDEO_ID                            # fixed video: an old store never changes it
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
