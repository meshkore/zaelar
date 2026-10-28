# musica — the LIVE reading: the Spotify connection, what is playing now (with a short-lived cache for the digest's
# per-turn read), and the live fields the card composes over the stored db (refactor2710-12 T-03: moved out of
# `data.py`, which re-exports every name here).
import logging
import time

from . import local_audio as _local   # V2-638: a track that is a FILE in the agent's own library

_log = logging.getLogger("zaelar.widgets.musica")


def _spotify_status() -> dict:
    try:
        from connectors.spotify import auth
        return auth.status()
    except Exception as _e:
        _log.debug("_spotify_status: degraded, carrying on without it: %s", _e)
        return {}


#: The last Spotify reading and when it was taken (V2-812): the brain's digest rides every turn while the card is
#: open, and a network read per turn is a price; a reading this fresh is the same fact.
_NP_FRESH_S = 5.0
_np_last: dict = {"at": 0.0, "np": None, "src": None}


def _now_playing() -> "dict | None":
    """What is playing NOW on the provider making the sound. Fail-open: never breaks the card."""
    np = _read_now_playing()
    _np_last.update(at=time.time(), np=np)
    return np


def _fresh_now_playing(db: dict, fresh_s: float) -> "dict | None":
    """A reading at most `fresh_s` old, of the SAME start: a new start (another provider, another device) is never
    answered with the reading of the old one."""
    src = db.get("source")
    if fresh_s and time.time() - _np_last["at"] < fresh_s and _np_last.get("src") == src:
        return _np_last["np"]
    np = _d._now_playing()
    _np_last["src"] = src
    return np


def _read_now_playing() -> "dict | None":
    try:
        from connectors import music
        np = music.now_playing()
        if not np:
            return None
        t = np.track
        # V2-717 — where the song IS, so the card can draw a progress bar for a device that is not here.
        # `progress_ms` is a photograph taken at THIS read (the card advances it with its own clock) and
        # `duration_ms` is what makes it meaningful; either at 0 means «this provider does not say», and the
        # card then draws no bar at all rather than one pinned at zero.
        return {"playing": bool(np.playing), "device": np.device or "", "volume": np.volume, "provider": np.provider,
                "title": (t.title if t else ""), "artist": (t.artist if t else ""),
                "album": (t.album if t else ""), "art": (t.art if t else ""),
                "progress_ms": int(getattr(np, "progress_ms", 0) or 0),
                "duration_ms": int(t.duration_ms if t else 0),
                "shuffle": bool(getattr(np, "shuffle", False)), "repeat": str(getattr(np, "repeat", "off") or "off")}
    except Exception as _e:
        _log.debug("_read_now_playing: degraded, carrying on without it: %s", _e)
        return None


def _live_fields(db: dict, fresh_s: float = 0.0) -> dict:
    """Live state recomputed on each read: Spotify connection + card display mode + now_playing. `fresh_s` > 0 lets
    a reading that young stand in for a new one (the digest's per-turn read, V2-812)."""
    st = _spotify_status()
    connected = bool(st.get("logged_in"))
    yt = dict(db.get("yt") or {})
    # mode = what the bar shows: spotify (remote device), youtube (hidden audio), or idle.
    loc = _local.display(db)
    # V2-638 — a file we hold is the third thing the bar can be showing. It wins over the connector
    # modes because it is the one playing IN the page: `local_audio.play` clears the yt block, so the
    # two can never be set at once and the order here only decides what an inconsistent db shows.
    # V2-812 — the bar shows the player that MAKES the sound: a song started in this page's player while a Spotify
    # account is connected (no Spotify device on the screen that asked) is the page player's, and the Spotify reading
    # of a device elsewhere is not what he hears.
    in_page = (db.get("source") or {}).get("provider") == "youtube" and yt.get("videoId")
    mode = "local" if loc else ("youtube" if in_page else ("spotify" if connected else
                                                           ("youtube" if yt.get("videoId") else "idle")))
    return {
        **_d._SEED,
        "connected": connected,
        "can_connect": bool(st.get("can_connect")),
        "own_client_id_set": bool(st.get("own_client_id_set")),
        "default_available": bool(st.get("default_available")),
        "redirect_uri": st.get("redirect_uri", ""),
        "now_playing": (None if mode != "spotify" else
                        _fresh_now_playing(db, fresh_s) if fresh_s else _d._now_playing()),
        "yt": _d._yt_display(yt),
        "local": loc,
        "mode": mode,
        "empty": mode == "idle",                             # V2-776 L2 — nothing playing, nothing to attest
    }


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


from . import data as _d  # noqa: E402 — read back at call time: data owns the store and re-exports these
