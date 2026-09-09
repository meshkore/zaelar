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
from . import account, library

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
    "captions": False,  # V2-590: subtitles on/off — the player re-asserts it on every load
    "paused": True,
    "last_cmd": "",
    "cmd_seq": 0,
    "loading": False,     # V2-062 fix: "load" search takes a few seconds (network); without this, the card looked
    "loading_query": "",  # COMPLETELY empty with no signal that something was happening (real bug 2026-07-23).
    # V2-366 — the PLAYLIST: linear queue of videos played one after another (operator asked for music-level lists).
    "list": [],           # [{videoId, title, channel, published, url, added_at}]
    # V2-401 — the player's own last error (IFrame API onError: 101/150 = embedding disabled). "" = healthy.
    # Written back by widget.js so "is it producing?" answers the player's reported reality, not our intent:
    # the operator's screenshot showed "This video is unavailable" while the declared state said playing.
    "player_error": "",
    # V2-634 — an unplayable video is a FACT to act on (rules and mechanism: availability.py's docstring).
    "blocked_videos": [],     # [{videoId,title,code,at}] the embedded player REFUSED — searches skip them
    "blocked_notice": {},     # {kind: swapped|explicit|exhausted, from, to?, code} — banner + brain; cleared on load
    "pick_explicit": False,   # the CURRENT video was a URL/id the operator handed over (block → honest message)
    "last_query": "",         # the search phrase behind our pick, so a swap can re-resolve the same intent
    "pos": -1,            # index in `list` of the item playing (or last played); -1 = current video is not from the list
    "adding": "",         # an `add` by name is searching the network right now (visible state, like `loading` for load)
    "list_filter": "",    # display-only filter over the list (filter_list); never touches the list itself
    # V2-467 — the list's NAME. `musica` has named playlists and this player did not, so «call it the afternoon
    # one» had nowhere to land: the model found no action, and the escalate catalogue's own «not being in
    # the catalogue is NOT a reason to refuse» sent a two-link queue to a Brain Worker (measured, and the
    # scenario calls escalating this a FAILURE — it is a rail, V2-042). "" = the card shows its generic title.
    "list_name": "",
    # V2-596 — channels the operator does not want to see («no me enseñes canales hechos con IA» — as he names
    # them, they are blocked). The FILTER lives in the widget's data; the KNOWLEDGE of which channels those are
    # lives with the brain/memory, which calls block_channel as it learns them. Applied to every NAME search
    # (load/add/search); an EXPLICIT link or id is an order and is never filtered.
    "blocked_channels": [],
    # V2-597 — the ACCOUNT layer. `platforms` caches the connector rows (connected/app_configured per video
    # platform) so view_data stays CHEAP (no connector import on the hot path — the archivos pattern); the
    # card asks for a `sync_platforms` once when the cache is stale. `suggested` is the HOME band: recent
    # uploads from the connected account's subscriptions, pulled ONLY when asked (`suggest`) — the operator's
    # standing rule is absolute control, so there is no background refresh (decision written in V2-597).
    "platforms": [],
    "platforms_at": 0,
    "connect_focus": None,   # {platform, ts} — the voice door into a platform's connect screen (V2-520 shape)
    "suggested": [],         # [{videoId, title, channel, published, url}] — normalized, newest first
    "suggested_at": 0,
    "suggested_channels": 0,
    "suggesting": False,     # a suggestions pull is on the network right now (visible state, like `adding`)
    # V2-632 — the SEARCH lives on the DASHBOARD, never in the queue (operator's redesign, 2026-09-09):
    # «búscame vídeos de X» paints numbered candidates at the TOP of the Inicio tab; he steers by voice from
    # there («reproduce el tercero», «añade los tres primeros a la cola», «regenera en 4K») and the queue only
    # receives what he explicitly sends in. `source` travels per row because the widget is provider-agnostic
    # by design — today every row says "youtube", and a second source is a value, not a schema change.
    "search_results": [],    # [{videoId, title, channel, published, url, source}]
    "search_query": "",
    "searched_at": 0,
}
# V2-604 — the widget's OWN library (followed channels, history, preferences, saved lists) lives in
# `library.py` and merges its fields here, so there is one seed and `_seed()`/`_load()` keep normalizing
# every field in one place. It owes nothing to the connector and does not degrade when it is absent.
_SEED.update(library.seed_fields())

