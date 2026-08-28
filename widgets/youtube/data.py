#
# youtube — EMBEDDED YouTube player in the canvas (a real <iframe> that PLAYS, not a capture).
# Video is controlled by VOICE: FlashBrain calls apply_action (tool widget_data) and here we store desired
# STATE/command in the store; the client (widget.js) applies it to the player through postMessage (YouTube IFrame API,
# NO library). data.py is pure server code (stdlib) — it never touches the player.
#
import re
import time
import unicodedata
import urllib.parse
import urllib.request

from .. import store

WID = "youtube"

# Seed: BLANK player by default (no video) until the operator requests one.
_SEED = {
    "videoId": "",
    "title": "",
    "url": "",
    "channel": "",
    "published": "",
    "latest": False,
    "volume": 70,
    "muted": True,      # browser autoplay requires starting muted; "unmute" to hear it
    "paused": True,
    "last_cmd": "",
    "cmd_seq": 0,
    "loading": False,     # V2-062 fix: "load" search takes a few seconds (network); without this, the card looked
    "loading_query": "",  # COMPLETELY empty with no signal that something was happening (real bug 2026-07-23).
    # V2-366 — the PLAYLIST: linear queue of videos played one after another (operator asked for musica-level lists).
    "list": [],           # [{videoId, title, channel, published, url, added_at}]
    # V2-401 — the player's own last error (IFrame API onError: 101/150 = embedding disabled). "" = healthy.
    # Written back by widget.js so "is it producing?" answers the player's reported reality, not our intent:
    # the operator's screenshot showed "This video is unavailable" while the declared state said playing.
    "player_error": "",
    "pos": -1,            # index in `list` of the item playing (or last played); -1 = current video is not from the list
    "adding": "",         # an `add` by name is searching the network right now (visible state, like `loading` for load)
    "list_filter": "",    # display-only filter over the list (filter_list); never touches the list itself
    # V2-467 — the list's NAME. `musica` has named playlists and this player did not, so «llámala la de la
    # tarde» had nowhere to land: the model found no action, and the escalate catalogue's own «no estar en
    # el catálogo NO es motivo para negarte» sent a two-link queue to a Brain Worker (measured, and the
    # scenario calls escalating this a FAILURE — it is a rail, V2-042). "" = the card shows its generic title.
    "list_name": "",
}

_YT_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([0-9A-Za-z_-]{11})"
)


