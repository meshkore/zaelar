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
import urllib.parse
import urllib.request

from .. import store
from . import local_audio as _local   # V2-638: a track that is a FILE in the agent's own library

WID = "musica"

_SEED = {"connected": False, "provider": "spotify", "can_connect": False, "own_client_id_set": False,
         "default_available": False, "redirect_uri": "", "now_playing": None}

_RECENT_CAP = 30
_TOP_CAP = 8

# Cover-art ENRICHMENT (V2-629): a track with no art yet (typed into a list, imported, or a legacy row from
# before the connector started giving out YouTube thumbnails for free) gets looked up ONCE against the iTunes
# Search API — free, no key, no auth — and the result is cached forever by (artist, title) so the SAME song
# never pays a second network round trip, on this machine or the next request. `_ART_MISS_COOLDOWN_S` bounds
# only the NEGATIVE case (nothing found): a transient API hiccup or a temporarily-misspelled title should not
# become a permanent "no art" verdict, but a song that genuinely is not in iTunes' catalog should not be
# re-queried on every render either.
_ART_MISS_COOLDOWN_S = 14 * 24 * 3600
_ART_CACHE_CAP = 600


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
    db.setdefault("art_cache", {})
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
    loc = _local.display(db)
    # V2-638 — a file we hold is the third thing the bar can be showing. It wins over the connector
    # modes because it is the one playing IN the page: `local_audio.play` clears the yt block, so the
    # two can never be set at once and the order here only decides what an inconsistent db shows.
    mode = "local" if loc else ("spotify" if connected else ("youtube" if yt.get("videoId") else "idle"))
    return {
        **_SEED,
        "connected": connected,
        "can_connect": bool(st.get("can_connect")),
        "own_client_id_set": bool(st.get("own_client_id_set")),
        "default_available": bool(st.get("default_available")),
        "redirect_uri": st.get("redirect_uri", ""),
        "now_playing": (_now_playing() if connected else None),
        "yt": _yt_display(yt),
        "local": loc,
        "mode": mode,
    }


def _derive_top(db: dict) -> list:
    """Top tracks are derived from playback counters (counts), descending by count."""
    counts = db.get("counts") or {}
    items = sorted(counts.values(), key=lambda c: (-int(c.get("count") or 0), _norm(c.get("title"))))
    return [dict(c) for c in items[:_TOP_CAP]]


def _compose(db: dict) -> dict:
    """Exact blob seen by the card: persisted db + live state + derived top tracks + whether the track
    playing right now is already one of the operator's favorites (the heart's filled state, V2-629)."""
    live = _live_fields(db)
    return {**db, **live, "top": _derive_top(db),
            "fav_current": _fav_playlist_match(db, _current_track_from_live(live))}


def view_data(q: str = "") -> dict:
    d = _compose(_load_db())
    # `art_cache` (V2-629) is server bookkeeping — up to 600 tiny entries the card never reads — so it
    # rides along in `_compose`'s return ONLY because `_persist` reuses that same function to write the
    # disk file back whole (see its docstring): stripping it THERE would delete the cache on the next
    # save. Stripped here instead, where it only shrinks what actually crosses the wire.
    d.pop("art_cache", None)
    return d


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


_ARTIST_TITLE_SEP = re.compile(r"\s+[-–—:]\s+")   # "Artist - Title" / "Artist – Title" / "Artist: Title"


