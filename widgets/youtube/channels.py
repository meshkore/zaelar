#
# youtube/channels — the channels he follows, as CARDS (picture, subscribers, videos) and as a PAGE he can browse:
# videos, lives, shorts and playlists, paged, cached, refreshed on every visit, the last 24 h / 72 h flagged.
#
# ⚠️ The subscription is OURS: nothing here signs in or subscribes on YouTube — every read is the public page plus
# the channel's RSS feed (the only source with EXACT upload times). Fetching and parsing: `channel_fetch.py`.
#
# Pages are CACHED one file per channel, never in `state.json` (which rides every SSE push). A refresh never
# drops old videos: it only PREPENDS what is new and updates what changed.
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

from . import channel_fetch as _f   # fetching + parsing; read through the module so a patch governs

WID = "youtube"


_PAGE = 30            # items the card is served per «more» step
_KEEP = 600           # items kept per section in the cache (oldest dropped past this)
_FRESH_META_S = 6 * 3600


# ── the channel itself ───────────────────────────────────────────────────────────────────────────────────

def find(name: str) -> dict:
    """Resolve a channel NAME (all we store for a follow) to its id, handle, picture and subscribers, via the
    public search filtered to channels. {} when nothing answers."""
    q = (name or "").strip()
    if not q:
        return {}
    try:
        html = _f._get("https://www.youtube.com/results?hl=" + _f._HL["hl"] + "&sp=EgIQAg%253D%253D&search_query="
                    + urllib.parse.quote_plus(q))
    except Exception:
        return {}
    rows = _f._walk(_f._initial_data(html), "channelRenderer", [])
    if not rows:
        return {}
    want = _fold(q)
    # The exact title first: «Ana» must not resolve to «Ana María» when both exist.
    row = next((r for r in rows if _fold(_f._text(r.get("title"))) == want), rows[0])
    # YouTube's own quirk, measured 2026-09-29: in this renderer the subscriber count sits in
    # `videoCountText` and the handle in `subscriberCountText`. Read by SHAPE, never by field name.
    texts = [_f._text(row.get("videoCountText")), _f._text(row.get("subscriberCountText"))]
    subs = next((t for t in texts if _f._is_subs(t)), "")
    handle = next((t for t in texts if t.startswith("@")), "")
    return {"id": str(row.get("channelId") or ""), "title": _f._text(row.get("title")), "handle": handle,
            "avatar": _f._best_img((row.get("thumbnail") or {}).get("thumbnails")), "subscribers": _f.count(subs)}


def _fold(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


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
    html = _f._get("https://www.youtube.com/channel/%s/%s?hl=%s" % (urllib.parse.quote(cid), tab, _f._HL["hl"]))
    _f._remember_api(html)
    d = _f._initial_data(html)
    head = _f._header(d)
    if head:
        c.setdefault("meta", {}).update({k: v for k, v in head.items() if k != "tabs"})
        if head.get("tabs"):
            c["tabs"] = head["tabs"]
    sec = c.setdefault("sections", {}).setdefault(tab, {"items": [], "cont": ""})
    fresh = _f._items(tab, d, now)
    had_rows = bool(sec.get("items"))
    sec["items"], new = _merge(sec.get("items") or [], fresh)
    if not had_rows or not sec.get("cont"):
        sec["cont"] = _f._cont_token(d)
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
    tab = view.get("tab") if view.get("tab") in _f.TABS else tabs[0]
    tabs = [t for t in _f.TABS if t in tabs]                 # YouTube's own order, whatever the page listed
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
        _f.set_lang(p.get("hl"))

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
        followed = ch is not None
        if ch is None:
            # A channel he does not follow still OPENS (live 2026-10-28: «show me the channel of SpaceX» answered
            # «No sigo ese canal» four turns in a row). Resolved by name on the public search, never stored: following
            # stays his explicit act (`follow_channel`).
            if not name:
                return {"ok": False, "error": "no_channel", "message": "Dime qué canal."}
            hit = find(name)
            if not hit.get("id"):
                return {"ok": False, "error": "not_found", "channel": name,
                        "channels": [c.get("name") for c in db.get("channels") or []],
                        "message": "No encuentro ese canal en YouTube."}
            ch = {"name": hit.get("title") or name, "id": hit["id"],
                  "meta": {k: hit[k] for k in ("handle", "avatar", "subscribers") if hit.get(k)}}
        if not ch.get("id") and not _resolve(ch):
            store.save(WID, db)
            return {"ok": False, "error": "not_found", "channel": ch.get("name"),
                    "message": "No encuentro ese canal en YouTube."}
        tab = str(p.get("tab") or "").strip().lower()
        db["channel_view"] = {"id": ch["id"], "name": ch.get("name") or "",
                              "tab": tab if tab in _f.TABS else "", "limit": _PAGE,
                              "rev": int(time.time() * 1000), "new_ids": []}
        db["goto_tab"] = {"tab": "subs", "seq": int(time.time() * 1000)}
        store.save(WID, db)
        # The card asks for `refresh_channel` right after this, with its loader up: opening is instant from
        # the cache, and looking for what is new is a separate, visible step.
        return {"ok": True, "channel": ch.get("name"), "id": ch["id"], "followed": followed}

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
                if tab not in _f.TABS:
                    return {"ok": False, "error": "bad_tab", "tabs": list(_f.TABS)}
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
                _fetch_section(cid, tab if tab in _f.TABS else "videos", cache, now)
                if tab != "videos" and "videos" in (cache.get("tabs") or []):
                    _fetch_section(cid, "videos", cache, now)
                _apply_rss(cache, _f._rss(cid))
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
        if not _f._API["key"]:
            _f._remember_api(_f._get("https://www.youtube.com/channel/%s/videos?hl=%s"
                               % (urllib.parse.quote(str(view.get("id") or "")), _f._HL["hl"])))
        d = _f._continue(sec["cont"])
        more = _f._items(tab, d, now)
        if not more:
            sec["cont"] = ""
            break
        have = {r.get("id") for r in sec.get("items") or []}
        sec["items"] = ((sec.get("items") or []) + [r for r in more if r.get("id") not in have])[:_KEEP]
        sec["cont"] = _f._cont_token(d)


def _fetch_playlist(cache: dict, pl: str, now: int) -> None:
    html = _f._get("https://www.youtube.com/playlist?hl=" + _f._HL["hl"] + "&list=" + urllib.parse.quote(pl))
    _f._remember_api(html)
    d = _f._initial_data(html)
    rows = _f._items("videos", d, now)
    sec = cache.setdefault("playlists", {}).setdefault(pl, {"items": [], "cont": ""})
    heads = _f._walk(d, "pageHeaderViewModel", [])
    title = _f._text(((heads[0].get("title") or {}).get("dynamicTextViewModel") or {}).get("text")) if heads else ""
    if title:
        sec["title"] = title
    sec["items"], _ = _merge(sec.get("items") or [], rows)
    sec["cont"] = _f._cont_token(d)
    sec["fetched_at"] = now
