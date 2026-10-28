"""channel_fetch.py — how a channel page is FETCHED and its numbers and dates PARSED (split from `channels.py`)."""
import calendar
import json
import os
import re
import time
import urllib.parse
import urllib.request
from .. import store

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/122.0 Safari/537.36")
# The pages are asked for in the CARD's language (es | en). Not a nicety: YouTube translates video titles
# to the requested language, so asking in English showed a Spanish channel's videos under English titles
# (measured 2026-09-29). The two languages' counts and relative dates («2,3 K», «hace 1 h» / «2.3K», «1h
# ago») are parsed into numbers here and formatted by the card; sections are recognised by their URL, never
# by their translated title.
# Kept es|en on purpose: the count/relative-date parsers below only read those two languages' formats.
_HL = {"hl": "es"}


def _headers() -> dict:
    lang = "es-ES,es;q=0.9" if _HL["hl"] == "es" else "en-US,en;q=0.9"
    return {"User-Agent": _UA, "Accept-Language": lang, "Cookie": "CONSENT=YES+1; SOCS=CAI"}


def set_lang(hl) -> None:
    _HL["hl"] = "en" if str(hl or "").lower().startswith("en") else "es"
_TIMEOUT = 8

# ── fetching ──────────────────────────────────────────────────────────────────────────────────────────────

def _get(url: str) -> str:
    req = urllib.request.Request(url, headers=_headers())
    return urllib.request.urlopen(req, timeout=_TIMEOUT).read().decode("utf-8", "ignore")


def _initial_data(html: str) -> dict:
    m = re.search(r"ytInitialData\s*=\s*(\{.+?\});\s*</script>", html or "", re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except ValueError:
        return {}


def _walk(o, key: str, out: list) -> list:
    """Every value stored under `key`, anywhere in the tree. YouTube reshuffles the nesting often enough
    that addressing a renderer by path is how scrapers die; finding it by name survives the reshuffles."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key:
                out.append(v)
            _walk(v, key, out)
    elif isinstance(o, list):
        for v in o:
            _walk(v, key, out)
    return out


def _text(o) -> str:
    if isinstance(o, str):
        return o
    if not isinstance(o, dict):
        return ""
    if "simpleText" in o:
        return str(o["simpleText"])
    if "content" in o:
        return str(o["content"])
    return "".join(str(r.get("text") or "") for r in o.get("runs") or [] if isinstance(r, dict))


def _best_img(sources) -> str:
    srcs = [s for s in (sources or []) if isinstance(s, dict) and s.get("url")]
    if not srcs:
        return ""
    url = max(srcs, key=lambda s: int(s.get("width") or 0))["url"]
    return ("https:" + url) if url.startswith("//") else url


_API = {"key": "", "ver": ""}


def _remember_api(html: str) -> None:
    k = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html or "")
    v = re.search(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"', html or "")
    if k and v:
        _API["key"], _API["ver"] = k.group(1), v.group(1)


def _continue(token: str) -> dict:
    """The next page of a section. This is the browser's own «load more» request, unauthenticated."""
    if not token or not _API["key"]:
        return {}
    body = json.dumps({"context": {"client": {"clientName": "WEB", "clientVersion": _API["ver"],
                                              "hl": _HL["hl"], "gl": "ES" if _HL["hl"] == "es" else "US"}},
                       "continuation": token}).encode()
    req = urllib.request.Request("https://www.youtube.com/youtubei/v1/browse?prettyPrint=false&key="
                                 + urllib.parse.quote(_API["key"]), data=body,
                                 headers={"Content-Type": "application/json", "User-Agent": _UA})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=_TIMEOUT).read().decode("utf-8", "ignore"))
    except Exception:
        return {}


# ── parsing numbers and dates ────────────────────────────────────────────────────────────────────────────

_MULT = {"k": 1e3, "mil": 1e3, "m": 1e6, "mill": 1e6, "millones": 1e6, "b": 1e9, "mm": 1e9}


