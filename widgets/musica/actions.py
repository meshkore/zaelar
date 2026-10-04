"""What each music action does, one function per action; `data.ACTIONS` maps the names to them (V2-778 F1-12,
2026-10-01).

Moved out of `widgets/musica/data.py`'s `apply_action` if-chain with no behaviour change: each body is the branch
it was, and every module-level name of `data` it reads is read through it (`_d.<name>`), so a patch on `data`
still governs every call.
"""
from __future__ import annotations

from . import data as _d


def _a_refresh(action: str, p: dict) -> dict:
    _d._save_view()
    return {"ok": True}


# V2-629 — lazy, cached cover-art lookup. The widget calls this ONCE per (title, artist) it renders
# without art (recent/top/playlist rows the card, not the connector, is showing); never on the play
# critical path, and never twice for the same song thanks to `_enrich_art`'s cache.
def _a_enrich_art(action: str, p: dict) -> dict:
    title = (p.get("title") or "").strip()
    artist = (p.get("artist") or "").strip()
    if not title:
        return {"ok": False, "error": "missing_title"}
    db = _d._load_db()
    art, album = _d._enrich_art(db, title, artist)
    _d._persist(db)
    return {"ok": bool(art), "art": art, "album": album}


# Lists (V2-058, Phase 1).
def _a_create_playlist(action: str, p: dict) -> dict:
    name = (p.get("name") or p.get("playlist") or "").strip() or "Nueva lista"
    db = _d._load_db()
    used = {pl.get("id") for pl in db["playlists"]}
    pid = _d._slug(name); base, i = pid, 2
    while pid in used:
        pid = f"{base}-{i}"; i += 1
    db["playlists"].append({"id": pid, "name": name, "art": "", "tracks": []})
    db["view"] = {"kind": "playlist", "id": pid}          # screen adapts to the new playlist
    _d._persist(db)
    out = {"ok": True, "playlist": pid, "name": name, "empty": True}
    # Teach through the seam (measured 2026-08-27: «save WHAT IS PLAYING in a list called Curro» ended as an
    # EMPTY list — the model picks create_playlist by lexical match and stops). The model reads this
    # result and the channel runs several data-ops per turn, so the hint lets it finish the job; with
    # nothing playing, an empty list is the whole request and no hint is added.
    if _d._current_track(db):
        out["hint"] = ("la lista está VACÍA y ahora mismo suena algo: si el operador quería guardarlo, "
                       "llama a add_to_playlist {playlist: '" + name + "'} sin canción y se añade la que suena")
    return out


def _a_add_to_playlist(action: str, p: dict) -> dict:
    db = _d._load_db()
    ref = p.get("playlist") or p.get("id") or p.get("name")
    if not str(ref or "").strip():
        return {"ok": False, "error": "playlist_not_found", "playlist": ref}
    tr = _d._track_from_payload(p)
    if not tr:
        # No explicit track → the one PLAYING NOW («save this one in…»), which is what the spoken form
        # almost always means. Resolved BEFORE creating anything: with nothing playing and no track,
        # creating an empty list here would turn a failed save into silent clutter.
        tr = _d._current_track(db)
        if not tr:
            return {"ok": False, "error": "nothing_playing",
                    "message": "No suena nada ahora y no me has dicho qué canción añadir."}
    pl, created = _d._find_or_create_playlist(db, ref)      # V2-384: one call is all the model gets
    dupe_key = _d._norm((tr.get("title") or "") + "|" + (tr.get("artist") or ""))
    tracks = pl.setdefault("tracks", [])
    if not any(_d._norm((t.get("title") or "") + "|" + (t.get("artist") or "")) == dupe_key for t in tracks):
        tracks.append(tr)
    db["view"] = {"kind": "playlist", "id": pl["id"]}
    _d._persist(db)
    return {"ok": True, "playlist": pl["id"], "name": pl.get("name"), "created": created,
            "track": tr.get("title"), "count": len(tracks)}


