"""connectors/music/itunes.py — the FREE catalogue: metadata from the iTunes Search API (V2-795).

No key, no account, no consent. It answers «which songs, artists and albums match these words» and «what is on
this album / by this artist» — never «play it»: it has no player. A track found here carries no `uri`, so whoever
plays it does so by its WORDS (`title artist`) through the active provider, exactly as a song typed into a list
is played. That is what lets the card search and browse with no streaming account connected at all.

Network I/O, synchronous, fail-open: a failure is logged and comes back as empty results, never an exception.
"""
from __future__ import annotations

import concurrent.futures as _cf
import json
import logging
import urllib.parse
import urllib.request
from connectors import outcome as _outcome   # every provider call reports what happened (V2-833)

logger = logging.getLogger("zaelar.music.itunes")

_BASE = "https://itunes.apple.com"
_TIMEOUT_S = 6


def _get(path: str, params: dict) -> list:
    """The `results` of one request, or [] (logged) when the network or the payload fails."""
    url = f"{_BASE}/{path}?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = json.loads(_outcome.call("itunes", path, lambda: urllib.request.urlopen(req, timeout=_TIMEOUT_S).read(),
                                        empty=lambda b: b'"resultCount":0' in b, measure=lambda b: {"bytes": len(b)}
                                        ).decode("utf-8", "ignore"))
    except Exception as e:  # noqa: BLE001 — a catalogue hiccup leaves the card without results, never broken
        logger.info(f"itunes {path} failed: {e!r}")
        data = {}
    res = data.get("results") if isinstance(data, dict) else None
    return res if isinstance(res, list) else []


def art(url: str) -> str:
    """iTunes hands out 100x100 thumbnails; the same URL with the size segment rewritten is 600x600."""
    return str(url or "").replace("100x100bb", "600x600bb")


def _track(r: dict) -> dict:
    title, artist = str(r.get("trackName") or ""), str(r.get("artistName") or "")
    return {"title": title, "artist": artist, "album": str(r.get("collectionName") or ""),
            "art": art(r.get("artworkUrl100")), "uri": "", "id": str(r.get("trackId") or ""),
            "duration_ms": int(r.get("trackTimeMillis") or 0),
            "query": " ".join(x for x in (title, artist) if x), "provider": "", "source": "itunes"}


def _album(r: dict) -> dict:
    return {"id": str(r.get("collectionId") or ""), "name": str(r.get("collectionName") or ""),
            "artist": str(r.get("artistName") or ""), "art": art(r.get("artworkUrl100")),
            "year": str(r.get("releaseDate") or "")[:4], "uri": "", "source": "itunes"}


def _artist(r: dict, pics: dict) -> dict:
    aid = str(r.get("artistId") or "")
    return {"id": aid, "name": str(r.get("artistName") or ""), "art": pics.get(aid, ""), "uri": "",
            "source": "itunes"}


def search(query: str, limit: int = 8) -> dict:
    """{tracks, artists, albums, playlists:[]} for free text. Three small requests, run side by side."""
    q = (query or "").strip()
    if not q:
        return {"tracks": [], "artists": [], "albums": [], "playlists": []}
    asks = {"song": {"term": q, "entity": "song", "limit": limit},
            "artist": {"term": q, "entity": "musicArtist", "limit": 5},
            "album": {"term": q, "entity": "album", "limit": 6}}
    with _cf.ThreadPoolExecutor(max_workers=3) as ex:
        futs = {k: ex.submit(_get, "search", v) for k, v in asks.items()}
        got = {k: f.result() for k, f in futs.items()}
    songs = [r for r in got["song"] if r.get("trackName")]
    albums = [r for r in got["album"] if r.get("collectionName")]
    # An artist has no picture of its own here; the cover of one of ITS songs or albums stands in for one.
    pics: dict = {}
    for r in songs + albums:
        aid = str(r.get("artistId") or "")
        if aid and aid not in pics and r.get("artworkUrl100"):
            pics[aid] = art(r.get("artworkUrl100"))
    return {"tracks": [_track(r) for r in songs],
            "artists": [_artist(r, pics) for r in got["artist"] if r.get("artistName")],
            "albums": [_album(r) for r in albums], "playlists": []}


def artist(artist_id: str) -> "dict | None":
    """{artist, top, albums} for one iTunes artist id, or None when it is not found."""
    aid = str(artist_id or "").strip()
    if not aid.isdigit():
        return None
    albums = _get("lookup", {"id": aid, "entity": "album", "limit": 12})
    songs = _get("lookup", {"id": aid, "entity": "song", "limit": 10})
    head = next((r for r in albums + songs if r.get("wrapperType") == "artist"), None)
    if head is None:
        return None
    alb = [_album(r) for r in albums if r.get("wrapperType") == "collection"]
    top = [_track(r) for r in songs if r.get("wrapperType") == "track"]
    pic = (alb[0]["art"] if alb else "") or (top[0]["art"] if top else "")
    return {"artist": _artist(head, {aid: pic}), "top": top, "albums": alb}


def album(album_id: str) -> "dict | None":
    """{album, tracks} for one iTunes collection id, in track order, or None when it is not found."""
    cid = str(album_id or "").strip()
    if not cid.isdigit():
        return None
    rows = _get("lookup", {"id": cid, "entity": "song", "limit": 60})
    head = next((r for r in rows if r.get("wrapperType") == "collection"), None)
    if head is None:
        return None
    tracks = sorted((r for r in rows if r.get("wrapperType") == "track"),
                    key=lambda r: (int(r.get("discNumber") or 1), int(r.get("trackNumber") or 0)))
    return {"album": _album(head), "tracks": [_track(r) for r in tracks]}


def cover(title: str, artist_name: str) -> "tuple[str, str]":
    """(art_url, album) of the best match for one song — the lookup the card's art enrichment uses."""
    term = " ".join(p for p in (artist_name, title) if p).strip()
    if not term:
        return "", ""
    rows = _get("search", {"term": term, "entity": "song", "limit": 1})
    if not rows:
        return "", ""
    return art(rows[0].get("artworkUrl100")), str(rows[0].get("collectionName") or "").strip()
