"""connectors/music/youtube_resolve.py — a song query → (videoId, title), for the free in-browser provider.

**YouTube Data API** if `YOUTUBE_API_KEY` exists, otherwise the search service's video door (`search/video.py`: the
results page, then the warm Chromium) — the SAME door the video card uses (V2-833 F1). The provider is `youtube_audio.py`.
"""
from __future__ import annotations

import logging
import os
import re
from connectors import outcome as _outcome   # every provider call reports what happened (V2-833)

logger = logging.getLogger("zaelar.music.youtube")


def _lang() -> str:
    from i18n import langs as _langs
    return (_langs.current_code() or "en").lower()


# ── query resolution -> (videoId, title) ─────────────────────────────────────────────────────────────────


def _resolve_api(query: str) -> tuple:
    key = (os.getenv("YOUTUBE_API_KEY") or "").strip()
    if not key:
        return "", ""
    try:
        import httpx
        r = _outcome.call("youtube.api", "search", lambda: httpx.get("https://www.googleapis.com/youtube/v3/search", params={
            "part": "snippet", "type": "video", "videoCategoryId": "10",  # 10 = Music
            "q": query, "maxResults": 1, "key": key}, timeout=8), measure=lambda r: {"status": r.status_code},
            refused=lambda r: r.status_code >= 400, empty=lambda r: not (r.json() or {}).get("items"))
        if r.status_code >= 400:
            logger.warning(f"YouTube Data API {r.status_code}: {r.text[:100]}")
            return "", ""
        items = (r.json() or {}).get("items") or []
        if not items:
            return "", ""
        sn = items[0].get("snippet") or {}
        return items[0].get("id", {}).get("videoId", ""), sn.get("title", query)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"YouTube Data API falló: {e!r}")
        return "", ""


def _accept_language() -> str:
    """The `Accept-Language` for a provider request — the operator's language, never a hardcoded one.

    A third party answers in the language we ask in, and whatever it answers can end up spoken. This is the
    cheapest half of «todo pasa por el idioma del operador»: one header.
    """
    code = _lang()
    # Only where a region is real. Deriving one («en» → «en-EN») invents a locale that does not exist, so
    # anything not in the map travels as the bare language tag, which is valid and honest.
    region = {"es": "es-ES", "en": "en-US", "fr": "fr-FR", "de": "de-DE", "pt": "pt-PT", "it": "it-IT"}
    head = region.get(code, code)
    return f"{head},{code};q=0.9,en;q=0.5"


# A resolved «title» that is nothing but a COUNT is not a name. YouTube labels a playlist that way
# («75 vídeos», «26 videos»), and speaking it produces «Now playing 75 vídeos.» — which says nothing, in
# the wrong language, about songs the operator asked for by NAME. Measured live twice in one minute.
_BARE_COUNT_RE = re.compile(r"^\s*\d+\s*(?:v[ií]deos?|videos?|canciones|songs|tracks|elementos|items)\s*$",
                            re.I)


def is_a_count_not_a_name(title: str) -> bool:
    """True when a provider's «title» is a bare item count, so the caller says what was ASKED for instead."""
    return bool(_BARE_COUNT_RE.match(title or ""))


def _resolve(query: str) -> tuple:
    """(videoId, title, why) — `why` is the lookup's outcome: found · empty · unreachable (V2-833 F3: «I could not
    ask» is never told as «there is no such song»)."""
    vid, title = _resolve_api(query)
    why = "found" if vid else "empty"
    if not vid:
        # V2-833 F1 — the search service's one video door (page, then the warm Chromium), never a private scrape
        from search import video as _video
        seen: dict = {}
        hits = _video.find_videos(f"{query} audio", 1, accept_language=_accept_language(), outcome=seen)
        vid, title = (hits[0]["videoId"], hits[0]["title"]) if hits else ("", "")
        why = seen.get("reason") or why
    # The QUERY is what he actually said; a bare count is what the provider happened to label the list.
    if vid and is_a_count_not_a_name(title):
        return vid, (query or title), why
    return vid, title, why


_YT_URL_RE = re.compile(r"(?:v=|youtu\.be/|/embed/|^)([0-9A-Za-z_-]{11})")


def _extract_id(uri: str) -> str:
    m = _YT_URL_RE.search((uri or "").replace("yt:", ""))
    return m.group(1) if m else ""