def _extract_id(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    m = _YT_RE.search(s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", s):          # already a bare id
        return s
    return ""


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return s.lower().strip()


def _resolve_item(lst: list, item) -> "int | None":
    """item = 1-based index ("2") or text matched against title/channel of a list entry. Never invents."""
    if item is None:
        return None
    s = str(item).strip()
    if not s:
        return None
    if s.isdigit():
        i = int(s) - 1
        return i if 0 <= i < len(lst) else None
    n = _norm(s)
    for i, it in enumerate(lst):                       # exact title
        if n == _norm(it.get("title")):
            return i
    for i, it in enumerate(lst):                       # contained in title+channel
        hay = _norm(" ".join([it.get("title") or "", it.get("channel") or ""]))
        if n in hay:
            return i
    return None


def _oembed_title(vid: str) -> dict:
    """Title/channel of a video added by bare LINK, via the public oembed endpoint. Best-effort, fail-open:
    a pasted link must land in the list even with the network down — the short URL is the honest fallback."""
    out = {"title": "", "channel": ""}
    try:
        url = ("https://www.youtube.com/oembed?format=json&url="
               + urllib.parse.quote_plus("https://www.youtube.com/watch?v=" + vid))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        import json
        d = json.loads(urllib.request.urlopen(req, timeout=4).read().decode("utf-8", "ignore"))
        out["title"] = str(d.get("title") or "").strip()[:140]
        out["channel"] = str(d.get("author_name") or "").strip()[:80]
    except Exception:
        pass
    return out


# Requests the MOST RECENT video (e.g. "the latest video by Jose Luis Carpatos") → sort by upload date.
_LATEST_RE = re.compile(r"\b(?:[uú]ltim[oa]s?|m[aá]s\s+recientes?|reciente|nuevo|last|latest|newest)\b", re.I)


def _unesc(s: str) -> str:
    """Decode \\uXXXX sequences that YouTube sometimes embeds in JSON, without touching already decoded UTF-8."""
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s or "")


def _search_many(q: str, n: int = 5) -> list:
    """Best-effort: top-N DISTINCT videos for a phrase, in the results-page order. Stdlib, 6s, fail-open ([]).

    One fetch: the results page already carries every candidate; only the parse changes with `n`. Kept separate
    from `_search_id` so the single-video contract (V2-057 verifiable metadata) stays byte-identical while a
    media SEARCH — "find me videos about X", where the operator wants to CHOOSE — can land several candidates
    in the player's list instead of a generic results sheet (V2-402: content you watch/listen lives in its
    dedicated widget; the sheet is for information).
    """
    q = (q or "").strip()
    if not q or n <= 0:
        return []
    try:
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(q)
        if _LATEST_RE.search(q):                         # sort by upload date (sp=CAI%3D)
            url += "&sp=CAI%3D"
        req = urllib.request.Request(url, headers={
            "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"),
            "Accept-Language": "es-ES,es;q=0.9",
        })
        html = urllib.request.urlopen(req, timeout=6).read().decode("utf-8", "ignore")
    except Exception:
        return []
    out, seen = [], set()
    for m in re.finditer(r'"videoId":"([0-9A-Za-z_-]{11})"', html):
        vid = m.group(1)
        if vid in seen:                                  # the page repeats each id many times (thumbs, params)
            continue
        seen.add(vid)
        # videoRenderer block for THIS video: title, channel and publication date are extracted from it.
        blk = html[m.start(): m.start() + 2500]
        t = re.search(r'"title":\{"runs":\[\{"text":"([^"]{2,140})"', blk)
        ch = re.search(r'"(?:ownerText|longBylineText)":\{"runs":\[\{"text":"([^"]{1,80})"', blk)
        pub = re.search(r'"publishedTimeText":\{"simpleText":"([^"]{2,40})"', blk)
        out.append({"videoId": vid, "title": _unesc(t.group(1)) if t else "",
                    "channel": _unesc(ch.group(1)) if ch else "",
                    "published": _unesc(pub.group(1)) if pub else ""})
        if len(out) >= n:
            break
    return out


def _search_id(q: str) -> dict:
    """Best-effort: resolve a phrase ("Messi goal") to the first YouTube video. Stdlib, 6s, fail-open.
    If the phrase asks for someone's MOST RECENT video ("the latest from ..."), sort by upload date.
    Returns {videoId,title,channel,published,latest} — publication date lets the operator VERIFY it is the correct
    video (V2-057: do not execute blindly; deliver a checkable result at a glance)."""
    q = (q or "").strip()
    out = {"videoId": "", "title": "", "channel": "", "published": "", "latest": bool(_LATEST_RE.search(q))}
    hits = _search_many(q, 1)
    if hits:
        h = hits[0]
        out.update({"videoId": h["videoId"], "title": h["title"] or q,
                    "channel": h["channel"], "published": h["published"]})
    return out


def _seed() -> dict:
    """Fresh copy of the seed. `dict(_SEED)` is SHALLOW: since the seed carries a mutable `list`, handing out
    the same list object meant an `append` on a "fresh" db mutated the module seed itself — every later fresh
    load inherited it (caught by the V2-366 tests before shipping)."""
    d = dict(_SEED)
    d["list"] = []
    return d


def _load() -> dict:
    db = store.load(WID, _seed())
    for k, v in _SEED.items():                          # normalize missing fields (old store)
        db.setdefault(k, [] if isinstance(v, list) else v)
    return db


def view_data(q: str = "") -> dict:
    try:
        return _load()
    except Exception as e:
        return {**_seed(), "error": str(e)[:120]}


