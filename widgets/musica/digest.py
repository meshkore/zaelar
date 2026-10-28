# musica — what the BRAIN reads of the card: the voice reference index and the now-playing digest (refactor2710-12
# T-03: moved out of `data.py`, which re-exports both because the runtime looks them up there).
import logging

from i18n import langs as _langs   # V2-778 F3-30: hints are read back aloud, in the agent's language

_log = logging.getLogger("zaelar.widgets.musica")


# ref_index (V2-026): playlists are voice-referenceable by name.
def ref_index() -> list:
    try:
        db = _d._load_db()
    except Exception as _e:
        _log.debug("ref_index: degraded, carrying on without it: %s", _e)
        return []
    out = []
    for pl in db.get("playlists") or []:
        n = len(pl.get("tracks") or [])
        out.append({"id": pl.get("id"), "label": pl.get("name") or pl.get("id"),
                    "field": "playlist",
                    "hint": _langs.words("hints.song_one" if n == 1 else "hints.song_many", default="{n}").format(n=n)})
    return out


def prompt_digest() -> str:
    """What the OPEN card shows, for the brain (V2-812): the song, WHICH player makes the sound and where, playing or
    paused, the volume, and whether the browser keeps it silent. Asked «is it muted?» over a card showing a song, the
    brain only had the list index — no lists, so «the card is EMPTY» — and answered that it had no data. Empty
    string when nothing plays: the lists line (`refs.items_line`) is then the whole truth."""
    try:
        db = _d._load_db()
        live = _d._live_fields(db, fresh_s=_d._NP_FRESH_S)
    except Exception as _e:  # noqa: BLE001
        _log.debug("prompt_digest: degraded, carrying on without it: %s", _e)
        return ""
    from . import player as _player
    from . import sound as _sound
    mode = live.get("mode")
    np = live.get("now_playing") or {}
    cur = (np if np.get("title") else None) if mode == "spotify" else (
        (live.get("local") or None) if mode == "local" else _d._current_track_from_live(live))
    if mode == "idle" or not cur:
        return ""
    if mode == "spotify":
        where = f"Spotify, on the device «{np.get('device') or '?'}» (not this page)"
        playing = bool(np.get("playing"))
    else:
        blk = (live.get("yt") or {}) if mode == "youtube" else (live.get("local") or {})
        screen = _screen_word((db.get("source") or {}).get("screen", ""))
        where = "the page player of this card" + (f", on his {screen}" if screen else "")
        playing = not blk.get("paused")
    vol = _player.volume(live, db)
    level = "?" if vol.get("level") is None else f"{vol['level']}%"
    lines = [f"MUSIC CARD — NOW: «{cur.get('title') or '?'}"
             + (f" — {cur.get('artist')}" if cur.get("artist") else "") + f"» · source: {where} · "
             + ("playing" if playing else "paused") + f" · volume {level}" + (" (MUTED)" if vol.get("muted") else "")]
    if (snd := _sound.digest_line(live)):
        lines.append(snd)
    n = len((_player.queue_view(live, db) or {}).get("items") or [])
    if n:
        lines.append(f"queue: {n} after this one")
    return "\n".join(lines)


def _screen_word(dev: str) -> str:
    try:
        from voice import screens
        return screens.surface(dev) if dev else ""
    except Exception as _e:  # noqa: BLE001
        _log.debug("_screen_word: degraded, carrying on without it: %s", _e)
        return ""


from . import data as _d  # noqa: E402 — read back at call time: data owns the store and re-exports these
