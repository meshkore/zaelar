#
# youtube/channels — the channels he follows, as CARDS and as a PAGE he can browse.
#
# Operator, 2026-09-29: the subscriptions tab was a list of names. He wants a card per channel (its picture,
# how many subscribers, how many videos) and, on a click, the channel's own page — its videos, its lives, its
# shorts, its playlists — paged, cached, and refreshed every time he walks in, with what came out in the last
# 24 h and 72 h flagged.
#
# ⚠️ The subscription is OURS and stays ours. Nothing here signs in, and nothing here subscribes to anything
# on YouTube: every read is the public page any browser sees (the same class of fetch `data._search_many`
# already makes) plus the channel's public RSS feed, which is the only source with EXACT upload times. «No
# quiero que te suscribas oficialmente en el canal de YouTube … nosotros manejamos nuestras propias
# suscripciones».
#
# The pages are CACHED in the widget's own data directory, one file per channel, and never in `state.json`:
# `view_data` serves the whole state on every repaint, and ten channels × four tabs × a few hundred videos
# would ride every SSE push. The state only says WHICH channel page is open; `page()` reads that one file.
# Old videos are never dropped on a refresh — «los anteriores siempre van a estar ahí» — a refresh only
# PREPENDS what is new and updates what changed (a view count, a title).
#
# Stdlib only (the validator checks every import of a widget module, lazy ones included).
#
import calendar
import json
import os
import re
import time
import urllib.parse
import urllib.request

from .. import store

WID = "youtube"

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/122.0 Safari/537.36")
# The pages are asked for in the CARD's language (es | en). Not a nicety: YouTube translates video titles
# to the requested language, so asking in English showed a Spanish channel's videos under English titles
# (measured 2026-09-29). The two languages' counts and relative dates («2,3 K», «hace 1 h» / «2.3K», «1h
# ago») are parsed into numbers here and formatted by the card; sections are recognised by their URL, never
# by their translated title.
_HL = {"hl": "es"}


def _headers() -> dict:
    lang = "es-ES,es;q=0.9" if _HL["hl"] == "es" else "en-US,en;q=0.9"
    return {"User-Agent": _UA, "Accept-Language": lang, "Cookie": "CONSENT=YES+1; SOCS=CAI"}


def set_lang(hl) -> None:
    _HL["hl"] = "en" if str(hl or "").lower().startswith("en") else "es"
_TIMEOUT = 8

#: The channel sections the card can browse, in the order YouTube shows them. Each key is the section's URL
#: path segment, which is how it is recognised on the page — its title is translated, its URL is not. A
#: section is offered only when the channel really has it.
TABS = ("videos", "streams", "shorts", "playlists")

_PAGE = 30            # items the card is served per «more» step
_KEEP = 600           # items kept per section in the cache (oldest dropped past this)
_FRESH_META_S = 6 * 3600


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


# ── the channel itself ───────────────────────────────────────────────────────────────────────────────────

def find(name: str) -> dict:
    """Resolve a channel NAME (all we store for a follow) to its id, handle, picture and subscribers, via the
    public search filtered to channels. {} when nothing answers."""
    q = (name or "").strip()
    if not q:
        return {}
    try:
        html = _get("https://www.youtube.com/results?hl=" + _HL["hl"] + "&sp=EgIQAg%253D%253D&search_query="
                    + urllib.parse.quote_plus(q))
    except Exception:
        return {}
    rows = _walk(_initial_data(html), "channelRenderer", [])
    if not rows:
        return {}
    want = _fold(q)
    # The exact title first: «Ana» must not resolve to «Ana María» when both exist.
    row = next((r for r in rows if _fold(_text(r.get("title"))) == want), rows[0])
    # YouTube's own quirk, measured 2026-09-29: in this renderer the subscriber count sits in
    # `videoCountText` and the handle in `subscriberCountText`. Read by SHAPE, never by field name.
    texts = [_text(row.get("videoCountText")), _text(row.get("subscriberCountText"))]
    subs = next((t for t in texts if _is_subs(t)), "")
    handle = next((t for t in texts if t.startswith("@")), "")
    return {"id": str(row.get("channelId") or ""), "title": _text(row.get("title")), "handle": handle,
            "avatar": _best_img((row.get("thumbnail") or {}).get("thumbnails")), "subscribers": count(subs)}