# How long the cached platform rows are trusted before the card asks for a re-sync. Short and cheap: the
# sync reads two local files (token store + credential store), no network.
_PLATFORMS_FRESH_S = 300

# The account layer lives in account.py (extracted 2026-09-09, V2-632) — re-exported so every caller and
# test keeps reaching them through data.py; the blocked-channels filter is injected to avoid a cycle.
_svc = account._svc
_accounts_enabled = account._accounts_enabled
_sync_platforms = account._sync_platforms
_NOT_YET = account._NOT_YET
account._drop_blocked = None  # bound below, once _drop_blocked exists


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


def _is_blocked(channel: str, blocked: list) -> bool:
    """True when `channel` matches one of the operator's blocked entries.

    Containment only for terms of 4+ normalized chars: a blocked «ia» must NOT wipe «Diario de un viaje» by
    substring — short terms match by whole-name equality only. Containment goes ONE way (the stored term inside
    the channel name): the operator blocks by the name he was told, which may be a fragment of the full one."""
    ch = _norm(channel)
    if not ch:
        return False
    for b in blocked or []:
        t = _norm(b)
        if not t:
            continue
        if t == ch or (len(t) >= 4 and t in ch):
            return True
    return False


def _drop_blocked(hits: list, blocked: list) -> "tuple[list, int]":
    """Split search hits into (kept, how_many_blocked). The count travels in the action's answer so the ack can
    say honestly that results existed and were filtered — a silent drop reads as a worse search (V2-414)."""
    kept = [h for h in hits if not _is_blocked(h.get("channel") or "", blocked)]
    return kept, len(hits) - len(kept)


account._drop_blocked = _drop_blocked   # the extraction's one seam back (V2-632)

from widgets.youtube import availability as _avail  # noqa: E402  — V2-634, the unplayable-video family
_blocked_ids, _swap_to = _avail.blocked_ids, _avail.swap_to


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
    ms = list(re.finditer(r'"videoId":"([0-9A-Za-z_-]{11})"', html))
    for i, m in enumerate(ms):
        vid = m.group(1)
        if vid in seen:                                  # the page repeats each id many times (thumbs, params)
            continue
        seen.add(vid)
        # videoRenderer block for THIS video: title, channel and publication date are extracted from it.
        # Bounded at the NEXT DIFFERENT videoId (V2-469): a fixed 2500-char window can reach into the
        # following video's block, and a title-less Shorts block would then STEAL its neighbour's title —
        # naming one video and playing another. The same id repeating (thumbs, params) stays inside.
        end = m.start() + 2500
        for m2 in ms[i + 1:]:
            if m2.group(1) != vid:
                end = min(end, m2.start())
                break
        blk = html[m.start(): end]
        t = re.search(r'"title":\{"runs":\[\{"text":"([^"]{2,140})"', blk)
        if not t:
            # V2-469 — a hit the parser cannot NAME is not a candidate. Shorts blocks repeat "videoId"
            # but carry reelPlayerOverlayRenderer instead of "title":{"runs":…}; a query whose results
            # page led with them returned 5 hits, all untitled, and every one became a bare
            # «youtu.be/<id>» row the operator could not choose from («you have not given me a title.
            # That makes it impossible for me to choose»). Skip and keep walking: named hits further down fill n, and
            # a page with none returns [] — the `search` action already says that honestly.
            continue
        ch = re.search(r'"(?:ownerText|longBylineText)":\{"runs":\[\{"text":"([^"]{1,80})"', blk)
        pub = re.search(r'"publishedTimeText":\{"simpleText":"([^"]{2,40})"', blk)
        out.append({"videoId": vid, "title": _unesc(t.group(1)),
                    "channel": _unesc(ch.group(1)) if ch else "",
                    "published": _unesc(pub.group(1)) if pub else ""})
        if len(out) >= n:
            break
    return out


