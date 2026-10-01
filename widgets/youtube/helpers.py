"""The YouTube card's small readers: item references, blocked channels, tabs and the play position (V2-778 F1).

Moved out of `widgets/youtube/data.py` (1,074 lines, over the 900 a new file may reach), unchanged: which row a
reference names, which channels he blocked, the tab aliases, the goto/bump/position bookkeeping, the id inside a
pasted link, the results query and the seed. `data` imports every name back. The search itself (`_search_many`)
and `_load` stay in `data`: tests patch them there.
"""
from __future__ import annotations

import re
import unicodedata
import urllib.request
from .. import store
from . import account, channels, library     # channels: the followed channels as cards and pages
from . import sources as _sources        # V2-638: where a playable row comes from (youtube | local | torrent)

WID = "youtube"   # the same constant as data.WID


def _tab_alias(word: str) -> str:
    """The face a declared alias names («home», «dashboard», «reproductor» …), read from the manifest's
    own `show_tab` payload text through `widgets.enums` — one declaration, both readers (V2-754)."""
    try:
        from .. import enums as _enums, runtime as _rt
        spec = ((((_rt.get(WID) or {}).get("actions") or {}).get("show_tab") or {}).get("payload") or {}).get("tab")
        return _enums.resolve(str(spec or ""), word)
    except Exception:  # noqa: BLE001
        return ""


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


_RESULTS_RE = re.compile(r"youtube\.com/results\?([^\s\"'<>]+)")


def _results_query(s: str) -> str:
    """The decoded `search_query` of a YouTube RESULTS link anywhere in `s`, or "".

    Live, 2026-09-29: «open this youtube search: https://www.youtube.com/results?search_query=Liverpool+Atletico…»
    reached `search` with the WHOLE sentence — URL included — as the query, and the scraper answered a
    question nobody asked. A pasted results link IS the query, already written: it is parsed, never read."""
    m = _RESULTS_RE.search(s or "")
    if not m:
        return ""
    qs = urllib.parse.parse_qs(m.group(1), keep_blank_values=False)
    vals = qs.get("search_query") or qs.get("q") or []
    return " ".join(str(v).strip() for v in vals if str(v).strip())[:200]


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


def _goto(db: dict, tab: str) -> None:
    """Order the card to bring a face forward — the SAME rail `show_tab` writes (V2-742): a sequence, so the
    card obeys it once and a re-render never fights the operator's hands.

    V2-755. Measured live (session 665e666a, 2026-09-23): he went back to the catalog with a video still
    loaded and then said «Vale, ahora ponme el vídeo número seis». `play_result` fired, the sixth video
    swapped into the player — and the card stayed on the catalog, because the auto-jump in `widget.js` only
    fires when the card had NO video before (`!st.key.slice(2)`). Nothing on screen changed. He said «No lo
    estás poniendo», then «Coge el vídeo número seis y reprodúcelo», then «No lo consigues», and the third
    attempt was eaten by the re-emit guard because the action HAD run, twice, invisibly.

    So the rule the redesign already stated («a video ARRIVING means watching it, leaving the dashboard up
    while it plays underneath is the confusion this exists to end») is declared HERE, where the order is
    known, instead of being inferred in the card from a state transition that cannot tell a swap from an
    arrival. The automatic advance at the end of a video does NOT write it: he may be reading the queue
    while one plays, and yanking his view on a track change is the same defect with the sign flipped.
    """
    prev = db.get("goto_tab") if isinstance(db.get("goto_tab"), dict) else {}
    db["goto_tab"] = {"tab": tab, "seq": int(prev.get("seq") or 0) + 1}


def _index_list(raw, n: int) -> list:
    """`"4,5,6"` / `[4, 5, 6]` / `"all"` → ZERO-based indices inside a list of `n`, deduped; [] when the
    payload names no number. The shape `add_results` has accepted since V2-632, read once so `remove`
    cannot drift from it (V2-756)."""
    if raw is None or n <= 0:
        return []
    if isinstance(raw, list):
        nums = [int(x) for x in raw if str(x).strip().lstrip("-").isdigit()]
    else:
        t = str(raw).strip().lower()
        if not t:
            return []
        if t in ("all", "todos", "todas", "*"):
            return list(range(n))
        nums = [int(x) for x in re.findall(r"\d+", t)]
    return sorted({i - 1 for i in nums if 1 <= i <= n})


def _bump(db: dict, cmd: str) -> dict:
    db["last_cmd"] = cmd
    db["cmd_seq"] = int(db.get("cmd_seq") or 0) + 1
    store.save(WID, db)
    return {"ok": True, "cmd": cmd, "videoId": db.get("videoId"), "title": db.get("title"),
            "volume": db.get("volume"), "muted": db.get("muted"), "paused": db.get("paused")}


def _play_pos(db: dict, i: int, cmd: str, *, watch: bool = True) -> dict:
    """Make list item i the CURRENT video and play it. The card fields (title/channel/published) become the
    item's own, so the on-screen verification (V2-057) keeps working when the list drives playback."""
    it = db["list"][i]
    db["player_error"] = ""   # a DIFFERENT video: the old player error says nothing about it (V2-401)
    db["blocked_notice"] = {}
    db["pick_explicit"] = False           # V2-634: queue-driven playback is our side driving
    db["videoId"] = it.get("videoId") or ""
    _sources.carry(db, it)                # V2-638: source + src travel with the row, or a <video> gets a stale src
    db["torrent_id"] = str(it.get("torrent_id") or "")
    # A local/torrent row has no watch URL to fall back to — inventing one names a YouTube video that is not it.
    db["url"] = it.get("url") or ("" if _sources.is_stream(it)
                                  else "https://www.youtube.com/watch?v=" + db["videoId"])
    db["title"] = it.get("title") or db["url"]
    db["channel"] = it.get("channel") or ""
    db["published"] = it.get("published") or ""
    db["latest"] = False
    db["pos"] = i
    db["paused"] = False
    library.record_play(db, it)                          # V2-604: we are the ones playing it, so the history is ours
    library.apply_prefs(db, fresh=False)
    if watch:
        _goto(db, "player")                              # V2-755: he asked to watch it, so show it
    r = _bump(db, cmd)
    r["position"] = i + 1
    return r
