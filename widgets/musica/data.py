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
import logging
import re
import time
import unicodedata

from .. import store
from . import local_audio as _local   # V2-638: a track that is a FILE in the agent's own library

WID = "musica"

_SEED = {"connected": False, "provider": "spotify", "can_connect": False, "own_client_id_set": False,
         "default_available": False, "redirect_uri": "", "now_playing": None}

_RECENT_CAP = 30
_TOP_CAP = 8


_log = logging.getLogger("zaelar.widgets.musica")


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
    db.setdefault("browse", {})
    return db


def _derive_top(db: dict) -> list:
    """Top tracks are derived from playback counters (counts), descending by count."""
    counts = db.get("counts") or {}
    items = sorted(counts.values(), key=lambda c: (-int(c.get("count") or 0), _norm(c.get("title"))))
    return [dict(c) for c in items[:_TOP_CAP]]


def _compose(db: dict) -> dict:
    """Exact blob seen by the card: persisted db + live state + derived top tracks + whether the track
    playing right now is already one of the operator's favorites (the heart's filled state, V2-629)."""
    live = _live_fields(db)
    from . import player as _player        # V2-795 — the transport's state, read from what is already stored
    return {**db, **live, "top": _derive_top(db),
            "fav_current": _fav_playlist_match(db, _current_track_from_live(live)),
            "modes": _player.modes(live), "queue": _player.queue_view(live, db),
            "volume": _player.volume(live, db), "fav": _fav_ref(db)}


def _fav_ref(db: dict) -> dict:
    """The favourites list the card's hearts write to: the one `_fav_playlist_match` reads, or the name
    `favorite_current` would create — so a heart on a row and the heart on the bar never open two lists."""
    for pl in db.get("playlists") or []:
        if "favorit" in _norm(pl.get("name")):
            return {"id": pl.get("id", ""), "name": pl.get("name", "")}
    return {"id": "", "name": "Favoritos"}


def view_data(q: str = "") -> dict:
    d = _compose(_load_db())
    # `art_cache` is server bookkeeping the card never reads. Stripped HERE, not in `_compose`: `_persist` writes
    # `_compose`'s return back whole, so stripping there would delete the cache on the next save (V2-629).
    d.pop("art_cache", None)
    return d


def _persist(db: dict) -> None:
    """Save the compound state, preserving yt + playlists + counts and reflecting connection; triggers SSE re-render."""
    try:
        store.save(WID, _compose(db))
    except Exception as _e:
        _log.debug("_persist: degraded, carrying on without it: %s", _e)
        pass


def _save_view() -> None:
    _persist(_load_db())


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


def _current_track(db: dict) -> "dict | None":
    return _current_track_from_live(_live_fields(db))


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
    The local branch needs the db (the player state lives there); without one a local track falls through to the
    connector, which refuses it."""
    if db is not None and _local.is_local(track):
        return _local.play(db, track)
    from connectors import music
    r = music.control("play", query=_track_query(track), uri=_uri_now(track))
    return {"ok": bool(getattr(r, "ok", False)), "message": getattr(r, "message", ""),
            "reason": getattr(r, "reason", "")}


def _uri_now(track: dict) -> str:
    """The track's uri when the provider playing now can use it, else "" (the player resolves it by its words)."""
    try:
        from connectors import music
        prov = music.active_provider()
        from . import curated as _curated
        return _curated.playable_uri(track, getattr(prov, "name", "") if prov else "")
    except Exception:  # noqa: BLE001
        return track.get("uri") or ""


def _find_or_create_playlist(db: dict, name: str) -> "tuple[dict, bool]":
    """Resolve a spoken list name to the real playlist, CREATING it when it does not exist (V2-384).
    The model gets ONE call: demanding create_playlist + add_to_playlist as two leaves nothing behind.
    Returns (playlist, created)."""
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


# The live reading, the track/list model, the cover art and the brain's readers live in their own modules; every
# name is re-exported here, where the siblings, the runtime and the tests look for it.
from .now_playing import (  # noqa: E402,F401
    _NP_FRESH_S, _current_track_from_live, _fresh_now_playing, _live_fields, _now_playing, _np_last,
    _read_now_playing, _spotify_status)
from .tracks import (  # noqa: E402,F401
    _ARTIST_TITLE_SEP, _YT_TAG_RE, _clean_yt_title, _closest_playlist, _find_playlist, _resolve_track_index,
    _split_artist_title, _track_from_payload, _track_from_resolved, _track_query, _yt_display)
from .art import (  # noqa: E402,F401
    _ART_CACHE_CAP, _ART_MISS_COOLDOWN_S, _art_cache_key, _backfill_art, _enrich_art, _itunes_lookup)
from .digest import (  # noqa: E402,F401
    _screen_word, prompt_digest, ref_index)


# The action handlers live in `actions.py` (which reads this module) (V2-778 F1-12).
from .actions import (  # noqa: E402,F401
    _a_refresh, _a_enrich_art, _a_create_playlist, _a_add_to_playlist,
    _a_remove_from_playlist, _a_favorite_current, _a_play_playlist, _a_open_view, _a_back, _a_play_local, _a_seek,
    _a_playback, _a_add_tracks, _a_rename_playlist, _a_delete_playlist, _a_move_track)
from .browse import a_search as _a_search, a_play_album as _a_play_album  # noqa: E402
from .player import (  # noqa: E402
    a_shuffle as _a_shuffle, a_repeat as _a_repeat, a_queue_remove as _a_queue_remove,
    a_queue_move as _a_queue_move, a_queue_clear as _a_queue_clear, a_played as _a_played)
from .sound import player_audio as _a_player_audio  # noqa: E402 — V2-812: what the page player really lets be heard


# `apply_action` is a table lookup; the contract gate reads the table's keys (`widgets/validator._table_actions`).


ACTIONS = {
    "refresh": _a_refresh,
    "enrich_art": _a_enrich_art,
    "create_playlist": _a_create_playlist,
    "add_to_playlist": _a_add_to_playlist,
    "add_tracks": _a_add_tracks,
    "remove_from_playlist": _a_remove_from_playlist,
    "favorite_current": _a_favorite_current,
    "play_playlist": _a_play_playlist,
    "open_view": _a_open_view,
    "back": _a_back,
    "play_local": _a_play_local,
    "seek": _a_seek,
    "play": _a_playback,
    "pause": _a_playback,
    "resume": _a_playback,
    "next": _a_playback,
    "previous": _a_playback,
    "volume_up": _a_playback,
    "volume_down": _a_playback,
    "set_volume": _a_playback,
    "queue": _a_playback,
    "ended": _a_playback,
    # V2-795 — what a player does that the card did not
    "rename_playlist": _a_rename_playlist,
    "delete_playlist": _a_delete_playlist,
    "move_track": _a_move_track,
    "shuffle": _a_shuffle,
    "repeat": _a_repeat,
    "queue_remove": _a_queue_remove,
    "queue_move": _a_queue_move,
    "queue_clear": _a_queue_clear,
    "search": _a_search,
    "play_album": _a_play_album,
    "played": _a_played,
    "player_audio": _a_player_audio,
}


def apply_action(action: str, payload: dict = None) -> dict:
    p = payload or {}
    handler = ACTIONS.get(action) if isinstance(action, str) else None
    if handler is None:
        return {"ok": False, "error": "unknown_action", "action": action}
    return handler(action, p)
