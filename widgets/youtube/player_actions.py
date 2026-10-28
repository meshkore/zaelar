"""What each PLAYBACK action does — play, pause, skip, sound, captions, close (split from `actions.py`)."""
from __future__ import annotations

from . import data as _d
from . import result_refs as _rr
from .actions import _a_play_result


def _a_play_item(action, p, db) -> dict:
    lst = db.get("list") or []
    ref = next((p.get(k) for k in ("item", "n", "query") if p.get(k) is not None), None)
    if not lst and db.get("search_results"):
        return _a_play_result(action, {"item": ref}, db)   # «play the second one» over Home's band (V2-781)
    idx = _d._resolve_item(lst, ref)
    if idx is None and not str(ref or "").strip().isdigit() \
            and _rr.resolve(db.get("search_results") or [], ref) is not None:
        return _a_play_result(action, {"item": ref}, db)   # a band row he named, the queue holding others
    if idx is None:
        return {"ok": False, "error": "item_not_found", "item": p.get("item"),
                "message": "No encuentro ese vídeo en la lista."}
    return _d._play_pos(db, idx, "play_item")


def _a_previous(action, p, db) -> dict:
    lst = db.get("list") or []
    pos = int(db.get("pos", -1))
    if lst and 0 < pos <= len(lst):
        return _d._play_pos(db, pos - 1, "previous")
    if db.get("videoId"):                           # at the start (or off-list): back = restart, like YouTube
        db["paused"] = False
        return _d._bump(db, "restart")
    return {"ok": False, "error": "no_video", "message": "No hay nada sonando."}


def _a_ended(action, p, db) -> dict:
    # Fired by the widget when the video reaches the end (onStateChange=0): one after another, by itself.
    lst = db.get("list") or []
    nxt = int(db.get("pos", -1)) + 1
    if 0 <= nxt < len(lst):
        # V2-755: automatic, so it does NOT move his view — see `_goto`.
        return _d._play_pos(db, nxt, "next", watch=False)
    db["paused"] = True                             # end of the list: stop honestly, do not loop
    return _d._bump(db, "ended")


def _a_play(action, p, db) -> dict:
    if not db.get("videoId"):
        # Empty player + a list waiting: "play" means start the list (add never autoplays, so this is the
        # voice path that actually launches a freshly built queue).
        lst = db.get("list") or []
        if lst:
            nxt = int(db.get("pos", -1)) + 1
            return _d._play_pos(db, nxt if 0 <= nxt < len(lst) else 0, "play_item")
        return {"ok": False, "error": "no_video", "message": "No hay ningún vídeo cargado ni lista."}
    db["paused"] = False
    return _d._bump(db, "play")


def _a_player_error(action, p, db) -> dict:
    # V2-401 — widget.js reports onError (untrusted, crosses postMessage). V2-634 — a FATAL code is
    # ACTED on: blocklist + swap of our own pick, or the honest message for a pasted link — the whole
    # behavior lives in `availability.on_player_error`, beside the blocklist it maintains.
    code = str(p.get("code") or "unknown")[:40]
    dead = str(p.get("videoId") or db.get("videoId") or "")[:20]
    verdict = _d._avail.on_player_error(db, code, dead)
    if verdict == "stale":
        _d.store.save(_d.WID, db)
        return {"ok": True, "cmd": "player_error", "stale": True}
    if verdict is None:
        db["player_error"] = code
    out = _d._bump(db, "player_error")
    tell = _d._avail.tell_for(db) if verdict == "handled" else ""
    if tell and isinstance(out, dict):
        out["tell"] = tell          # said only if an agent order is being contradicted (`widgets/late_report.py`)
    return out


def _a_pause(action, p, db) -> dict:
    db["paused"] = True
    return _d._bump(db, "pause")


def _a_mute(action, p, db) -> dict:
    db["muted"] = True
    _d._sound.kept_mute(db, True)                  # V2-791: his mute survives the next video
    return _d._bump(db, "mute")


def _a_unmute(action, p, db) -> dict:
    # V2-791 — this is what was ORDERED; whether the browser let the player obey is the player's own report
    # (`player_audio` → `audio_blocked`), never assumed from here.
    db["muted"] = False
    _d._sound.kept_mute(db, False)
    return _d._bump(db, "unmute")


def _a_captions_on(action, p, db) -> dict:
    # V2-590 — «quita los subtítulos» was narrated as impossible («solo puedes quitarlos desde los
    # controles», measured live): the capability had no declared action, and an undeclared capability
    # is one the model narrates (V2-540). The widget toggles the IFrame API captions module.
    db["captions"] = True
    return _d._bump(db, "captions_on")


def _a_captions_off(action, p, db) -> dict:
    db["captions"] = False
    return _d._bump(db, "captions_off")


def _a_volume_up(action, p, db) -> dict:
    db["volume"] = min(100, int(db.get("volume") or 70) + 15)
    db["muted"] = False
    _d._sound.kept_mute(db, False)
    return _d._bump(db, "volume_up")


def _a_volume_down(action, p, db) -> dict:
    db["volume"] = max(0, int(db.get("volume") or 70) - 15)
    return _d._bump(db, "volume_down")


def _a_set_volume(action, p, db) -> dict:
    try:
        lvl = int(p.get("level"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_level", "message": "Dime un nivel entre 0 y 100."}
    db["volume"] = max(0, min(100, lvl))
    db["muted"] = db["volume"] == 0
    _d._sound.kept_mute(db, db["muted"])
    return _d._bump(db, "set_volume")


def _a_restart(action, p, db) -> dict:
    db["paused"] = False
    return _d._bump(db, "restart")


def _a_close(action, p, db) -> dict:
    # Empty the video → widget.js detects videoId="" and REBUILDS the card without <iframe>: the video REALLY
    # stops playing in the browser (not just data deletion), and the card moves to empty state.
    db["videoId"] = ""
    db["title"] = ""
    db["url"] = ""
    db["channel"] = ""
    db["published"] = ""
    db["latest"] = False
    db["paused"] = True
    db["muted"] = True
    db["pos"] = -1                                  # V2-366: close closes the VIDEO; the list survives
    return _d._bump(db, "close")