def count(s: str) -> int:
    """«77.2K subscribers» / «77,2 mil suscriptores» → 77200; «2,3 K» → 2300; «1,234 views» → 1234.
    0 when it says nothing. The decimal mark is told apart by position, not by language: a separator
    followed by exactly three digits and no multiplier is a thousands mark, anything else is a decimal."""
    m = re.search(r"(\d[\d.,]*)\s*(k|mil|mill|millones|mm|m|b)?\b", str(s or "").replace("\xa0", " "), re.I)
    if not m:
        return 0
    num, mult = m.group(1), (m.group(2) or "").lower()
    if not mult and re.fullmatch(r"\d{1,3}([.,]\d{3})+", num):
        num = re.sub(r"[.,]", "", num)
    else:
        num = num.replace(".", "#").replace(",", ".").replace("#", ".") if "," in num else num
        if num.count(".") > 1:
            num = num.replace(".", "", num.count(".") - 1)
    try:
        v = float(num)
    except ValueError:
        return 0
    return int(round(v * _MULT.get(mult, 1)))


_UNIT_S = {"second": 1, "sec": 1, "s": 1, "segundo": 1, "seg": 1,
           "minute": 60, "min": 60, "minuto": 60, "m": 60,
           "hour": 3600, "hr": 3600, "h": 3600, "hora": 3600,
           "day": 86400, "d": 86400, "dia": 86400, "día": 86400,
           "week": 604800, "wk": 604800, "w": 604800, "semana": 604800, "sem": 604800,
           "month": 2592000, "mo": 2592000, "mes": 2592000, "meses": 2592000,
           "year": 31536000, "yr": 31536000, "y": 31536000, "año": 31536000, "a": 31536000}


def age_seconds(s: str) -> int:
    """«3h ago» / «2 days ago» / «hace 1 h» / «Emitido hace 5 días» → seconds. -1 when it is not one."""
    t = str(s or "").lower().replace("\xa0", " ")
    m = re.search(r"(\d+)\s*([a-záéíóúñ]+?)(?:e?s)?\s+ago\b", t) or re.search(r"\bhace\s+(\d+)\s*([a-záéíóúñ]+)", t)
    if not m:
        return -1
    unit = m.group(2)
    sec = _UNIT_S.get(unit) or _UNIT_S.get(unit.rstrip("s")) or _UNIT_S.get(re.sub(r"(es|s)$", "", unit))
    return int(m.group(1)) * sec if sec else -1


def _is_subs(t: str) -> bool:
    return bool(re.search(r"subscri|suscript", t, re.I))


def _is_videos(t: str) -> bool:
    return bool(re.search(r"\bv[ií]deos?\b", t, re.I))


# ── reading a channel page ──

#: The channel sections the card can browse, in the order YouTube shows them. Each key is the section's URL
#: path segment, which is how it is recognised on the page — its title is translated, its URL is not. A
#: section is offered only when the channel really has it.
TABS = ("videos", "streams", "shorts", "playlists")


def _header(d: dict) -> dict:
    """Name, picture, subscribers and video count from a channel page's own header."""
    out = {}
    ph = _walk(d, "pageHeaderViewModel", [])
    if ph:
        h = ph[0]
        out["title"] = _text((h.get("title") or {}).get("dynamicTextViewModel", {}).get("text"))
        srcs = _walk(h.get("image") or {}, "sources", [])
        out["avatar"] = _best_img(srcs[0]) if srcs else ""
        for part in _walk(h.get("metadata") or {}, "metadataParts", []):
            for p in part:
                t = _text((p or {}).get("text"))
                if t.startswith("@"):
                    out["handle"] = t
                elif _is_subs(t):
                    out["subscribers"] = count(t)
                elif _is_videos(t):
                    out["videos"] = count(t)
    tabs = []
    for t in _walk(d, "tabRenderer", []):
        url = str(((t.get("endpoint") or {}).get("commandMetadata") or {}).get("webCommandMetadata", {})
                  .get("url") or "")
        key = url.rstrip("/").rsplit("/", 1)[-1] if url else ""
        key = key if key in TABS else ""
        if key and key not in tabs:
            tabs.append(key)
    out["tabs"] = tabs
    return {k: v for k, v in out.items() if v not in ("", None)}


