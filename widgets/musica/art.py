# musica — cover-art ENRICHMENT through the iTunes Search API, cached per song (refactor2710-12 T-03: moved out of
# `data.py`, which re-exports every name here).
import time



# Cover-art ENRICHMENT (V2-629): a track with no art yet (typed into a list, imported, or a legacy row from
# before the connector started giving out YouTube thumbnails for free) gets looked up ONCE against the iTunes
# Search API — free, no key, no auth — and the result is cached forever by (artist, title) so the SAME song
# never pays a second network round trip, on this machine or the next request. `_ART_MISS_COOLDOWN_S` bounds
# only the NEGATIVE case (nothing found): a transient API hiccup or a temporarily-misspelled title should not
# become a permanent "no art" verdict, but a song that genuinely is not in iTunes' catalog should not be
# re-queried on every render either.
_ART_MISS_COOLDOWN_S = 14 * 24 * 3600
_ART_CACHE_CAP = 600


# ── Cover-art ENRICHMENT for tracks the connector never resolved (V2-629) ────────────────────────────────
# A track typed straight into a list (`add_to_playlist {title, artist}`, no `query`), or a legacy row from
# before the connector started giving out YouTube thumbnails, has no art and never will on its own. This is
# the SLOW, cached path the widget asks for lazily, on demand, once per song — never on the play critical
# path (`_track_from_resolved` above already covers the fast, zero-cost case for anything actually played
# through YouTube-audio).
def _art_cache_key(title: str, artist: str) -> str:
    return _d._norm((title or "") + "|" + (artist or ""))


def _itunes_lookup(title: str, artist: str) -> "tuple[str, str]":
    """(art_url, album) from the iTunes Search API — free, no key, no auth. Best-effort, fail-open: a network
    hiccup or a song iTunes does not carry must never break the widget, it just stays without art. The one
    iTunes client lives in the connector (`connectors/music/itunes.py`, V2-795), shared with search/browse."""
    from connectors.music import itunes
    return itunes.cover(title, artist)


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


from . import data as _d  # noqa: E402 — read back at call time: data owns the store and re-exports these
