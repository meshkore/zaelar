"""Playing a track that is a FILE in the agent's own library (V2-638).

The music widget had exactly two ways to make sound: a Spotify device, or a hidden YouTube iframe. Both are
somebody else's catalog. This is the third — a file we hold, in `library/audio/` — and it is what makes a
playlist able to mix a Spotify link, a YouTube link and a local file, which is what the operator asked for.

**A local track needs no new schema.** The track shape already carries `uri`, dispatched by `_play_track`, and
YouTube-audio already uses a scheme there (`yt:<id>`). So a local track is just `uri = "local:<rel>"`, and every
existing path — playlists, Recent, Top, dedup by title/artist — keeps working untouched.

What IS new is that this provider plays in the PAGE rather than out of process: `db["local"]` carries the src
and a sequence number, and `widget.js` mounts an `<audio>` for it, exactly as it mounts the hidden iframe for
YouTube. The `seq` is what makes re-playing the SAME file work — without it the widget cannot tell "play this
again" from "nothing changed" and the second request is silently ignored.
"""
from __future__ import annotations

import os

PREFIX = "local:"


def is_local(track) -> bool:
    return str((track or {}).get("uri") or "").startswith(PREFIX)


def rel_of(track) -> str:
    """The library-relative path inside a `local:` uri."""
    return str((track or {}).get("uri") or "")[len(PREFIX):] if is_local(track) else ""


def track_from_library(rel: str) -> "dict | None":
    """The track shape for an audio file we hold, or None if it is not there / cannot be played."""
    from library import index
    rec = index.entry_for(rel)
    if not rec or rec.get("kind") != "audio" or not rec.get("playable"):
        return None
    stem = os.path.splitext(rec["name"])[0]
    # A file name is all the metadata a bare file has. «Artist - Title» is the one convention worth reading;
    # anything else stays a title, because inventing an artist from a filename is how a library fills with
    # wrong credits that then propagate into Recent, Top and every playlist that ever holds the track.
    artist, title = "", stem
    if " - " in stem:
        left, right = stem.split(" - ", 1)
        if left.strip() and right.strip():
            artist, title = left.strip(), right.strip()
    return {"title": title, "artist": artist, "album": "", "art": "",
            "query": stem, "uri": PREFIX + rec["rel"], "videoId": "", "src": rec["url"]}


def play(db: dict, track: dict) -> dict:
    """Make a local track the current one. Returns the `_play_track` result shape."""
    from library import index
    rel = rel_of(track)
    rec = index.entry_for(rel) if rel else None
    if not rec or not rec.get("playable"):
        return {"ok": False, "message": "", "reason": "ese fichero ya no está en tu biblioteca"}
    cur = dict(db.get("local") or {})
    db["local"] = {
        "src": rec["url"],
        "rel": rec["rel"],
        "title": track.get("title") or rec["name"],
        "artist": track.get("artist") or "",
        "art": track.get("art") or "",
        "paused": False,
        # Bumped on EVERY play, so asking for the same file twice is two events and not one silent no-op.
        "seq": int(cur.get("seq") or 0) + 1,
    }
    # The bar shows ONE thing. Leaving the YouTube block behind would have the card claiming two songs at once.
    db["yt"] = {}
    return {"ok": True, "message": "", "reason": ""}


def stop(db: dict) -> None:
    if db.get("local"):
        db["local"] = {}


def display(db: dict) -> dict:
    """What the playback bar shows for a local track ({} when nothing local is playing)."""
    loc = dict(db.get("local") or {})
    if not loc.get("src"):
        return {}
    return {"src": loc.get("src", ""), "title": loc.get("title", ""), "artist": loc.get("artist", ""),
            "art": loc.get("art", ""), "paused": bool(loc.get("paused")), "seq": int(loc.get("seq") or 0)}
