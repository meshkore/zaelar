# musica — cover-art ENRICHMENT through the iTunes Search API, cached per song (`data.py` re-exports every name).
import time



# A track with no art is looked up ONCE against iTunes (free, no key) and cached by (artist, title) (V2-629).
# `_ART_MISS_COOLDOWN_S` bounds only the NEGATIVE case: a hiccup is not a permanent "no art", nor is a song
# missing from the catalog re-queried on every render.
_ART_MISS_COOLDOWN_S = 14 * 24 * 3600
_ART_CACHE_CAP = 600


# ── Cover-art ENRICHMENT for tracks the connector never resolved (V2-629) ────────────────────────────────
# The SLOW, cached path the widget asks for lazily, once per song — never on the play critical path
# (`_track_from_resolved` covers anything actually played through YouTube-audio).
def _art_cache_key(title: str, artist: str) -> str:
    return _d._norm((title or "") + "|" + (artist or ""))


def _itunes_lookup(title: str, artist: str) -> "tuple[str, str]":
    """(art_url, album) from iTunes. Fail-open: the song just stays without art. The one iTunes client lives in
    `connectors/music/itunes.py` (V2-795)."""
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
    """Cached iTunes lookup: a HIT is cached forever (an album's art does not change); a MISS only for
    `_ART_MISS_COOLDOWN_S`."""
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