def _fold(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


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


# ── the cache ────────────────────────────────────────────────────────────────────────────────────────────

def _cache_path(cid: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", cid)[:64] or "unknown"
    d = os.path.join(store.data_dir(WID), "channels")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, safe + ".json")


def _load_cache(cid: str) -> dict:
    try:
        with open(_cache_path(cid), encoding="utf-8") as f:
            c = json.load(f)
        return c if isinstance(c, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cache(cid: str, c: dict) -> None:
    p = _cache_path(cid)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)
    os.replace(tmp, p)


def _merge(old: list, fresh: list) -> "tuple[list, int]":
    """Fresh first page in front, every older row kept behind it. Returns (rows, how many are new)."""
    seen = {r.get("id") for r in fresh}
    before = {r.get("id"): r for r in old}
    for r in fresh:                                   # keep an exact time learned earlier (RSS) over a guess
        prev = before.get(r.get("id"))
        if prev and prev.get("exact") and not r.get("exact"):
            r["ts"], r["exact"] = prev.get("ts"), True
    new = sum(1 for r in fresh if r.get("id") not in before)
    return (fresh + [r for r in old if r.get("id") not in seen])[:_KEEP], new


def _fetch_section(cid: str, tab: str, c: dict, now: int) -> int:
    """Refresh one section's FIRST page into the cache. Returns how many rows are new."""
    html = _get("https://www.youtube.com/channel/%s/%s?hl=%s" % (urllib.parse.quote(cid), tab, _HL["hl"]))
    _remember_api(html)
    d = _initial_data(html)
    head = _header(d)
    if head:
        c.setdefault("meta", {}).update({k: v for k, v in head.items() if k != "tabs"})
        if head.get("tabs"):
            c["tabs"] = head["tabs"]
    sec = c.setdefault("sections", {}).setdefault(tab, {"items": [], "cont": ""})
    fresh = _items(tab, d, now)
    had_rows = bool(sec.get("items"))
    sec["items"], new = _merge(sec.get("items") or [], fresh)
    if not had_rows or not sec.get("cont"):
        sec["cont"] = _cont_token(d)
    sec["fetched_at"] = now
    return new if had_rows else 0


def _apply_rss(c: dict, exact: dict) -> None:
    for sec in (c.get("sections") or {}).values():
        for r in sec.get("items") or []:
            ts = exact.get(r.get("id"))
            if ts:
                r["ts"], r["exact"] = ts, True


# ── what the card reads ──────────────────────────────────────────────────────────────────────────────────

def cards(db: dict) -> list:
    """The followed channels as cards: whatever we know of each (picture, subscribers, videos). A channel we
    have not resolved yet still gets its card — with its name, which is what he followed."""
    out = []
    for ch in db.get("channels") or []:
        m = ch.get("meta") or {}
        out.append({"name": ch.get("name") or "", "id": ch.get("id") or "", "handle": m.get("handle") or "",
                    "avatar": m.get("avatar") or "", "subscribers": int(m.get("subscribers") or 0),
                    "videos": int(m.get("videos") or 0), "resolved": bool(ch.get("id")),
                    "tried": bool(ch.get("resolved_at"))})
    return out


def page(db: dict) -> dict:
    """The open channel page — ONE channel, ONE section, the first `limit` rows — or {} when none is open."""
    view = db.get("channel_view") or {}
    cid = str(view.get("id") or "")
    if not cid:
        return {}
    c = _load_cache(cid)
    tabs = c.get("tabs") or ["videos"]
    tab = view.get("tab") if view.get("tab") in TABS else tabs[0]
    tabs = [t for t in TABS if t in tabs]                 # YouTube's own order, whatever the page listed
    limit = max(_PAGE, int(view.get("limit") or _PAGE))
    out = {"id": cid, "name": view.get("name") or "", "meta": c.get("meta") or {}, "tabs": tabs, "tab": tab,
           "refreshed_at": int(c.get("refreshed_at") or 0), "rev": int(view.get("rev") or 0)}
    pl = str(view.get("playlist") or "")
    if pl:
        sec = (c.get("playlists") or {}).get(pl) or {}
        out["playlist"] = {"id": pl, "title": sec.get("title") or view.get("playlist_title") or ""}
    else:
        sec = (c.get("sections") or {}).get(tab) or {}
    items = sec.get("items") or []
    out["items"] = items[:limit]
    out["total"] = len(items)
    out["has_more"] = len(items) > limit or bool(sec.get("cont"))
    out["loaded"] = "fetched_at" in sec
    out["new_ids"] = list(view.get("new_ids") or [])
    return out


# ── the actions ──────────────────────────────────────────────────────────────────────────────────────────

def _followed(db: dict, name: str) -> "dict | None":
    n = _fold(name)
    chans = db.get("channels") or []
    return (next((c for c in chans if _fold(c.get("name")) == n), None)
            or next((c for c in chans if n and n in _fold(c.get("name"))), None)
            or next((c for c in chans if c.get("id") and c.get("id") == name), None))


def _resolve(ch: dict) -> bool:
    """Fill a followed row's id and card facts. True when it now has an id."""
    hit = find(ch.get("name") or "")
    ch["resolved_at"] = int(time.time())
    if not hit.get("id"):
        return bool(ch.get("id"))
    ch["id"] = hit["id"]
    m = ch.setdefault("meta", {})
    for k in ("handle", "avatar", "subscribers"):
        if hit.get(k):
            m[k] = hit[k]
    return True


def apply(action: str, p: dict, db: dict) -> "dict | None":
    """This module's actions. None when `action` is not one of them (the library.apply contract)."""
    if p.get("hl"):
        set_lang(p.get("hl"))

    if action == "sync_channels":
        # Fired by the card for followed channels that have no card facts yet. Bounded: at most three per
        # call, and a channel tried in the last six hours is not tried again, so a name YouTube cannot
        # resolve never becomes a request on every repaint.
        now = int(time.time())
        todo = [c for c in db.get("channels") or []
                if (not c.get("id") or not (c.get("meta") or {}).get("videos"))
                and now - int(c.get("resolved_at") or 0) > _FRESH_META_S][:3]
        done = 0
        for ch in todo:
            if not ch.get("id"):
                _resolve(ch)
            if ch.get("id"):
                try:
                    cache = _load_cache(ch["id"])
                    _fetch_section(ch["id"], "videos", cache, now)
                    _save_cache(ch["id"], cache)
                    ch.setdefault("meta", {}).update(cache.get("meta") or {})
                    ch["resolved_at"] = now
                    done += 1
                except Exception:
                    ch["resolved_at"] = now
        store.save(WID, db)
        return {"ok": True, "synced": done, "pending": len(todo) - done}

    if action == "open_channel":
        name = str(p.get("channel") or p.get("name") or p.get("item") or "").strip()
        ch = _followed(db, name)
        if ch is None:
            return {"ok": False, "error": "not_followed", "channel": name,
                    "channels": [c.get("name") for c in db.get("channels") or []],
                    "message": "No sigo ese canal."}
        if not ch.get("id") and not _resolve(ch):
            store.save(WID, db)
            return {"ok": False, "error": "not_found", "channel": ch.get("name"),
                    "message": "No encuentro ese canal en YouTube."}
        tab = str(p.get("tab") or "").strip().lower()
        db["channel_view"] = {"id": ch["id"], "name": ch.get("name") or "",
                              "tab": tab if tab in TABS else "", "limit": _PAGE,
                              "rev": int(time.time() * 1000), "new_ids": []}
        db["goto_tab"] = {"tab": "subs", "seq": int(time.time() * 1000)}
        store.save(WID, db)
        # The card asks for `refresh_channel` right after this, with its loader up: opening is instant from
        # the cache, and looking for what is new is a separate, visible step.
        return {"ok": True, "channel": ch.get("name"), "id": ch["id"]}

    if action == "close_channel":
        db["channel_view"] = {}
        store.save(WID, db)
        return {"ok": True}

    if action in ("channel_tab", "channel_more", "channel_playlist", "refresh_channel"):
        view = db.get("channel_view") or {}
        cid = str(view.get("id") or "")
        if not cid:
            return {"ok": False, "error": "no_channel_open", "message": "No hay ningún canal abierto."}
        now = int(time.time())
        cache = _load_cache(cid)
        try:
            if action == "channel_tab":
                tab = str(p.get("tab") or "").strip().lower()
                if tab not in TABS:
                    return {"ok": False, "error": "bad_tab", "tabs": list(TABS)}
                view.update({"tab": tab, "limit": _PAGE, "playlist": "", "playlist_title": "", "new_ids": []})
                if not ((cache.get("sections") or {}).get(tab) or {}).get("fetched_at"):
                    _fetch_section(cid, tab, cache, now)
            elif action == "channel_playlist":
                pl = str(p.get("playlist") or p.get("id") or "").strip()
                if not pl:
                    view.update({"playlist": "", "playlist_title": "", "limit": _PAGE})
                else:
                    view.update({"playlist": pl, "playlist_title": str(p.get("title") or "")[:200],
                                 "limit": _PAGE})
                    _fetch_playlist(cache, pl, now)
            elif action == "channel_more":
                view["limit"] = int(view.get("limit") or _PAGE) + _PAGE
                _fill_to(cache, view, now)
            else:                                       # refresh_channel — «buscando últimos vídeos del canal»
                tab = view.get("tab") or (cache.get("tabs") or ["videos"])[0]
                before = {r.get("id") for s in (cache.get("sections") or {}).values()
                          for r in s.get("items") or []}
                first_time = not before
                _fetch_section(cid, tab if tab in TABS else "videos", cache, now)
                if tab != "videos" and "videos" in (cache.get("tabs") or []):
                    _fetch_section(cid, "videos", cache, now)
                _apply_rss(cache, _rss(cid))
                cache["refreshed_at"] = now
                after = [r.get("id") for s in (cache.get("sections") or {}).values()
                         for r in s.get("items") or []]
                view["new_ids"] = [] if first_time else [i for i in after if i not in before][:100]
                ch = _followed(db, cid) or _followed(db, view.get("name") or "")
                if ch is not None:
                    ch.setdefault("meta", {}).update(cache.get("meta") or {})
        except Exception as e:
            db["channel_view"] = view
            view["rev"] = int(time.time() * 1000)
            store.save(WID, db)
            return {"ok": False, "error": "fetch_failed", "detail": str(e)[:120],
                    "message": "YouTube no me ha contestado; enseño lo que ya tenía."}
        _save_cache(cid, cache)
        view["rev"] = int(time.time() * 1000)
        db["channel_view"] = view
        store.save(WID, db)
        return {"ok": True, "tab": view.get("tab"), "new": len(view.get("new_ids") or []),
                "refreshed_at": cache.get("refreshed_at")}

    return None


def _fill_to(cache: dict, view: dict, now: int) -> None:
    """Make sure the cache holds `view.limit` rows of the open section, walking continuations as needed."""
    pl = view.get("playlist")
    if pl:
        sec = (cache.get("playlists") or {}).get(pl) or {}
    else:
        tab = view.get("tab") or (cache.get("tabs") or ["videos"])[0]
        sec = cache.setdefault("sections", {}).setdefault(tab, {"items": [], "cont": ""})
    tab = "videos" if pl else (view.get("tab") or "videos")
    guard = 0
    while len(sec.get("items") or []) < int(view.get("limit") or _PAGE) and sec.get("cont") and guard < 4:
        guard += 1
        if not _API["key"]:
            _remember_api(_get("https://www.youtube.com/channel/%s/videos?hl=%s"
                               % (urllib.parse.quote(str(view.get("id") or "")), _HL["hl"])))
        d = _continue(sec["cont"])
        more = _items(tab, d, now)
        if not more:
            sec["cont"] = ""
            break
        have = {r.get("id") for r in sec.get("items") or []}
        sec["items"] = ((sec.get("items") or []) + [r for r in more if r.get("id") not in have])[:_KEEP]
        sec["cont"] = _cont_token(d)


def _fetch_playlist(cache: dict, pl: str, now: int) -> None:
    html = _get("https://www.youtube.com/playlist?hl=" + _HL["hl"] + "&list=" + urllib.parse.quote(pl))
    _remember_api(html)
    d = _initial_data(html)
    rows = _items("videos", d, now)
    sec = cache.setdefault("playlists", {}).setdefault(pl, {"items": [], "cont": ""})
    heads = _walk(d, "pageHeaderViewModel", [])
    title = _text(((heads[0].get("title") or {}).get("dynamicTextViewModel") or {}).get("text")) if heads else ""
    if title:
        sec["title"] = title
    sec["items"], _ = _merge(sec.get("items") or [], rows)
    sec["cont"] = _cont_token(d)
    sec["fetched_at"] = now
