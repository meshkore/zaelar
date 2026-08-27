#
# musica: face of the music connector (V2-041) + Spotify-style LISTS (V2-058, Phase 1). Hand-built SYSTEM widget,
# not generated: it DOES import core modules (connectors.music / connectors.spotify / config.credentials) because it
# runs in the server process, like the `mensajeria` owner.
#
# Two responsibilities:
#  - Spotify connection (guided flow like messaging QRs) + playback control (card buttons).
#  - Lists/recent/top tracks persisted in widget state (widgets/_data/musica/state.json).
#
# PLAYBACK = the existing connector (connectors.music.control()); never reinvent it here. Voice playback goes
# through the FlashBrain play_music tool; play_playlist/play from the widget also converge on that seam.
#
# Persistence invariant: the `yt` block (hidden YouTube audio) and lists share the SAME store. view_data composes
# {persisted db} + {live state (connected/mode/now_playing)}, so saving the compound preserves everything
# (yt + playlists + counts). The youtube_audio provider performs read-modify-write on `yt`, so respect the same
# contract: never overwrite persisted keys.
#
import re
import time
import unicodedata

from .. import store

WID = "musica"

_SEED = {"connected": False, "provider": "spotify", "can_connect": False, "own_client_id_set": False,
         "default_available": False, "redirect_uri": "", "now_playing": None}

_RECENT_CAP = 30
_TOP_CAP = 8


# Normalization helpers.
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return s.lower().strip()