def _search_id(q: str, blocked: list = None, blocked_ids: set = None) -> dict:
    """Best-effort: resolve a phrase ("Messi goal") to the first YouTube video. Stdlib, 6s, fail-open.
    If the phrase asks for someone's MOST RECENT video ("the latest from ..."), sort by upload date.
    Returns {videoId,title,channel,published,latest} — publication date lets the operator VERIFY it is the correct
    video (V2-057: do not execute blindly; deliver a checkable result at a glance).

    V2-596: with blocked channels declared, the FIRST hit is the first hit from a channel the operator still
    wants — a few candidates are fetched and the blocked ones skipped, so «pon el vídeo de X» never lands on a
    channel he told us to filter out."""
    q = (q or "").strip()
    out = {"videoId": "", "title": "", "channel": "", "published": "", "latest": bool(_LATEST_RE.search(q))}
    hits = _search_many(q, 6 if (blocked or blocked_ids) else 1)
    if blocked:
        hits, _ = _drop_blocked(hits, blocked)
    if blocked_ids:   # V2-634: a video the player already refused is never offered again
        hits = [h for h in hits if h["videoId"] not in blocked_ids]
    if hits:
        h = hits[0]
        out.update({"videoId": h["videoId"], "title": h["title"] or q,
                    "channel": h["channel"], "published": h["published"]})
    return out

_avail._search_id = _search_id   # the injected search door (see availability.py docstring)


def _seed() -> dict:
    """Fresh copy of the seed. `dict(_SEED)` is SHALLOW: since the seed carries mutable containers, handing
    out the same object meant an `append` on a "fresh" db mutated the module seed itself — every later fresh
    load inherited it (caught by the V2-366 tests before shipping, and again by the V2-604 ones when `prefs`
    arrived as the first DICT in the seed and the list-only guard let it straight through: a preference set
    in one session was still there in the next widget's "empty" state). Every container gets its own copy."""
    d = dict(_SEED)
    for k, v in _SEED.items():
        if isinstance(v, list):
            d[k] = []
        elif isinstance(v, dict):
            d[k] = {}
    return d


def _load() -> dict:
    db = store.load(WID, _seed())
    for k, v in _SEED.items():                          # normalize missing fields (old store)
        if k in db:
            continue
        db[k] = [] if isinstance(v, list) else ({} if isinstance(v, dict) else v)
    return db


def view_data(q: str = "") -> dict:
    try:
        db = _load()
    except Exception as e:
        return {**_seed(), "error": str(e)[:120]}
    # Computed, never stored (a cache written before a restart is still a cache with an age): the card reads
    # this on mount to ask for ONE `sync_platforms` — the same `needs_refresh` shape archivos uses.
    out = dict(db)
    age = int(time.time()) - int(db.get("platforms_at") or 0)
    out["platforms_stale"] = age > _PLATFORMS_FRESH_S or not db.get("platforms_at")
    # V2-603 F2 — is the ACCOUNT layer usable at all? While no OAuth client exists anywhere the card renders
    # no platform row and no connect screen: a door that cannot open is worse than no door (measured, session
    # e1acdcca). DERIVED from the connector, so it turns on by itself the day a client id lands.
    out["accounts_enabled"] = _accounts_enabled()
    # V2-632 — the connector SHELF: what video sources exist, live or not, with their honest state. The card's
    # 🔌 screen renders it exactly like messaging's — including the shut doors, on purpose (INI-027's wishlist
    # rule: what we do NOT have is shown, never narrated). Composed from the V2-526 catalog (data, stdlib json)
    # merged with the live platform rows; fail-soft to [] — a broken catalog must not blank the player.
    out["connector_shelf"] = _connector_shelf(db)
    return out