def _items(tab: str, d: dict, now: int) -> list:
    """The videos (or playlists) a section shows, in page order, as flat rows the card can paint."""
    rows = []
    if tab == "shorts":
        for s in _walk(d, "shortsLockupViewModel", []):
            ep = _walk(s, "reelWatchEndpoint", [])
            vid = str(ep[0].get("videoId") or "") if ep else ""
            if not vid:
                continue
            ov = s.get("overlayMetadata") or {}
            rows.append({"id": vid, "kind": "short", "title": _text(ov.get("primaryText")) or "",
                         "views": count(_text(ov.get("secondaryText"))), "age": -1, "ts": 0, "live": False,
                         "duration": ""})
        return rows
    for lk in _walk(d, "lockupViewModel", []):
        cid = str(lk.get("contentId") or "")
        ctype = str(lk.get("contentType") or "")
        if not cid:
            continue
        meta = (lk.get("metadata") or {}).get("lockupMetadataViewModel") or {}
        title = _text(meta.get("title"))
        parts = [_text((p or {}).get("text")) for ps in _walk(meta, "metadataParts", []) for p in ps]
        badges = [str(b.get("text") or "") for b in _walk(lk, "thumbnailBadgeViewModel", [])]
        if ctype.endswith("PLAYLIST"):
            n = next((count(b) for b in badges if _is_videos(b)), 0)
            srcs = _walk(lk.get("contentImage") or {}, "sources", [])
            thumb = _best_img(srcs[0]) if srcs else ""
            rows.append({"id": cid, "kind": "playlist", "title": title, "count": n, "thumb": thumb})
            continue
        age = next((age_seconds(p) for p in parts if age_seconds(p) >= 0), -1)
        views = next((count(p) for p in parts if re.search(r"\d", p) and age_seconds(p) < 0), 0)
        live = (any(b.strip().upper() in ("LIVE", "EN DIRECTO") for b in badges)
                or any(re.search(r"watching|espectador|viendo", p, re.I) for p in parts))
        dur = next((b for b in badges if re.fullmatch(r"\d+(:\d\d)+", b.strip())), "")
        rows.append({"id": cid, "kind": "live" if tab == "streams" else "video", "title": title,
                     "views": views, "age": age, "ts": (now - age) if age >= 0 else 0, "live": live,
                     "duration": dur})
    return rows


def _cont_token(d: dict) -> str:
    """The «load more» token of the GRID — the one inside its `continuationItemRenderer`. A page carries
    other continuations (the sort chips, the «about» panel), and following one of those returns an empty
    page (measured: the last token on the page was one of those and «more» brought nothing). Searched only
    inside the grid; a grid with no token of its own (the shorts shelf) has no next page to offer."""
    grids = (_walk(d, "richGridRenderer", []) + _walk(d, "appendContinuationItemsAction", [])
             + _walk(d, "playlistVideoListRenderer", []) + _walk(d, "gridRenderer", []))
    for ci in _walk(grids, "continuationItemRenderer", []):
        toks = _walk(ci, "continuationCommand", [])
        if toks and toks[0].get("token"):
            return str(toks[0]["token"])
    return ""


def _rss(cid: str) -> dict:
    """videoId → exact upload time (epoch) for the channel's last ~15 uploads. {} on any failure."""
    try:
        xml = _get("https://www.youtube.com/feeds/videos.xml?channel_id=" + urllib.parse.quote(cid))
    except Exception:
        return {}
    out = {}
    for m in re.finditer(r"<yt:videoId>([^<]+)</yt:videoId>.*?<published>([^<]+)</published>", xml, re.S):
        try:
            out[m.group(1)] = calendar.timegm(time.strptime(m.group(2)[:19], "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            continue
    return out
