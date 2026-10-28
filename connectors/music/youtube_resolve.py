"""connectors/music/youtube_resolve.py — a song query → (videoId, title), for the free in-browser provider.

**YouTube Data API** if `YOUTUBE_API_KEY` exists (fast and reliable), otherwise a stdlib scrape of the results page
(best-effort, fail-open) — OWN copy, does not touch the YouTube widget. The provider is `youtube_audio.py`.
"""
from __future__ import annotations

import logging
import os
import re
import urllib.parse
import urllib.request

logger = logging.getLogger("zaelar.music.youtube")


def _lang() -> str:
    from i18n import langs as _langs
    return (_langs.current_code() or "en").lower()


# ── query resolution -> (videoId, title) ─────────────────────────────────────────────────────────────────
_YT_ID_RE = re.compile(r'"videoId":"([0-9A-Za-z_-]{11})"')
_YT_TITLE_RE = r'"videoId":"{vid}".*?"text":"([^"]{{3,120}})"'


def _resolve_api(query: str) -> tuple:
    key = (os.getenv("YOUTUBE_API_KEY") or "").strip()
    if not key:
        return "", ""
    try:
        import httpx
        r = httpx.get("https://www.googleapis.com/youtube/v3/search", params={
            "part": "snippet", "type": "video", "videoCategoryId": "10",  # 10 = Music
            "q": query, "maxResults": 1, "key": key}, timeout=8)
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


def _resolve_scrape(query: str) -> tuple:
    try:
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query + " audio")
        req = urllib.request.Request(url, headers={
            "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"),
            # V2-678 — this was hardcoded `es-ES` in a module that reads the operator's language two
            # functions above for its own sentences. So the provider answered in Spanish whatever the
            # operator speaks, and the agent spoke the Spanish title back: measured live 2026-09-12
            # (session 352268b5, 11:00:11), an English session got «Now playing 75 vídeos.»
            "Accept-Language": _accept_language(),
            # The consent choice already made. From an EU address without it the results page is a consent
            # interstitial with no video in it, and the search came back empty — which is where a hosted
            # instance in an EU region sits. Changes nothing where no interstitial is served.
            "Cookie": "SOCS=CAI; CONSENT=YES+"})
        html = urllib.request.urlopen(req, timeout=6).read().decode("utf-8", "ignore")
        m = _YT_ID_RE.search(html)
        if not m:
            return "", ""
        vid = m.group(1)
        t = re.search(_YT_TITLE_RE.format(vid=re.escape(vid)), html)
        return vid, (t.group(1) if t else query)
    except Exception:
        return "", ""


def _resolve(query: str) -> tuple:
    vid, title = _resolve_api(query)
    if not vid:
        vid, title = _resolve_scrape(query)
    # The QUERY is what he actually said; a bare count is what the provider happened to label the list.
    if vid and is_a_count_not_a_name(title):
        return vid, (query or title)
    return vid, title


_YT_URL_RE = re.compile(r"(?:v=|youtu\.be/|/embed/|^)([0-9A-Za-z_-]{11})")


def _extract_id(uri: str) -> str:
    m = _YT_URL_RE.search((uri or "").replace("yt:", ""))
    return m.group(1) if m else ""
