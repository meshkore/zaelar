"""search/video.py — a video (or a track to play) on YouTube, found THROUGH the search service (V2-833 F1).

The class: YouTube lookups had left the service. The video card (`widgets/youtube/data`) and the music player's
in-page resolver (`connectors/music/youtube_resolve`) each scraped the results page with their own copy — other
headers, another parser — with no health probe, no second source and no outcome. On a hosted engine the music copy
came back empty ten times in a row while the card's copy had worked on the same Machine two days earlier, and
nothing said why (`stack.md`: «a search never leaves the service»).

One door, `find_videos(query, n)`, over the providers declared in `providers/__init__.py`, in order:
  · `youtube`         — the results page over HTTP: free, fast; the one parser (each hit must carry a title).
  · `youtube_browser` — the same page in the service's warm Chromium (a real browser's fingerprint), when the first
                        answered nothing or could not be reached.
Each call reports its outcome (`connectors/outcome`): found · empty · unreachable, with size and hits. A caller gets
`[{videoId, title, channel, published}]` — or [] once every provider has had its say.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request

from connectors import outcome as _outcome

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36")
_ID_RE = re.compile(r'"videoId":"([0-9A-Za-z_-]{11})"')


def results_url(query: str, *, latest: bool = False) -> str:
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    return url + "&sp=CAI%3D" if latest else url             # sort by upload date


def _unesc(s: str) -> str:
    """Decode \\uXXXX sequences YouTube embeds in its JSON, without touching already decoded UTF-8."""
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s or "")


def parse(html: str, n: int) -> list[dict]:
    """Top-`n` DISTINCT videos of a results page, in page order. A hit the parser cannot NAME is not a candidate
    (V2-469: Shorts blocks repeat `videoId` with no title — skipped, the walk goes on). Each block is bounded at the
    NEXT different id, so a title-less block never steals its neighbour's title."""
    out, seen = [], set()
    ms = list(_ID_RE.finditer(html or ""))
    for i, m in enumerate(ms):
        vid = m.group(1)
        if vid in seen:
            continue
        seen.add(vid)
        end = m.start() + 2500
        for m2 in ms[i + 1:]:
            if m2.group(1) != vid:
                end = min(end, m2.start())
                break
        blk = html[m.start(): end]
        t = re.search(r'"title":\{"runs":\[\{"text":"([^"]{2,140})"', blk)
        if not t:
            continue
        ch = re.search(r'"(?:ownerText|longBylineText)":\{"runs":\[\{"text":"([^"]{1,80})"', blk)
        pub = re.search(r'"publishedTimeText":\{"simpleText":"([^"]{2,40})"', blk)
        out.append({"videoId": vid, "title": _unesc(t.group(1)), "channel": _unesc(ch.group(1)) if ch else "",
                    "published": _unesc(pub.group(1)) if pub else ""})
        if len(out) >= n:
            break
    return out


def _page(query: str, n: int, latest: bool, accept_language: str) -> list[dict]:
    req = urllib.request.Request(results_url(query, latest=latest),
                                 headers={"User-Agent": _UA, "Accept-Language": accept_language})
    raw = _outcome.call("youtube", "results", lambda: urllib.request.urlopen(req, timeout=6).read(),
                        empty=lambda b: not parse(b.decode("utf-8", "ignore"), 1),
                        measure=lambda b: {"bytes": len(b), "hits": b.count(b'"videoId"')})
    return parse(raw.decode("utf-8", "ignore"), n)


def _browser(query: str, n: int, latest: bool) -> list[dict]:
    from . import browser
    html = _outcome.call("youtube_browser", "results", lambda: browser.page_html_sync(results_url(query, latest=latest)),
                         empty=lambda h: not parse(h, 1), measure=lambda h: {"bytes": len(h)})
    return parse(html, n)


def find_videos(query: str, n: int = 5, *, latest: bool = False, accept_language: str = "en-US,en;q=0.9",
                outcome: dict | None = None) -> list[dict]:
    """The videos a phrase names, through every declared provider until one answers. Never raises. `outcome`, when
    given, is filled with `reason`: found · empty (a provider answered, nothing named) · unreachable (none answered)."""
    q = " ".join(str(query or "").split())
    if not q or n <= 0:
        return []
    answered = False
    for source in (lambda: _page(q, n, latest, accept_language), lambda: _browser(q, n, latest)):
        try:
            hits = source()
        except Exception as e:  # noqa: BLE001 — reported by the outcome door; the next provider is asked
            __import__("logging").getLogger(__name__).debug("video lookup: provider unreachable: %r", e)
            continue
        answered = True
        if hits:
            if outcome is not None:
                outcome["reason"] = _outcome.FOUND
            return hits
    if outcome is not None:
        outcome["reason"] = _outcome.EMPTY if answered else _outcome.UNREACHABLE
    return []