def ref_index() -> list:
    """The videos in the LIST, so the brain can name one instead of guessing an index (`widgets/refs.py`).

    The only member of the media family that did not publish its items — measured 2026-08-28 comparing the
    three: `musica` and `imagenes` answer, this one returned "". Two consequences, and the second is the
    expensive one: «pon la tercera» / «quita la de los Beatles» had nothing to resolve against (and the
    model must never invent an id, V2-026); and with the card OPEN AND EMPTY the brief could not say so,
    which is exactly the «doy por entregado lo que no está» that V2-377/380/383 each paid for once.

    `field: "item"` matches `play_item`/`remove`/`move`'s own payload key, and the label is the title the
    operator would actually say. The CURRENT one is marked in the hint: «la que suena» is a real way to
    refer to a video, and without it the brain cannot tell which of twelve is playing."""
    try:
        db = _load()
    except Exception:  # noqa: BLE001
        return []
    cur = int(db.get("pos") or -1)
    out = []
    for i, it in enumerate(db.get("list") or []):
        titulo = str(it.get("title") or it.get("url") or it.get("videoId") or "").strip()
        if not titulo:
            continue
        pistas = [p for p in (str(it.get("channel") or "").strip(),
                              "la que suena" if i == cur else "") if p]
        out.append({"id": str(i + 1), "label": titulo[:80], "field": "item",
                    "hint": " · ".join(pistas)})
    return out


def _bump(db: dict, cmd: str) -> dict:
    db["last_cmd"] = cmd
    db["cmd_seq"] = int(db.get("cmd_seq") or 0) + 1
    store.save(WID, db)
    return {"ok": True, "cmd": cmd, "videoId": db.get("videoId"), "title": db.get("title"),
            "volume": db.get("volume"), "muted": db.get("muted"), "paused": db.get("paused")}


def _play_pos(db: dict, i: int, cmd: str) -> dict:
    """Make list item i the CURRENT video and play it. The card fields (title/channel/published) become the
    item's own, so the on-screen verification (V2-057) keeps working when the list drives playback."""
    it = db["list"][i]
    db["player_error"] = ""   # a DIFFERENT video: the old player error says nothing about it (V2-401)
    db["videoId"] = it.get("videoId") or ""
    db["url"] = it.get("url") or ("https://www.youtube.com/watch?v=" + db["videoId"])
    db["title"] = it.get("title") or db["url"]
    db["channel"] = it.get("channel") or ""
    db["published"] = it.get("published") or ""
    db["latest"] = False
    db["pos"] = i
    db["paused"] = False
    r = _bump(db, cmd)
    r["position"] = i + 1
    return r


