# musica — the TRACK and LIST model: a track built from a payload or a resolved provider track, the display
# clean-up of an upload title, and the resolution of a spoken list or track reference (`data.py` re-exports all).
import re



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
    Plain concatenation is left untouched: with no metadata to guess from, a wrong split is worse than none."""
    parts = _ARTIST_TITLE_SEP.split(text, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return "", text.strip()


# YouTube upload boilerplate ("(Official Video)", "[Lyric Video]"…) stripped for DISPLAY ONLY — the STORED title
# never changes, so the no-restart guard on `yt.query` is untouched (V2-047 F5). Only a KNOWN, closed set of tags,
# applied repeatedly for stacked ones: recognize, don't invent.
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
    """The `yt` block reshaped for what the card SHOWS: boilerplate stripped, an artist split off an explicit
    delimiter. Never mutates the stored block: the OTHER fields pass through byte-identical, which
    `widget.js::syncYtPlayer`'s equality checks depend on."""
    if not yt or not yt.get("videoId"):
        return yt or {}
    out = dict(yt)
    title = _clean_yt_title(yt.get("title"))
    artist, stripped = _split_artist_title(title)
    out["title"] = stripped if artist else title
    if artist:
        out["artist"] = artist
    return out


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


def _find_playlist(db: dict, ref) -> "dict | None":
    """Resolves a reference (exact ID or natural-language name) to the actual list. Never invents one."""
    ref = str(ref or "")
    pls = db.get("playlists") or []
    for pl in pls:                                    # exact ID
        if pl.get("id") == ref:
            return pl
    nref = _d._norm(ref)
    if not nref:
        return None
    for pl in pls:                                    # exact name
        if _d._norm(pl.get("name")) == nref:
            return pl
    for pl in pls:                                    # contains / contained in
        nn = _d._norm(pl.get("name"))
        if nn and (nref in nn or nn in nref):
            return pl
    return None


def _closest_playlist(db: dict, ref) -> "dict | None":
    """Last-resort resolution for a SPOKEN reference STT garbled («Trublo» for «True Blue»). Normalized,
    space-stripped similarity; only a CLEAR, UNIQUE winner resolves (≥0.6, runner-up under 0.5). Anything
    murkier stays a refusal that names what exists — never a guess between two plausible lists."""
    from difflib import SequenceMatcher
    nref = _d._norm(str(ref or "")).replace(" ", "")
    if not nref:
        return None
    scored = []
    for pl in (db.get("playlists") or []):
        nn = _d._norm(pl.get("name") or "").replace(" ", "")
        if nn:
            scored.append((SequenceMatcher(None, nref, nn).ratio(), pl))
    scored.sort(key=lambda t: -t[0])
    if scored and scored[0][0] >= 0.6 and (len(scored) == 1 or scored[1][0] < 0.5):
        return scored[0][1]
    return None


def _resolve_track_index(tracks: list, item) -> "int | None":
    """item = 1-based index ('2') or text matching a track title/query in the list."""
    if item is None:
        return None
    s = str(item).strip()
    if s.isdigit():
        i = int(s) - 1
        return i if 0 <= i < len(tracks) else None
    nitem = _d._norm(s)
    if not nitem:
        return None
    for i, t in enumerate(tracks):                    # exact match
        if nitem == _d._norm(t.get("title")) or nitem == _d._norm(t.get("query")):
            return i
    for i, t in enumerate(tracks):                    # contains
        hay = _d._norm(" ".join([t.get("title") or "", t.get("artist") or "", t.get("query") or ""]))
        if nitem in hay:
            return i
    return None


def _track_from_resolved(query: str, track) -> dict:
    """What gets remembered in Recent/Top when the card plays a bare query: the RESOLVED provider `Track` (title,
    artist, album, cover art) when the connector found one, the operator's own words otherwise."""
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


from . import data as _d  # noqa: E402 — read back at call time: data owns the store and re-exports these