def _a_remove_from_playlist(action: str, p: dict) -> dict:
    db = _d._load_db()
    pl = _d._find_playlist(db, p.get("playlist") or p.get("id"))
    if pl is None:
        return {"ok": False, "error": "playlist_not_found", "playlist": p.get("playlist")}
    tracks = pl.get("tracks") or []
    idx = _d._resolve_track_index(tracks, p.get("item"))
    if idx is None:
        return {"ok": False, "error": "track_not_found", "item": p.get("item")}
    removed = tracks.pop(idx)
    db["view"] = {"kind": "playlist", "id": pl["id"]}
    _d._persist(db)
    return {"ok": True, "playlist": pl["id"], "removed": removed.get("title")}


def _a_favorite_current(action: str, p: dict) -> dict:
    db = _d._load_db()
    cur = _d._current_track(db)
    if not cur:
        return {"ok": False, "error": "nothing_playing"}
    # Plain "Favoritos": the old hardcoded "Favoritos de Manolo" was a demo leftover shipped to every
    # operator. No dual lineage on upgrade: _find_playlist matches by containment, so an existing
    # "Favoritos de Manolo" list keeps receiving the favorites under its old name. And since V2-384 the
    # target can be a NAMED list («save it in Curro») — found or created, same seam as add_to_playlist.
    fav_name = (p.get("playlist") or p.get("name") or "").strip() or "Favoritos"
    pl, _created = _d._find_or_create_playlist(db, fav_name)
    tracks = pl.setdefault("tracks", [])
    key = _d._norm((cur.get("title") or "") + "|" + (cur.get("artist") or ""))
    if not any(_d._norm((t.get("title") or "") + "|" + (t.get("artist") or "")) == key for t in tracks):
        tracks.append(cur)
    db["view"] = {"kind": "playlist", "id": pl["id"]}
    _d._persist(db)
    return {"ok": True, "playlist": pl["id"], "track": cur.get("title")}


def _a_play_playlist(action: str, p: dict) -> dict:
    db = _d._load_db()
    ref = p.get("playlist") or p.get("id")
    pl = _d._find_playlist(db, ref) or _d._closest_playlist(db, ref)
    if pl is None:
        names = [str(x.get("name") or x.get("id") or "").strip() for x in (db.get("playlists") or [])]
        names = [n for n in names if n]
        # The spoken correction reads `message` (data_ops.report_failure), so the refusal must be a
        # sentence naming what exists (V2-463) — the bare code was read aloud as «playlistnotfound».
        msg = (f"No encuentro ninguna lista que se llame «{str(ref or '').strip()}». "
               + (f"Tienes: {', '.join(names[:6])}." if names else "Todavía no hay ninguna lista guardada."))
        return {"ok": False, "error": "playlist_not_found", "playlist": ref, "message": msg}
    tracks = pl.get("tracks") or []
    if not tracks:
        return {"ok": False, "error": "empty_playlist", "playlist": pl["id"]}
    pl_id = pl["id"]
    first_local = _d._local.is_local(tracks[0])
    try:
        # A local first track mutates THIS snapshot (local state has no other writer); a streamed one
        # goes through the connector, which loads/saves the store ITSELF — so it gets no db.
        r = _d._play_track(tracks[0], db if first_local else None)   # first track starts now
        from connectors import music
        for t in tracks[1:]:                                # rest goes to queue (V2-047 F4)
            if _d._local.is_local(t):
                continue        # the connector queue holds query STRINGS it re-resolves; a file
                                # has nothing to re-resolve, so queueing it would silently drop it
            try:
                music.control("queue", query=_d._track_query(t), uri=t.get("uri") or "")
            except Exception:
                pass
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:120]}
    if not first_local:
        # V2-650: the connector just wrote yt.videoId + the queue into the store while we held this
        # snapshot; persisting the snapshot would erase the playback it started (measured live
        # 2026-09-10: «reproduce la lista» resolved True Blue, then wrote yt={} back — silence).
        db = _d._load_db()
    _d._push_recent(db, tracks[0])
    db["view"] = {"kind": "playlist", "id": pl_id}
    _d._persist(db)
    return {"ok": r.get("ok", False), "message": r.get("message", ""), "playlist": pl_id}