def _split_artist_title(text: str) -> "tuple[str, str]":
    """Best-effort split of a combined search string into (artist, title), on an EXPLICIT delimiter only.
    Plain concatenation ('Madonna Papa Don't Preach', no separator) is left untouched — there is no music
    metadata source here to guess the boundary from, and a wrong guess would be worse than none."""
    parts = _ARTIST_TITLE_SEP.split(text, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return "", text.strip()


# YouTube upload titles carry boilerplate no album ever had ("(Official Video)", "[Lyric Video]"…). Stripped
# for DISPLAY ONLY — the STORED title never changes, so this stays reversible and the no-restart guard
# (V2-047 F5, which compares queries against the stored `yt.query`) is untouched. Only a KNOWN, closed set of
# upload tags is removed, applied repeatedly because an upload sometimes stacks two ("Song (Official Video)
# (4K)") — never a guess, the same discipline `_split_artist_title` follows: recognize, don't invent.
_YT_TAG_RE = re.compile(
    r"\s*[\(\[]\s*(?:official\s*(?:music\s*)?(?:video|audio|lyric\s*video)?|lyrics?(?:\s*video)?|"
    r"audio\s*(?:only)?|visualizer|hq|hd|4k|remaster(?:ed)?(?:\s*\d{2,4})?)\s*[\)\]]\s*$",
    re.IGNORECASE,
)


def _clean_yt_title(title: str) -> str:
    t = str(title or "").strip()
    seen = set()
    while t and t not in seen:
        seen.add(t)
        stripped = _YT_TAG_RE.sub("", t).strip(" -–—")
        if not stripped:                      # never strip a title down to nothing
            break
        t = stripped
    return t or str(title or "").strip()


def _yt_display(yt: dict) -> dict:
    """The `yt` block reshaped for what the card SHOWS: upload boilerplate stripped from the raw video title,
    and an artist split off an explicit 'Artist - Title' delimiter when the connector could not name one
    separately (YouTube never does — Spotify already gives artist/title apart). Never mutates the stored
    block: all the OTHER fields (`videoId`/`cmd_seq`/`paused`/`volume`/`queue`) pass through byte-identical,
    which is what `widget.js::syncYtPlayer`'s equality checks depend on."""
    if not yt or not yt.get("videoId"):
        return yt or {}
    out = dict(yt)
    title = _clean_yt_title(yt.get("title"))
    artist, stripped = _split_artist_title(title)
    out["title"] = stripped if artist else title
    if artist:
        out["artist"] = artist
    return out


def _fav_playlist_match(db: dict, track: "dict | None") -> bool:
    """Whether `track` is already saved in a 'Favoritos'-shaped list — the SAME loose contains-match
    `favorite_current` uses to find its own target list, so the heart's filled state and what tapping it
    again would actually do never disagree."""
    if not track:
        return False
    key = _norm((track.get("title") or "") + "|" + (track.get("artist") or ""))
    if not key or key == "|":
        return False
    for pl in db.get("playlists") or []:
        if "favorit" not in _norm(pl.get("name")):
            continue
        for t in pl.get("tracks") or []:
            if _norm((t.get("title") or "") + "|" + (t.get("artist") or "")) == key:
                return True
    return False


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
    artist = (p.get("artist") or "").strip()
    if not artist and not p.get("title"):          # a bare `query` — try the explicit-delimiter split
        guessed_artist, guessed_title = _split_artist_title(q)
        if guessed_artist:
            artist, title = guessed_artist, guessed_title
    return {"title": title, "artist": artist,
            "album": (p.get("album") or "").strip(), "art": "", "query": q, "uri": "", "videoId": ""}


def _current_track_from_live(live: dict) -> "dict | None":
    """Currently playing song (Spotify or YouTube-audio), so it can be saved into a favorites list. Takes
    the already-composed LIVE state (`_live_fields`'s return) so a caller who has it — `_compose`, on
    every render — need not pay for `_spotify_status()` a second time."""
    np = live.get("now_playing")
    if np and np.get("title"):
        return {"title": np.get("title") or "", "artist": np.get("artist") or "",
                "album": np.get("album") or "", "art": np.get("art") or "", "query": np.get("title") or ""}
    yt = live.get("yt") or {}          # already DISPLAY-shaped (V2-629): clean title, split artist, free art
    if yt.get("videoId"):
        return {"title": yt.get("title") or "Música", "artist": yt.get("artist") or "", "album": "",
                "art": yt.get("art") or "", "query": yt.get("title") or "", "videoId": yt.get("videoId")}
    return None


def _current_track(db: dict) -> "dict | None":
    return _current_track_from_live(_live_fields(db))


def _find_playlist(db: dict, ref) -> "dict | None":
    """Resolves a reference (exact ID or natural-language name) to the actual list. Never invents one."""
    ref = str(ref or "")
    pls = db.get("playlists") or []
    for pl in pls:                                    # exact ID
        if pl.get("id") == ref:
            return pl
    nref = _norm(ref)
    if not nref:
        return None
    for pl in pls:                                    # exact name
        if _norm(pl.get("name")) == nref:
            return pl
    for pl in pls:                                    # contains / contained in
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
    for i, t in enumerate(tracks):                    # exact match
        if nitem == _norm(t.get("title")) or nitem == _norm(t.get("query")):
            return i
    for i, t in enumerate(tracks):                    # contains
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


def _play_track(track: dict, db: "dict | None" = None) -> "dict":
    """Plays ONE track. A `local:` uri is a file WE hold and plays in the page (V2-638); everything else goes
    through the connector seam (Spotify if there is an account, otherwise YouTube-audio). Fail-safe.

    The local branch needs the db because that is where the player state lives, so callers that have one pass
    it; a caller without one keeps the old behaviour and a local track simply falls through to the connector,
    which refuses it honestly rather than pretending."""
    if db is not None and _local.is_local(track):
        return _local.play(db, track)
    from connectors import music
    r = music.control("play", query=_track_query(track), uri=track.get("uri") or "")
    return {"ok": bool(getattr(r, "ok", False)), "message": getattr(r, "message", ""),
            "reason": getattr(r, "reason", "")}


def _track_from_resolved(query: str, track) -> dict:
    """What actually gets remembered in Recent/Top when the card plays a bare query: the RESOLVED provider
    `Track` (real title, artist, album and — since V2-629 — free cover art) when the connector found one,
    the operator's own words otherwise. Before this, `_push_recent` stored exactly the spoken/typed query
    forever, so Home kept showing the raw search string even after the connector had already resolved a
    clean title and free YouTube-thumbnail art for it."""
    title = getattr(track, "title", "") if track is not None else ""
    if not title:
        return {"title": query, "query": query}
    clean = _clean_yt_title(title)
    artist = (getattr(track, "artist", "") or "").strip()
    if not artist:                            # YouTube never splits artist/title; Spotify already does
        guessed_artist, guessed_title = _split_artist_title(clean)
        if guessed_artist:
            artist, clean = guessed_artist, guessed_title
    return {"title": clean, "artist": artist, "album": (getattr(track, "album", "") or "").strip(),
            "art": getattr(track, "art", "") or "", "query": query,
            "uri": getattr(track, "uri", "") or "", "videoId": getattr(track, "id", "") or ""}


# ── Cover-art ENRICHMENT for tracks the connector never resolved (V2-629) ────────────────────────────────
# A track typed straight into a list (`add_to_playlist {title, artist}`, no `query`), or a legacy row from
# before the connector started giving out YouTube thumbnails, has no art and never will on its own. This is
# the SLOW, cached path the widget asks for lazily, on demand, once per song — never on the play critical
# path (`_track_from_resolved` above already covers the fast, zero-cost case for anything actually played
# through YouTube-audio).
def _art_cache_key(title: str, artist: str) -> str:
    return _norm((title or "") + "|" + (artist or ""))


def _itunes_lookup(title: str, artist: str) -> "tuple[str, str]":
    """(art_url, album) from the iTunes Search API — free, no key, no auth. Best-effort, fail-open: a network
    hiccup or a song iTunes does not carry must never break the widget, it just stays without art. The
    100x100 thumbnail iTunes returns by default is upsized to 600x600 by rewriting that URL segment — a
    documented trick, the SAME single request, no second endpoint."""
    import json
    term = " ".join(p for p in (artist, title) if p).strip()
    if not term:
        return "", ""
    try:
        url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(
            {"term": term, "entity": "song", "limit": 1})
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = json.loads(urllib.request.urlopen(req, timeout=5).read().decode("utf-8", "ignore"))
    except Exception:
        return "", ""
    results = data.get("results") or []
    if not results:
        return "", ""
    hit = results[0]
    art = str(hit.get("artworkUrl100") or "").replace("100x100bb", "600x600bb")
    return art, str(hit.get("collectionName") or "").strip()


def _backfill_art(db: dict, key: str, art: str, album: str) -> None:
    """One enrichment lights up the song wherever it ALREADY appears — Home's Recent/Top and any list it was
    saved into — not only the single row that happened to ask first."""
    def matches(t: dict) -> bool:
        return _art_cache_key(t.get("title") or t.get("query") or "", t.get("artist") or "") == key

    for t in db.get("recent") or []:
        if matches(t) and not t.get("art"):
            t["art"] = art
            if album and not t.get("album"):
                t["album"] = album
    for c in (db.get("counts") or {}).values():
        if matches(c) and not c.get("art"):
            c["art"] = art
            if album and not c.get("album"):
                c["album"] = album
    for pl in db.get("playlists") or []:
        for t in pl.get("tracks") or []:
            if matches(t) and not t.get("art"):
                t["art"] = art
                if album and not t.get("album"):
                    t["album"] = album


def _enrich_art(db: dict, title: str, artist: str) -> "tuple[str, str]":
    """Cached iTunes lookup: a HIT is cached forever (an album's art does not change); a MISS is cached only
    for `_ART_MISS_COOLDOWN_S` — a transient API hiccup, or a title that reads oddly, should not become a
    permanent "no art" verdict, but a song genuinely absent from iTunes' catalog should not be re-queried on
    every render either."""
    key = _art_cache_key(title, artist)
    if not key or key == "|":
        return "", ""
    cache = db.setdefault("art_cache", {})
    hit = cache.get(key)
    now = time.time()
    if hit and (hit.get("art") or now - float(hit.get("at") or 0) < _ART_MISS_COOLDOWN_S):
        return hit.get("art") or "", hit.get("album") or ""
    art, album = _itunes_lookup(title, artist)
    cache[key] = {"art": art, "album": album, "at": now}
    if len(cache) > _ART_CACHE_CAP:               # evict the OLDEST misses first — a real hit is never dropped
        stale = sorted(cache.items(), key=lambda kv: (bool(kv[1].get("art")), kv[1].get("at") or 0))
        for k, _v in stale[:len(cache) - _ART_CACHE_CAP]:
            cache.pop(k, None)
    if art:
        _backfill_art(db, key, art, album)
    return art, album


def _find_or_create_playlist(db: dict, name: str) -> "tuple[dict, bool]":
    """Resolve a spoken list name to the real playlist, CREATING it when it does not exist (V2-384).
    Measured live: «save it in a list called Curro» answered «Done.» with nothing behind —
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

    # V2-629 — lazy, cached cover-art lookup. The widget calls this ONCE per (title, artist) it renders
    # without art (recent/top/playlist rows the card, not the connector, is showing); never on the play
    # critical path, and never twice for the same song thanks to `_enrich_art`'s cache.
    if action == "enrich_art":
        title = (p.get("title") or "").strip()
        artist = (p.get("artist") or "").strip()
        if not title:
            return {"ok": False, "error": "missing_title"}
        db = _load_db()
        art, album = _enrich_art(db, title, artist)
        _persist(db)
        return {"ok": bool(art), "art": art, "album": album}

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
        out = {"ok": True, "playlist": pid, "name": name, "empty": True}
        # Teach through the seam (measured 2026-08-27: «save WHAT IS PLAYING in a list called Curro» ended as an
        # EMPTY list — the model picks create_playlist by lexical match and stops). The model reads this
        # result and the channel runs several data-ops per turn, so the hint lets it finish the job; with
        # nothing playing, an empty list is the whole request and no hint is added.
        if _current_track(db):
            out["hint"] = ("la lista está VACÍA y ahora mismo suena algo: si el operador quería guardarlo, "
                           "llama a add_to_playlist {playlist: '" + name + "'} sin canción y se añade la que suena")
        return out

    if action == "add_to_playlist":
        db = _load_db()
        ref = p.get("playlist") or p.get("id") or p.get("name")
        if not str(ref or "").strip():
            return {"ok": False, "error": "playlist_not_found", "playlist": ref}
        tr = _track_from_payload(p)
        if not tr:
            # No explicit track → the one PLAYING NOW («save this one in…»), which is what the spoken form
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
        # target can be a NAMED list («save it in Curro») — found or created, same seam as add_to_playlist.
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
            r = _play_track(tracks[0], db)                      # first track starts now (local or not)
            from connectors import music
            for t in tracks[1:]:                                # rest goes to queue (V2-047 F4)
                if _local.is_local(t):
                    continue        # the connector queue holds query STRINGS it re-resolves; a file
                                    # has nothing to re-resolve, so queueing it would silently drop it
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
            pl = _find_playlist(db, vid)                        # name -> actual ID
            vid = pl["id"] if pl else vid
        db["view"] = {"kind": kind, "id": vid}
        _persist(db)
        return {"ok": True, "view": db["view"]}

    if action == "back":
        db = _load_db()
        db["view"] = {"kind": "home", "id": ""}
        _persist(db)
        return {"ok": True, "view": db["view"]}

    # V2-638 — a track that is a FILE we hold. Mixed lists (a Spotify link, a YouTube link, a local file)
    # need no new schema: a local track is just `uri = "local:<rel>"`, so playlists, Recent and Top keep
    # working untouched.
    if action == "play_local":
        db = _load_db()
        t = _local.track_from_library(str(p.get("path") or p.get("file") or ""))
        if t is None:
            return {"ok": False, "error": "no encuentro ese audio en tu biblioteca (o no se puede reproducir)"}
        r = _play_track(t, db)
        if r.get("ok"):
            _push_recent(db, t)
        _persist(db)
        return r

    # Playback control from card buttons. Voice uses play_music. Converges on the same seam.
    # `ended` (V2-047 F4): fired by the widget when the song ends; the seam advances the queue.
    if action in ("play", "pause", "resume", "next", "previous", "volume_up", "volume_down", "set_volume",
                  "queue", "ended"):
        if action in ("ended", "next") and (_load_db().get("local") or {}).get("src"):
            # A local file finished (or was skipped): it is not in the connector's queue — that holds query
            # strings it re-resolves — so clear the bar here instead of asking the connector to advance past
            # something it never knew about.
            _db = _load_db()
            _local.stop(_db)
            _persist(_db)
            return {"ok": True, "message": "", "reason": ""}
        try:
            from connectors import music
            query = str(p.get("query") or "")
            r = music.control(action, query=query, percent=int(p.get("level") or 0))
            ok = bool(getattr(r, "ok", False))
            # Playing a standalone track from the card (recent/top/list row) feeds recent + top tracks. Voice
            # (play_music) goes through another path and does not pass here (Phase 1).
            if action == "play" and ok and query:
                db = _load_db()
                _push_recent(db, _track_from_resolved(query, getattr(r, "track", None)))
                _persist(db)
            else:
                _save_view()
            return {"ok": ok, "message": getattr(r, "message", ""), "reason": getattr(r, "reason", "")}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:120]}

    return {"ok": False, "error": "unknown_action", "action": action}