def _connector_shelf(db: dict) -> list:
    rows = []
    try:
        from connectors import catalog as _cat
        live = {str(r.get("id") or ""): r for r in (db.get("platforms") or [])}
        for m in _cat.load_manifests():
            if m.get("family") != "video" or m.get("kind") != "connector":
                continue
            pid = str(m.get("id") or "")
            lv = live.get(pid) or {}
            rows.append({"id": pid, "label": str(m.get("label") or pid),
                         "state": str(m.get("state") or "planned"),
                         "connected": bool(lv.get("connected")),
                         "note": str(m.get("why-not") or m.get("notes") or m.get("note") or "")[:220]})
    except Exception:  # noqa: BLE001
        return []
    # YouTube first (the one people ask about), then buildable, then shut doors.
    rank = {"built": 0, "planned": 1, "not-possible": 2}
    rows.sort(key=lambda r: (0 if r["id"] == "youtube" else 1, rank.get(r["state"], 3), r["label"]))
    return rows


def prompt_digest() -> str:
    """What the OPEN card is showing that the brain must not guess at (V2-576's seam, open cards only):
    the dashboard's numbered search results — «reproduce el tercero» has to resolve against THESE rows, and
    without this block the model either invents an index or re-searches what is already on screen."""
    try:
        db = _load()
    except Exception:  # noqa: BLE001
        return ""
    # V2-634 — what just happened to playback is a FACT the model must say instead of narrate.
    lines = _avail.notice_lines(db)
    res = db.get("search_results") or []
    if not res:
        return "\n".join(lines)
    q = str(db.get("search_query") or "").strip()
    lines += [f"BÚSQUEDA DE VÍDEOS EN PANTALLA («{q}», {len(res)} resultados numerados — "
              "«el tercero» = el 3; reproducir: play_result{item:N} · a la cola: add_results{items:\"1,3\"|\"all\"}):"]
    for i, r in enumerate(res, 1):
        bits = [str(r.get("title") or "")[:70]]
        if r.get("channel"):
            bits.append(str(r["channel"])[:30])
        lines.append(f"  {i}. " + " — ".join(bits))
    return "\n".join(lines)


def ref_index() -> list:
    """The videos in the LIST, so the brain can name one instead of guessing an index (`widgets/refs.py`).

    The only member of the media family that did not publish its items — measured 2026-08-28 comparing the
    three: `musica` and `imagenes` answer, this one returned "". Two consequences, and the second is the
    expensive one: «play the third one» / «remove the Beatles one» had nothing to resolve against (and the
    model must never invent an id, V2-026); and with the card OPEN AND EMPTY the brief could not say so,
    which is exactly the «I consider what is missing delivered» that V2-377/380/383 each paid for once.

    `field: "item"` matches `play_item`/`remove`/`move`'s own payload key, and the label is the title the
    operator would actually say. The CURRENT one is marked in the hint: «the one that is playing» is a real way to
    refer to a video, and without it the brain cannot tell which of twelve is playing."""
    try:
        db = _load()
    except Exception:  # noqa: BLE001
        return []
    # `db.get("pos") or -1` was a falsy-zero bug (V2-469): with the FIRST video playing (pos=0, the most
    # common case) the `or` turned it into -1 and no item was ever marked as playing.
    cur = int(db.get("pos", -1))
    # «the one that is playing» over a broken player is a lie (V2-469, measured: play → player_error ×2, embedding
    # disabled, and the model answered «what is playing?» with evasions for four turns — nothing it READS
    # carried the fact). V2-401 fixed the producing predicate; this is the hint's half.
    roto = bool(str(db.get("player_error") or "").strip())
    out = []
    for i, it in enumerate(db.get("list") or []):
        titulo = str(it.get("title") or it.get("url") or it.get("videoId") or "").strip()
        if not titulo:
            continue
        _estado = ""
        if i == cur:
            _estado = ("no se puede reproducir aquí (el sitio bloquea la inserción); ofrécele otra o el enlace"
                       if roto else "la que suena")
        pistas = [p for p in (str(it.get("channel") or "").strip(), _estado) if p]
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
    db["blocked_notice"] = {}
    db["pick_explicit"] = False           # V2-634: queue-driven playback is our side driving
    db["videoId"] = it.get("videoId") or ""
    db["url"] = it.get("url") or ("https://www.youtube.com/watch?v=" + db["videoId"])
    db["title"] = it.get("title") or db["url"]
    db["channel"] = it.get("channel") or ""
    db["published"] = it.get("published") or ""
    db["latest"] = False
    db["pos"] = i
    db["paused"] = False
    library.record_play(db, it)                          # V2-604: we are the ones playing it, so the history is ours
    library.apply_prefs(db, fresh=False)
    r = _bump(db, cmd)
    r["position"] = i + 1
    return r