def _a_open_view(action: str, p: dict) -> dict:
    kind = (p.get("kind") or "home").strip().lower()
    # V2-717 — `home` is the ADAPTIVE face (the song when something sounds, the library when not) and the
    # two explicit ones exist so a click or a sentence can cross over and STAY there. «nowplaying» was
    # the spelling declared in V2-058 and never implemented; it is kept as an alias so an old data-op,
    # or a model that learned it, lands on the screen it was always asking for.
    if kind in ("nowplaying", "now_playing", "song", "track"):
        kind = "now"
    if kind not in ("home", "library", "now", "playlist", "connect"):
        kind = "home"
    db = _d._load_db()
    vid = str(p.get("id") or "").strip()
    if kind == "playlist" and vid:
        pl = _d._find_playlist(db, vid)                        # name -> actual ID
        vid = pl["id"] if pl else vid
    db["view"] = {"kind": kind, "id": vid}
    _d._persist(db)
    return {"ok": True, "view": db["view"]}


def _a_back(action: str, p: dict) -> dict:
    db = _d._load_db()
    db["view"] = {"kind": "home", "id": ""}
    _d._persist(db)
    return {"ok": True, "view": db["view"]}


# V2-638 — a track that is a FILE we hold. Mixed lists (a Spotify link, a YouTube link, a local file)
# need no new schema: a local track is just `uri = "local:<rel>"`, so playlists, Recent and Top keep
# working untouched.
def _a_play_local(action: str, p: dict) -> dict:
    db = _d._load_db()
    t = _d._local.track_from_library(str(p.get("path") or p.get("file") or ""))
    if t is None:
        return {"ok": False, "error": "no encuentro ese audio en tu biblioteca (o no se puede reproducir)"}
    r = _d._play_track(t, db)
    if r.get("ok"):
        _d._push_recent(db, t)
    _d._persist(db)
    return r


# V2-717 — move the playhead, by voice or by dragging the card's own bar.
#
# Two of the three sources play INSIDE the operator's page (the hidden YouTube iframe and a local file's
# <audio>), and the only clock that knows where the song is lives there. So for those this writes an
# INTENTION into the store — a numbered command the widget applies on the next render — instead of
# pretending the server can move a playhead it has never held. Spotify plays on a device somewhere else
# and is the opposite case: it is a round trip through the connector.
def _a_seek(action: str, p: dict) -> dict:
    to, by = p.get("to"), p.get("by")
    if to is None and by is None:                       # «adelanta» with no number means a nudge forward
        to, by = None, p.get("seconds", 30)
    try:
        secs = float(to if to is not None else by)
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_position", "message": "Dime a qué punto de la canción voy."}
    relative = to is None
    db = _d._load_db()
    loc = dict(db.get("local") or {})
    if loc.get("src"):
        prev = dict(loc.get("seek") or {})
        cmd = {"n": int(prev.get("n") or 0) + 1}
        cmd["by" if relative else "to"] = secs if relative else max(0.0, secs)
        loc["seek"] = cmd
        db["local"] = loc
        _d._persist(db)
        return {"ok": True, "message": "", "reason": ""}
    try:
        from connectors import music
        r = music.control("seek", seconds=secs, relative=relative)
        _d._save_view()
        return {"ok": bool(getattr(r, "ok", False)), "message": getattr(r, "message", ""),
                "reason": getattr(r, "reason", "")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:120]}


# Playback control from card buttons. Voice uses play_music. Converges on the same seam.
# `ended` (V2-047 F4): fired by the widget when the song ends; the seam advances the queue.
def _a_playback(action: str, p: dict) -> dict:
    if action in ("ended", "next") and (_d._load_db().get("local") or {}).get("src"):
        # A local file finished (or was skipped): it is not in the connector's queue — that holds query
        # strings it re-resolves — so clear the bar here instead of asking the connector to advance past
        # something it never knew about.
        _db = _d._load_db()
        _d._local.stop(_db)
        _d._persist(_db)
        return {"ok": True, "message": "", "reason": ""}
    try:
        from connectors import music
        query = str(p.get("query") or "")
        r = music.control(action, query=query, percent=int(p.get("level") or 0))
        ok = bool(getattr(r, "ok", False))
        # Playing a standalone track from the card (recent/top/list row) feeds recent + top tracks. Voice
        # (play_music) goes through another path and does not pass here (Phase 1).
        if action == "play" and ok and query:
            db = _d._load_db()
            _d._push_recent(db, _d._track_from_resolved(query, getattr(r, "track", None)))
            _d._persist(db)
        else:
            _d._save_view()
        return {"ok": ok, "message": getattr(r, "message", ""), "reason": getattr(r, "reason", "")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:120]}