def _slug(s: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", _norm(s)).strip("-")
    return base or "lista"


# Store: persisted db (yt + playlists + recent + counts + view).
def _load_db() -> dict:
    try:
        db = store.load(WID, {}) or {}
    except Exception:
        db = {}
    if not isinstance(db, dict):
        db = {}
    db.setdefault("yt", {})
    db.setdefault("playlists", [])
    db.setdefault("recent", [])
    db.setdefault("counts", {})
    db.setdefault("view", {"kind": "home", "id": ""})
    return db


def _spotify_status() -> dict:
    try:
        from connectors.spotify import auth
        return auth.status()
    except Exception:
        return {}


def _now_playing() -> "dict | None":
    """What is playing NOW, only if a Spotify account is connected. Fail-open: never breaks the card."""
    try:
        from connectors import music
        np = music.now_playing()
        if not np:
            return None
        t = np.track
        return {"playing": bool(np.playing), "device": np.device or "", "volume": np.volume,
                "title": (t.title if t else ""), "artist": (t.artist if t else ""),
                "album": (t.album if t else ""), "art": (t.art if t else "")}
    except Exception:
        return None


def _live_fields(db: dict) -> dict:
    """Live state recomputed on each read: Spotify connection + card display mode + now_playing."""
    st = _spotify_status()
    connected = bool(st.get("logged_in"))
    yt = dict(db.get("yt") or {})
    # mode = what the bar shows: spotify (remote device), youtube (hidden audio), or idle.
    mode = "spotify" if connected else ("youtube" if yt.get("videoId") else "idle")
    return {
        **_SEED,
        "connected": connected,
        "can_connect": bool(st.get("can_connect")),
        "own_client_id_set": bool(st.get("own_client_id_set")),
        "default_available": bool(st.get("default_available")),
        "redirect_uri": st.get("redirect_uri", ""),
        "now_playing": (_now_playing() if connected else None),
        "yt": yt,
        "mode": mode,
    }


def _derive_top(db: dict) -> list:
    """Top tracks are derived from playback counters (counts), descending by count."""
    counts = db.get("counts") or {}
    items = sorted(counts.values(), key=lambda c: (-int(c.get("count") or 0), _norm(c.get("title"))))
    return [dict(c) for c in items[:_TOP_CAP]]


def _compose(db: dict) -> dict:
    """Exact blob seen by the card: persisted db + live state + derived top tracks."""
    return {**db, **_live_fields(db), "top": _derive_top(db)}


def view_data(q: str = "") -> dict:
    return _compose(_load_db())


def _persist(db: dict) -> None:
    """Save the compound state, preserving yt + playlists + counts and reflecting connection; triggers SSE re-render."""
    try:
        store.save(WID, _compose(db))
    except Exception:
        pass


def _save_view() -> None:
    _persist(_load_db())


# Track / list model.
def _track_query(t: dict) -> str:
    q = (t.get("query") or "").strip()
    if q:
        return q
    parts = [t.get("title") or "", t.get("artist") or ""]
    return " ".join(p for p in parts if p).strip() or (t.get("title") or "")


def _track_from_payload(p: dict) -> "dict | None":
    """Build a track from flexible payload: {track:{...}} or {query|title[,artist,album]}."""
    src = p.get("track")
    if isinstance(src, dict):
        title = (src.get("title") or p.get("query") or "").strip()
        return {"title": title, "artist": (src.get("artist") or "").strip(),
                "album": (src.get("album") or "").strip(), "art": src.get("art") or "",
                "query": (src.get("query") or title).strip(), "uri": src.get("uri") or "",
                "videoId": src.get("videoId") or ""}
    q = (p.get("query") or (src if isinstance(src, str) else "") or p.get("title") or "").strip()
    if not q:
        return None
    title = (p.get("title") or q).strip()
    return {"title": title, "artist": (p.get("artist") or "").strip(),
            "album": (p.get("album") or "").strip(), "art": "", "query": q, "uri": "", "videoId": ""}


def _current_track(db: dict) -> "dict | None":
    """Currently playing song (Spotify or YouTube-audio), so it can be saved into a favorites list."""
    live = _live_fields(db)
    np = live.get("now_playing")
    if np and np.get("title"):
        return {"title": np.get("title") or "", "artist": np.get("artist") or "",
                "album": np.get("album") or "", "art": np.get("art") or "", "query": np.get("title") or ""}
    yt = live.get("yt") or {}
    if yt.get("videoId"):
        return {"title": yt.get("title") or "Música", "artist": "", "album": "", "art": "",
                "query": yt.get("title") or "", "videoId": yt.get("videoId")}
    return None


def _find_playlist(db: dict, ref) -> "dict | None":
    """Resuelve una referencia (id exacto o nombre en lenguaje natural) a la lista real. Nunca inventa."""
    ref = str(ref or "")
    pls = db.get("playlists") or []
    for pl in pls:                                    # id exacto
        if pl.get("id") == ref:
            return pl
    nref = _norm(ref)
    if not nref:
        return None
    for pl in pls:                                    # nombre exacto
        if _norm(pl.get("name")) == nref:
            return pl
    for pl in pls:                                    # contiene / contenido
        nn = _norm(pl.get("name"))
        if nn and (nref in nn or nn in nref):
            return pl
    return None


def _resolve_track_index(tracks: list, item) -> "int | None":
    """item = 1-based index ('2') or text matching a track title/query in the list."""
    if item is None:
        return None
    s = str(item).strip()
    if s.isdigit():
        i = int(s) - 1
        return i if 0 <= i < len(tracks) else None
    nitem = _norm(s)
    if not nitem:
        return None
    for i, t in enumerate(tracks):                    # exacto
        if nitem == _norm(t.get("title")) or nitem == _norm(t.get("query")):
            return i
    for i, t in enumerate(tracks):                    # contiene
        hay = _norm(" ".join([t.get("title") or "", t.get("artist") or "", t.get("query") or ""]))
        if nitem in hay:
            return i
    return None


def _push_recent(db: dict, t: dict) -> None:
    """Record playback: recent tracks (dedup by title+artist, capped) + counter for top tracks."""
    title = (t.get("title") or t.get("query") or "").strip()
    if not title:
        return
    artist = (t.get("artist") or "").strip()
    key = _norm(title + "|" + artist)
    rec = db.setdefault("recent", [])
    rec[:] = [x for x in rec if x.get("_k") != key]
    rec.insert(0, {"title": title, "artist": artist, "album": (t.get("album") or "").strip(),
                   "art": t.get("art") or "", "query": t.get("query") or title, "_k": key,
                   "at": int(time.time())})
    del rec[_RECENT_CAP:]
    counts = db.setdefault("counts", {})
    c = counts.get(key) or {"title": title, "artist": artist, "album": (t.get("album") or "").strip(),
                            "art": t.get("art") or "", "query": t.get("query") or title, "count": 0}
    c["count"] = int(c.get("count") or 0) + 1
    counts[key] = c


def _play_track(track: dict) -> "dict":
    """Reproduce UN track por el seam del conector (Spotify si hay cuenta, si no YouTube-audio). Fail-safe."""
    from connectors import music
    r = music.control("play", query=_track_query(track), uri=track.get("uri") or "")
    return {"ok": bool(getattr(r, "ok", False)), "message": getattr(r, "message", ""),
            "reason": getattr(r, "reason", "")}


def _find_or_create_playlist(db: dict, name: str) -> "tuple[dict, bool]":
    """Resolve a spoken list name to the real playlist, CREATING it when it does not exist (V2-384).
    Measured live: «guárdamelo en una lista que se llame Curro» answered «Hecho.» with nothing behind —
    the model gets ONE call, and demanding create_playlist + add_to_playlist as two is how that call
    resolves to nothing. Returns (playlist, created)."""
    pl = _find_playlist(db, name)
    if pl is not None:
        return pl, False
    name = (str(name or "").strip() or "Nueva lista")
    used = {x.get("id") for x in db["playlists"]}
    pid = _slug(name); base, i = pid, 2
    while pid in used:
        pid = f"{base}-{i}"; i += 1
    pl = {"id": pid, "name": name, "art": "", "tracks": []}
    db["playlists"].append(pl)
    return pl, True


# ref_index (V2-026): playlists are voice-referenceable by name.
def ref_index() -> list:
    try:
        db = _load_db()
    except Exception:
        return []
    out = []
    for pl in db.get("playlists") or []:
        n = len(pl.get("tracks") or [])
        out.append({"id": pl.get("id"), "label": pl.get("name") or pl.get("id"),
                    "field": "playlist", "hint": f"{n} canción{'es' if n != 1 else ''}"})
    return out


def apply_action(action: str, payload: dict = None) -> dict:
    p = payload or {}

    # Spotify connection, unchanged from V2-041.
    if action == "connect":
        cid = (p.get("client_id") or "").strip()
        if cid:
            try:
                from config import credentials
                credentials.set_key("SPOTIFY_CLIENT_ID", cid)
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"credential_store:{e}"[:120]}
        try:
            from connectors.spotify import auth
            res = auth.begin_login()          # {ok, url} or {ok:False, error:'no_client_id'}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:120]}
        if not res.get("ok") and res.get("error") == "no_client_id":
            res["need_client_id"] = True      # widget shows the advanced field
        return res

    if action == "disconnect":
        try:
            from connectors.spotify import auth
            auth.disconnect()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:120]}
        _save_view()
        return {"ok": True}

    if action == "refresh":
        _save_view()
        return {"ok": True}

    # Lists (V2-058, Phase 1).
    if action == "create_playlist":
        name = (p.get("name") or p.get("playlist") or "").strip() or "Nueva lista"
        db = _load_db()
        used = {pl.get("id") for pl in db["playlists"]}
        pid = _slug(name); base, i = pid, 2
        while pid in used:
            pid = f"{base}-{i}"; i += 1
        db["playlists"].append({"id": pid, "name": name, "art": "", "tracks": []})
        db["view"] = {"kind": "playlist", "id": pid}          # screen adapts to the new playlist
        _persist(db)
        return {"ok": True, "playlist": pid, "name": name}

    if action == "add_to_playlist":
        db = _load_db()
        ref = p.get("playlist") or p.get("id") or p.get("name")
        if not str(ref or "").strip():
            return {"ok": False, "error": "playlist_not_found", "playlist": ref}
        tr = _track_from_payload(p)
        if not tr:
            # No explicit track → the one PLAYING NOW («guárdame esta en…»), which is what the spoken form
            # almost always means. Resolved BEFORE creating anything: with nothing playing and no track,
            # creating an empty list here would turn a failed save into silent clutter.
            tr = _current_track(db)
            if not tr:
                return {"ok": False, "error": "nothing_playing",
                        "message": "No suena nada ahora y no me has dicho qué canción añadir."}
        pl, created = _find_or_create_playlist(db, ref)      # V2-384: one call is all the model gets
        dupe_key = _norm((tr.get("title") or "") + "|" + (tr.get("artist") or ""))
        tracks = pl.setdefault("tracks", [])
        if not any(_norm((t.get("title") or "") + "|" + (t.get("artist") or "")) == dupe_key for t in tracks):
            tracks.append(tr)
        db["view"] = {"kind": "playlist", "id": pl["id"]}
        _persist(db)
        return {"ok": True, "playlist": pl["id"], "name": pl.get("name"), "created": created,
                "track": tr.get("title"), "count": len(tracks)}

    if action == "remove_from_playlist":
        db = _load_db()
        pl = _find_playlist(db, p.get("playlist") or p.get("id"))
        if pl is None:
            return {"ok": False, "error": "playlist_not_found", "playlist": p.get("playlist")}
        tracks = pl.get("tracks") or []
        idx = _resolve_track_index(tracks, p.get("item"))
        if idx is None:
            return {"ok": False, "error": "track_not_found", "item": p.get("item")}
        removed = tracks.pop(idx)
        db["view"] = {"kind": "playlist", "id": pl["id"]}
        _persist(db)
        return {"ok": True, "playlist": pl["id"], "removed": removed.get("title")}

    if action == "favorite_current":
        db = _load_db()
        cur = _current_track(db)
        if not cur:
            return {"ok": False, "error": "nothing_playing"}
        # Plain "Favoritos": the old hardcoded "Favoritos de Manolo" was a demo leftover shipped to every
        # operator. No dual lineage on upgrade: _find_playlist matches by containment, so an existing
        # "Favoritos de Manolo" list keeps receiving the favorites under its old name. And since V2-384 the
        # target can be a NAMED list («guárdamela en Curro») — found or created, same seam as add_to_playlist.
        fav_name = (p.get("playlist") or p.get("name") or "").strip() or "Favoritos"
        pl, _created = _find_or_create_playlist(db, fav_name)
        tracks = pl.setdefault("tracks", [])
        key = _norm((cur.get("title") or "") + "|" + (cur.get("artist") or ""))
        if not any(_norm((t.get("title") or "") + "|" + (t.get("artist") or "")) == key for t in tracks):
            tracks.append(cur)
        db["view"] = {"kind": "playlist", "id": pl["id"]}
        _persist(db)
        return {"ok": True, "playlist": pl["id"], "track": cur.get("title")}

    if action == "play_playlist":
        db = _load_db()
        pl = _find_playlist(db, p.get("playlist") or p.get("id"))
        if pl is None:
            return {"ok": False, "error": "playlist_not_found", "playlist": p.get("playlist")}
        tracks = pl.get("tracks") or []
        if not tracks:
            return {"ok": False, "error": "empty_playlist", "playlist": pl["id"]}
        try:
            r = _play_track(tracks[0])                          # first track starts now
            from connectors import music
            for t in tracks[1:]:                                # rest goes to queue (V2-047 F4)
                try:
                    music.control("queue", query=_track_query(t), uri=t.get("uri") or "")
                except Exception:
                    pass
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:120]}
        _push_recent(db, tracks[0])
        db["view"] = {"kind": "playlist", "id": pl["id"]}
        _persist(db)
        return {"ok": r.get("ok", False), "message": r.get("message", ""), "playlist": pl["id"]}

    if action == "open_view":
        kind = (p.get("kind") or "home").strip().lower()
        if kind not in ("home", "playlist", "album", "artist", "nowplaying"):
            kind = "home"
        db = _load_db()
        vid = str(p.get("id") or "").strip()
        if kind == "playlist" and vid:
            pl = _find_playlist(db, vid)                        # name -> real id
            vid = pl["id"] if pl else vid
        db["view"] = {"kind": kind, "id": vid}
        _persist(db)
        return {"ok": True, "view": db["view"]}

    if action == "back":
        db = _load_db()
        db["view"] = {"kind": "home", "id": ""}
        _persist(db)
        return {"ok": True, "view": db["view"]}

    # Playback control from card buttons. Voice uses play_music. Converges on the same seam.
    # `ended` (V2-047 F4): fired by the widget when the song ends; the seam advances the queue.
    if action in ("play", "pause", "resume", "next", "previous", "volume_up", "volume_down", "set_volume",
                  "queue", "ended"):
        try:
            from connectors import music
            query = str(p.get("query") or "")
            r = music.control(action, query=query, percent=int(p.get("level") or 0))
            ok = bool(getattr(r, "ok", False))
            # Playing a standalone track from the card (recent/top/list row) feeds recent + top tracks. Voice
            # (play_music) goes through another path and does not pass here (Phase 1).
            if action == "play" and ok and query:
                db = _load_db()
                _push_recent(db, {"title": query, "query": query})
                _persist(db)
            else:
                _save_view()
            return {"ok": ok, "message": getattr(r, "message", ""), "reason": getattr(r, "reason", "")}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:120]}

    return {"ok": False, "error": "unknown_action", "action": action}