def apply_action(action: str, payload: dict = None) -> dict:
    p = payload or {}
    db = _load()

    if action == "load":
        raw = str(p.get("url") or p.get("videoId") or "").strip()
        vid = _extract_id(raw)
        title = str(p.get("title") or "").strip()
        channel, published, latest = "", "", False
        if not vid:                                     # not URL/id → search by name
            q = str(p.get("query") or p.get("q") or raw or "").strip()
            # Real LOADER (bug 2026-07-23, "there is no loader showing that you are searching"): _search_id scrapes
            # the network (several seconds) — without this the card looked COMPLETELY empty in the meantime,
            # indistinguishable from "nothing requested". Save+emit NOW (before network) so widget.js paints the
            # spinner immediately; the final load turns it off.
            db["loading"], db["loading_query"] = True, q
            store.save(WID, db)
            r = _search_id(q)
            vid = r["videoId"]
            latest = r["latest"]
            if vid and not title:
                title = r["title"]
            channel, published = r["channel"], r["published"]
        db["loading"], db["loading_query"] = False, ""
        if not vid:
            store.save(WID, db)                          # turn off loader even if nothing was found
            return {"ok": False, "error": "no_video", "message": "No encontré ese vídeo."}
        db["player_error"] = ""   # fresh video, clean slate (V2-401)
        db["videoId"] = vid
        db["url"] = "https://www.youtube.com/watch?v=" + vid
        db["title"] = title or db["url"]
        db["channel"] = channel                          # V2-057: VERIFIABLE metadata in the card
        db["published"] = published                      # e.g. "2 days ago" — confirms it is the correct one
        db["latest"] = latest                            # most recent requested (date order)
        # If the loaded video happens to BE in the list, `next` continues from there; otherwise the list is a
        # queue that will start after this video ends (pos=-1 → ended plays list[0]).
        db["pos"] = next((i for i, it in enumerate(db.get("list") or []) if it.get("videoId") == vid), -1)
        db["paused"] = False
        return _bump(db, "load")

    if action == "add":
        # V2-366 — into the LIST, never into the player: like YouTube's own "Add to queue", adding NEVER starts
        # playback (this is also what keeps `add` usable with the agent stopped — it is not a `produce` op).
        raw = str(p.get("url") or p.get("videoId") or "").strip()
        if isinstance(p.get("urls"), list):              # explicit list payload also accepted
            raw = " ".join(str(u) for u in p["urls"]) + " " + raw
        # SEVERAL links in one payload (V2-384 bis, measured 2026-08-27 14:38): the operator pastes two urls in
        # one sentence and the model emits ONE `add` with the pasted text — taking only the first id silently
        # dropped the rest. Every id in the text lands; the single-id path below stays byte-identical.
        vids = _YT_RE.findall(raw)
        if len(vids) > 1:
            added, positions = [], []
            lst = db.setdefault("list", [])
            for v in vids:
                if any(it.get("videoId") == v for it in lst):
                    continue
                meta = _oembed_title(v)
                seq = max((int(it.get("added_seq") or 0) for it in lst), default=0) + 1
                lst.append({"videoId": v, "title": meta["title"] or ("youtu.be/" + v),
                            "channel": meta["channel"], "published": "",
                            "url": "https://www.youtube.com/watch?v=" + v,
                            "added_at": int(time.time()), "added_seq": seq})
                added.append(lst[-1]["title"]); positions.append(len(lst))
            store.save(WID, db)
            return {"ok": True, "added": added, "positions": positions, "count": len(lst)}
        vid = _extract_id(raw)
        title = str(p.get("title") or "").strip()
        channel, published = "", ""
        if vid and not title:
            meta = _oembed_title(vid)                   # a pasted bare link still deserves a readable row
            title, channel = meta["title"], meta["channel"]
        if not vid:                                     # not URL/id → search by name
            q = str(p.get("query") or p.get("q") or raw or "").strip()
            if not q:
                return {"ok": False, "error": "no_video", "message": "Dime qué vídeo añado (enlace o nombre)."}
            db["adding"] = q                            # visible state while the network search runs
            store.save(WID, db)
            r = _search_id(q)
            db["adding"] = ""
            vid = r["videoId"]
            if vid and not title:
                title = r["title"]
            channel, published = r["channel"], r["published"]
        if not vid:
            store.save(WID, db)                          # turn the "adding" state off even on failure
            return {"ok": False, "error": "no_video", "message": "No encontré ese vídeo."}
        lst = db.setdefault("list", [])
        for i, it in enumerate(lst):                    # dedup by videoId: a repeated add is almost always a retry
            if it.get("videoId") == vid:
                store.save(WID, db)
                return {"ok": True, "already_in_list": True, "position": i + 1,
                        "title": it.get("title"), "count": len(lst)}
        url = "https://www.youtube.com/watch?v=" + vid
        # `added_seq` is the insertion order: several adds can land in the same SECOND, so `added_at` alone
        # cannot restore it (measured: sort_list by=added left a same-second batch in its current order).
        seq = max((int(it.get("added_seq") or 0) for it in lst), default=0) + 1
        lst.append({"videoId": vid, "title": title or ("youtu.be/" + vid), "channel": channel,
                    "published": published, "url": url, "added_at": int(time.time()), "added_seq": seq})
        if db.get("videoId") and db.get("pos", -1) < 0:
            # current video was loaded outside the list; keep it that way (ended → list[0] still correct)
            pass
        store.save(WID, db)
        return {"ok": True, "position": len(lst), "title": lst[-1]["title"], "count": len(lst)}

    if action == "search":
        # V2-402 — a MEDIA search lands in the PLAYER, not in the results sheet. "Find me videos about X" means
        # the operator wants to CHOOSE: several candidates go into the list (same rows as `add`, so play_item /
        # next / remove all work on them), and NOTHING starts playing — V2-366's rule (adding never autoplays)
        # holds for searching too. Player state is untouched on purpose: a search must not interrupt playback.
        q = str(p.get("query") or p.get("q") or "").strip()
        if not q:
            return {"ok": False, "error": "no_query", "message": "Dime qué vídeos busco."}
        try:
            n = int(p.get("n") or 5)
        except Exception:
            n = 5
        n = max(1, min(n, 8))
        db["adding"] = q                                # visible state while the network search runs (as `add`)
        store.save(WID, db)
        hits = _search_many(q, n)
        db["adding"] = ""
        if not hits:
            store.save(WID, db)                          # turn the state off even when nothing was found
            return {"ok": False, "error": "no_video", "message": "No encontré vídeos de eso."}
        lst = db.setdefault("list", [])
        added, positions = [], []
        for h in hits:
            if any(it.get("videoId") == h["videoId"] for it in lst):
                continue
            seq = max((int(it.get("added_seq") or 0) for it in lst), default=0) + 1
            lst.append({"videoId": h["videoId"], "title": h["title"] or ("youtu.be/" + h["videoId"]),
                        "channel": h["channel"], "published": h["published"],
                        "url": "https://www.youtube.com/watch?v=" + h["videoId"],
                        "added_at": int(time.time()), "added_seq": seq})
            added.append(lst[-1]["title"])
            positions.append(len(lst))
        store.save(WID, db)
        return {"ok": True, "added": added, "positions": positions, "count": len(lst), "query": q}

    if action == "remove":
        lst = db.get("list") or []
        idx = _resolve_item(lst, p.get("item"))
        if idx is None:
            return {"ok": False, "error": "item_not_found", "item": p.get("item"),
                    "message": "No encuentro ese vídeo en la lista."}
        removed = lst.pop(idx)
        pos = int(db.get("pos", -1))
        # Keep `pos` meaning "last played": removing an earlier item shifts everything one left, and removing
        # the CURRENT one leaves pos pointing at the slot BEFORE the next item — so `ended`/`next` (pos+1)
        # play exactly the item that followed the removed one. Playback itself is untouched (like YouTube).
        if idx <= pos:
            db["pos"] = pos - 1
        store.save(WID, db)
        return {"ok": True, "removed": removed.get("title"), "count": len(lst)}

    if action == "move":
        lst = db.get("list") or []
        idx = _resolve_item(lst, p.get("item"))
        if idx is None:
            return {"ok": False, "error": "item_not_found", "item": p.get("item"),
                    "message": "No encuentro ese vídeo en la lista."}
        try:
            to = max(0, min(len(lst) - 1, int(p.get("to")) - 1))     # 1-based target position
        except (TypeError, ValueError):
            return {"ok": False, "error": "bad_position", "message": "Dime a qué posición (1-N) lo muevo."}
        cur = lst[int(db.get("pos", -1))] if 0 <= int(db.get("pos", -1)) < len(lst) else None
        it = lst.pop(idx)
        lst.insert(to, it)
        if cur is not None:                              # pos follows the ITEM that was playing, not the slot
            db["pos"] = lst.index(cur)
        store.save(WID, db)
        return {"ok": True, "moved": it.get("title"), "position": to + 1}

    if action == "sort_list":
        by = str(p.get("by") or "title").strip().lower()
        if by not in ("title", "added"):
            return {"ok": False, "error": "bad_sort", "message": "Puedo ordenar por 'title' o por 'added'."}
        lst = db.get("list") or []
        cur = lst[int(db.get("pos", -1))] if 0 <= int(db.get("pos", -1)) < len(lst) else None
        if by == "title":
            lst.sort(key=lambda it: _norm(it.get("title")))
        else:
            lst.sort(key=lambda it: (int(it.get("added_at") or 0), int(it.get("added_seq") or 0)))
        if cur is not None:
            db["pos"] = lst.index(cur)
        store.save(WID, db)
        return {"ok": True, "by": by, "count": len(lst)}

    if action == "filter_list":
        # Display-only: the widget shows the rows matching the text; the list itself never changes.
        db["list_filter"] = str(p.get("q") or p.get("query") or "").strip()
        store.save(WID, db)
        return {"ok": True, "filter": db["list_filter"]}

    if action == "name_list":
        # Naming is not renaming ANOTHER list: this player has exactly ONE queue, so the name is a field of
        # the card, not an entity. Empty clears it back to the generic title — the same «vacío = quitar» that
        # `filter_list` already uses, so two list actions do not disagree about what an empty payload means.
        nombre = str(p.get("name") or p.get("title") or p.get("item") or "").strip()[:80]
        db["list_name"] = nombre
        store.save(WID, db)
        return {"ok": True, "name": nombre, "count": len(db.get("list") or [])}

    if action == "clear_list":
        # Empties the LIST only: whatever is playing keeps playing (voice «vacía la lista» must not cut the
        # video — close is the action that stops playback).
        db["list"] = []
        db["pos"] = -1
        store.save(WID, db)
        return {"ok": True, "count": 0}

    if action == "play_item":
        lst = db.get("list") or []
        idx = _resolve_item(lst, p.get("item") if p.get("item") is not None else p.get("query"))
        if idx is None:
            return {"ok": False, "error": "item_not_found", "item": p.get("item"),
                    "message": "No encuentro ese vídeo en la lista."}
        return _play_pos(db, idx, "play_item")

    if action == "next":
        lst = db.get("list") or []
        nxt = int(db.get("pos", -1)) + 1
        if not lst or nxt >= len(lst):
            return {"ok": False, "error": "end_of_list", "message": "No hay más vídeos en la lista."}
        return _play_pos(db, nxt, "next")

    if action == "previous":
        lst = db.get("list") or []
        pos = int(db.get("pos", -1))
        if lst and 0 < pos <= len(lst):
            return _play_pos(db, pos - 1, "previous")
        if db.get("videoId"):                           # at the start (or off-list): back = restart, like YouTube
            db["paused"] = False
            return _bump(db, "restart")
        return {"ok": False, "error": "no_video", "message": "No hay nada sonando."}

    if action == "ended":
        # Fired by the widget when the video reaches the end (onStateChange=0): one after another, by itself.
        lst = db.get("list") or []
        nxt = int(db.get("pos", -1)) + 1
        if 0 <= nxt < len(lst):
            return _play_pos(db, nxt, "next")
        db["paused"] = True                             # end of the list: stop honestly, do not loop
        return _bump(db, "ended")

    if action == "play":
        if not db.get("videoId"):
            # Empty player + a list waiting: "play" means start the list (add never autoplays, so this is the
            # voice path that actually launches a freshly built queue).
            lst = db.get("list") or []
            if lst:
                nxt = int(db.get("pos", -1)) + 1
                return _play_pos(db, nxt if 0 <= nxt < len(lst) else 0, "play_item")
            return {"ok": False, "error": "no_video", "message": "No hay ningún vídeo cargado ni lista."}
        db["paused"] = False
        return _bump(db, "play")
    if action == "player_error":
        # V2-401 — reported by widget.js when the embedded player refuses to play (onError). Recorded so the
        # producing predicate stops counting a broken player as playing. Never raises on a garbage code: the
        # value crosses a postMessage boundary and is data, not trusted input.
        db["player_error"] = str(p.get("code") or "unknown")[:40]
        return _bump(db, "player_error")

    if action == "pause":
        db["paused"] = True
        return _bump(db, "pause")
    if action == "mute":
        db["muted"] = True
        return _bump(db, "mute")
    if action == "unmute":
        db["muted"] = False
        return _bump(db, "unmute")
    if action == "volume_up":
        db["volume"] = min(100, int(db.get("volume") or 70) + 15)
        db["muted"] = False
        return _bump(db, "volume_up")
    if action == "volume_down":
        db["volume"] = max(0, int(db.get("volume") or 70) - 15)
        return _bump(db, "volume_down")
    if action == "set_volume":
        try:
            lvl = int(p.get("level"))
        except (TypeError, ValueError):
            return {"ok": False, "error": "bad_level", "message": "Dime un nivel entre 0 y 100."}
        db["volume"] = max(0, min(100, lvl))
        db["muted"] = db["volume"] == 0
        return _bump(db, "set_volume")
    if action == "restart":
        db["paused"] = False
        return _bump(db, "restart")
    if action == "close":
        # Empty the video → widget.js detects videoId="" and REBUILDS the card without <iframe>: the video REALLY
        # stops playing in the browser (not just data deletion), and the card moves to empty state.
        db["videoId"] = ""
        db["title"] = ""
        db["url"] = ""
        db["channel"] = ""
        db["published"] = ""
        db["latest"] = False
        db["paused"] = True
        db["muted"] = True
        db["pos"] = -1                                  # V2-366: close closes the VIDEO; the list survives
        return _bump(db, "close")

    return {"ok": False, "error": "unknown_action", "action": action}