def apply_action(action: str, payload: dict = None) -> dict:
    p = payload or {}
    db = _load()

    # V2-632 — «este vídeo me gusta: sigue al autor» names nobody; the CURRENT video's channel is the obvious
    # referent, and demanding the name back is an argument the sentence never fills (the V2-609 class).
    if action == "follow_channel" and not str(p.get("channel") or p.get("name") or p.get("item") or "").strip():
        cur = str(db.get("channel") or "").strip()
        if cur:
            p = dict(p); p["channel"] = cur

    if action == "load":
        had_video = bool(db.get("videoId"))
        raw = str(p.get("url") or p.get("videoId") or "").strip()
        vid = _extract_id(raw)
        # V2-634 — provenance decides what a playback block may do (availability.py); internal swaps pass
        # pick:"ours" so re-loading through this branch never claims the operator's authorship.
        explicit = bool(vid) and str(p.get("pick") or "") != "ours"
        title = str(p.get("title") or "").strip()
        channel, published, latest = "", "", False
        if not vid:                                     # not URL/id → search by name
            q = str(p.get("query") or p.get("q") or raw or "").strip()
            db["last_query"] = q
            # Real LOADER (bug 2026-07-23, "there is no loader showing that you are searching"): _search_id scrapes
            # the network (several seconds) — without this the card looked COMPLETELY empty in the meantime,
            # indistinguishable from "nothing requested". Save+emit NOW (before network) so widget.js paints the
            # spinner immediately; the final load turns it off.
            db["loading"], db["loading_query"] = True, q
            store.save(WID, db)
            r = _search_id(q, db.get("blocked_channels"), _blocked_ids(db))
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
        db["blocked_notice"] = {}
        db["pick_explicit"] = explicit
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
        library.record_play(db, {"videoId": vid, "title": db["title"], "channel": channel, "url": db["url"]})
        library.apply_prefs(db, fresh=not had_video)
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
            r = _search_id(q, db.get("blocked_channels"), _blocked_ids(db))
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
        # V2-402/V2-632 — a MEDIA search lands in the WIDGET, never in the results sheet; and since the
        # operator's redesign (2026-09-09) it lands on the DASHBOARD as its own numbered band, never in the
        # queue: results are something to CHOOSE FROM, the queue is what he chose. A new search REPLACES the
        # previous one (results are a view of the last question, not an archive). NOTHING starts playing
        # (V2-366's rule holds), and player state is untouched: a search must not interrupt playback.
        q = str(p.get("query") or p.get("q") or "").strip()
        if not q:
            return {"ok": False, "error": "no_query", "message": "Dime qué vídeos busco."}
        try:
            n = int(p.get("n") or 6)
        except Exception:
            n = 6
        n = max(1, min(n, 10))
        db["adding"] = q                                # visible state while the network search runs (as `add`)
        store.save(WID, db)
        blocked = db.get("blocked_channels") or []
        bids = _blocked_ids(db)
        # Fetch a few extra when a filter exists, so blocking a channel does not shrink every search.
        hits = _search_many(q, n + (4 if blocked else 0) + (4 if bids else 0))
        hits, n_blocked = _drop_blocked(hits, blocked)
        hits = [h for h in hits if h["videoId"] not in bids][:n]   # V2-634: the refused never come back
        db["last_query"] = q
        db["adding"] = ""
        if not hits:
            store.save(WID, db)                          # turn the state off even when nothing was found
            if n_blocked:
                # Results existed and the operator's own filter removed them — saying «no videos» would read
                # as a worse search and invite retries against a wall he built himself (V2-414's confound).
                return {"ok": False, "error": "all_blocked", "blocked_out": n_blocked,
                        "message": "Había resultados pero todos eran de canales que tienes bloqueados."}
            return {"ok": False, "error": "no_video", "message": "No encontré vídeos de eso."}
        db["search_results"] = [{"videoId": h["videoId"],
                                 "title": h["title"] or ("youtu.be/" + h["videoId"]),
                                 "channel": h["channel"], "published": h["published"],
                                 "url": "https://www.youtube.com/watch?v=" + h["videoId"],
                                 "source": "youtube"} for h in hits]
        db["search_query"] = q
        db["searched_at"] = int(time.time())
        store.save(WID, db)
        out = {"ok": True, "results": [r["title"] for r in db["search_results"]],
               "count": len(db["search_results"]), "query": q}
        if n_blocked:
            out["blocked_out"] = n_blocked               # the ack can say «and N more from blocked channels»
        return out

    if action == "play_result":
        # V2-632 — «reproduce el tercero» over the dashboard's search band. 1-based, like every spoken number.
        res = db.get("search_results") or []
        try:
            i = int(str(p.get("item") or p.get("n") or "").strip()) - 1
        except Exception:
            i = -1
        if not res:
            return {"ok": False, "error": "no_results", "message": "No hay resultados de búsqueda ahora mismo."}
        if i < 0 or i >= len(res):
            return {"ok": False, "error": "bad_index", "count": len(res),
                    "message": f"Solo hay {len(res)} resultados."}
        it = res[i]
        _swap_to(db, it)   # V2-634: the shared field-set (pick_explicit=False and queue position inside)
        r = _bump(db, "load")
        r["position"] = i + 1
        return r

    if action == "add_results":
        # V2-632 — «añade los tres primeros a la cola» / «añádelos todos». Payload: items="1,2,3" | [1,2,3] |
        # "all" (or a single n). The queue gets rows in the same shape `add` writes, so play_item/next/remove
        # keep working on them untouched.
        res = db.get("search_results") or []
        if not res:
            return {"ok": False, "error": "no_results", "message": "No hay resultados de búsqueda ahora mismo."}
        raw = p.get("items", p.get("item", p.get("n", "")))
        idxs = []
        if isinstance(raw, list):
            idxs = [int(x) for x in raw if str(x).strip().isdigit()]
        else:
            t = str(raw or "").strip().lower()
            if t in ("all", "todos", "todas", "*"):
                idxs = list(range(1, len(res) + 1))
            else:
                idxs = [int(x) for x in re.findall(r"\d+", t)]
        idxs = [i for i in idxs if 1 <= i <= len(res)]
        if not idxs:
            return {"ok": False, "error": "no_items", "count": len(res),
                    "message": "Dime cuáles añado (números, o «todos»)."}
        lst = db.setdefault("list", [])
        added, positions = [], []
        for i in idxs:
            h = res[i - 1]
            if any(it.get("videoId") == h.get("videoId") for it in lst):
                continue
            seq = max((int(it.get("added_seq") or 0) for it in lst), default=0) + 1
            lst.append({"videoId": h.get("videoId"), "title": h.get("title") or "",
                        "channel": h.get("channel") or "", "published": h.get("published") or "",
                        "url": h.get("url") or "", "added_at": int(time.time()), "added_seq": seq})
            added.append(h.get("title") or "")
            positions.append(len(lst))
        store.save(WID, db)
        return {"ok": True, "added": added, "positions": positions, "count": len(lst)}

    if action == "clear_search":
        db["search_results"], db["search_query"], db["searched_at"] = [], "", 0
        store.save(WID, db)
        return {"ok": True}

    r = account.apply(action, p, db)                     # the ACCOUNT layer (V2-597, account.py)
    if r is not None:
        return r

    if action == "block_channel":
        # V2-596 — «no quiero ver este canal»: the filter the operator educates by voice. The brain names the
        # channel as it learns which ones he means («canales hechos con IA» → block each one it identifies);
        # the widget only stores and applies the filter. Blocking also SWEEPS the current list — a channel he
        # just refused must not keep sitting in his queue — but never cuts what is already playing (V2-366's
        # rule: only `close` stops playback).
        ch = str(p.get("channel") or p.get("name") or p.get("item") or "").strip()[:80]
        if not ch:
            return {"ok": False, "error": "no_channel",
                    "message": "Dime qué canal bloqueo (su nombre, como sale en la lista)."}
        blocked = db.setdefault("blocked_channels", [])
        if any(_norm(b) == _norm(ch) for b in blocked):
            store.save(WID, db)
            return {"ok": True, "already_blocked": True, "channel": ch, "blocked": list(blocked)}
        blocked.append(ch)
        lst = db.get("list") or []
        cur = lst[int(db.get("pos", -1))] if 0 <= int(db.get("pos", -1)) < len(lst) else None
        kept = [it for it in lst if not _is_blocked(it.get("channel") or "", [ch])]
        swept = len(lst) - len(kept)
        db["list"] = kept
        db["pos"] = kept.index(cur) if cur is not None and cur in kept else -1
        # V2-597 — the SUGGESTIONS band is swept too: a channel he just refused must not keep sitting on
        # his home screen either.
        sug = db.get("suggested") or []
        db["suggested"] = [it for it in sug if not _is_blocked(it.get("channel") or "", [ch])]
        swept += len(sug) - len(db["suggested"])
        store.save(WID, db)
        return {"ok": True, "channel": ch, "removed_from_list": swept, "blocked": list(blocked)}

    if action == "unblock_channel":
        ch = str(p.get("channel") or p.get("name") or p.get("item") or "").strip()
        blocked = db.get("blocked_channels") or []
        n = _norm(ch)
        hit = next((b for b in blocked if _norm(b) == n or (n and n in _norm(b))), None)
        if hit is None:
            return {"ok": False, "error": "not_blocked", "channel": ch, "blocked": list(blocked),
                    "message": "Ese canal no está bloqueado." if blocked
                               else "No hay ningún canal bloqueado."}
        blocked.remove(hit)
        store.save(WID, db)
        return {"ok": True, "channel": hit, "blocked": list(blocked)}

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
        # the card, not an entity. Empty clears it back to the generic title — the same «empty = remove» that
        # `filter_list` already uses, so two list actions do not disagree about what an empty payload means.
        nombre = str(p.get("name") or p.get("title") or p.get("item") or "").strip()[:80]
        db["list_name"] = nombre
        store.save(WID, db)
        return {"ok": True, "name": nombre, "count": len(db.get("list") or [])}

    if action == "clear_list":
        # Empties the LIST only: whatever is playing keeps playing (voice «empty the list» must not cut the
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
        # V2-401 — widget.js reports onError (untrusted, crosses postMessage). V2-634 — a FATAL code is
        # ACTED on: blocklist + swap of our own pick, or the honest message for a pasted link — the whole
        # behavior lives in `availability.on_player_error`, beside the blocklist it maintains.
        code = str(p.get("code") or "unknown")[:40]
        dead = str(p.get("videoId") or db.get("videoId") or "")[:20]
        verdict = _avail.on_player_error(db, code, dead)
        if verdict == "stale":
            store.save(WID, db)
            return {"ok": True, "cmd": "player_error", "stale": True}
        if verdict is None:
            db["player_error"] = code
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
    if action == "captions_on":
        # V2-590 — «quita los subtítulos» was narrated as impossible («solo puedes quitarlos desde los
        # controles», measured live): the capability had no declared action, and an undeclared capability
        # is one the model narrates (V2-540). The widget toggles the IFrame API captions module.
        db["captions"] = True
        return _bump(db, "captions_on")
    if action == "captions_off":
        db["captions"] = False
        return _bump(db, "captions_off")
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

    r = library.apply(action, p, db)                     # V2-604 — channels, history, preferences, saved lists
    if r is not None:
        return r

    return {"ok": False, "error": "unknown_action", "action": action}

