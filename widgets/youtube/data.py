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
from widgets import hint_lang as _hl   # V2-778 F3-30: hints are read back aloud, in the agent's language
from . import account, channels, library     # channels: the followed channels as cards and pages
from .helpers import (  # noqa: E402,F401 — V2-778 F1: moved, imported back under their names
    _RESULTS_RE, _SEED, _YT_RE, _bump, _drop_blocked, _extract_id, _goto, _index_list, _is_blocked, _norm,
    _oembed_title, _play_pos, _resolve_item, _results_query, _seed, _tab_alias)

WID = "youtube"

#: The card's own faces (V2-632). Mirrored in `widget.js` as `_TABS`; a test pins the two lists
#: equal, because a tab that exists on one side only is an order that silently does nothing.
_TABS = ("inicio", "player", "cola", "subs", "listas")


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


account._drop_blocked = _drop_blocked   # the extraction's one seam back (V2-632)

from widgets.youtube import availability as _avail  # noqa: E402  — V2-634, the unplayable-video family
_blocked_ids, _swap_to = _avail.blocked_ids, _avail.swap_to
from . import sources as _sources        # V2-638: where a playable row comes from (youtube | local | torrent)


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
    out["connector_shelf"] = _sources.connector_shelf(db)
    # V2-638 — a download being watched while it fills; {} for every other source, so the card shows nothing.
    out["download"] = _sources.live_status(db)
    # V2-755 — does this card HOLD anything? The errand harness asks every widget this and takes silence as
    # «unverifiable»; this one never answered, so the goal born at «muéstrame el widget de vídeo» could never
    # be met and the prompt carried «la hoja `youtube` sigue VACÍA» over six results and a playing video for
    # three minutes (session 665e666a). Anything the operator can SEE counts: what is in the player, the
    # numbered search band, and the queue — the three surfaces the card renders.
    out["empty"] = not (db.get("videoId") or db.get("src") or db.get("search_results") or db.get("list"))
    out["channel_cards"], out["channel_page"] = channels.cards(db), channels.page(db)
    return out


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
    # V2-756 — the NEGATIVE belongs here too. «ponme el vídeo número tres» over this band came back as
    # `play_video(action=list)`, a fresh search, three turns running. This block costs prompt only while
    # the card is open (V2-526's pattern), which is exactly when the sentence is true.
    lines += [f"BÚSQUEDA DE VÍDEOS EN PANTALLA («{q}», {len(res)} resultados numerados — "
              "«el tercero» = el 3; reproducir: play_result{item:N} · a la cola: add_results{items:\"1,3\"|\"all\"}"
              " · quitar varios de la cola: remove{items:\"4,5,6\"}. Elegir uno de ESTOS por número NO es "
              "play_video: volver a buscar RENUMERA esta lista):"]
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
            _estado = (_hl.pick("no se puede reproducir aquí (el sitio bloquea la inserción); ofrécele otra o el "
                                "enlace", "cannot play here (the site blocks embedding); offer another or the link")
                       if roto else _hl.pick("la que suena", "the one playing"))
        pistas = [p for p in (str(it.get("channel") or "").strip(), _estado) if p]
        out.append({"id": str(i + 1), "label": titulo[:80], "field": "item",
                    "hint": " · ".join(pistas)})
    return out


# V2-778 F1-12 — the action handlers live in `actions.py`, imported back under their names (that module
# reads this one).
from .actions import (  # noqa: E402,F401
    _a_torrent, _a_load, _a_add, _a_search, _a_play_result, _a_add_results, _a_show_tab, _a_clear_search,
    _a_block_channel, _a_unblock_channel, _a_remove, _a_move, _a_sort_list, _a_filter_list, _a_name_list,
    _a_clear_list, _a_play_item, _a_next, _a_previous, _a_ended, _a_play, _a_player_error, _a_pause, _a_mute,
    _a_unmute, _a_captions_on, _a_captions_off, _a_volume_up, _a_volume_down, _a_set_volume, _a_restart, _a_close)


# V2-778 F1-12 — one function per action (in `actions.py`), and `apply_action` is the table lookup. Each body
# is the branch it was, moved verbatim; the contract gate reads the table's keys
# (`widgets/validator._table_actions`).


ACTIONS = {
    "play_local": _a_torrent,
    "play_torrent": _a_torrent,
    "load": _a_load,
    "add": _a_add,
    "search": _a_search,
    "play_result": _a_play_result,
    "add_results": _a_add_results,
    "show_tab": _a_show_tab,
    "clear_search": _a_clear_search,
    "block_channel": _a_block_channel,
    "unblock_channel": _a_unblock_channel,
    "remove": _a_remove,
    "move": _a_move,
    "sort_list": _a_sort_list,
    "filter_list": _a_filter_list,
    "name_list": _a_name_list,
    "clear_list": _a_clear_list,
    "play_item": _a_play_item,
    "next": _a_next,
    "previous": _a_previous,
    "ended": _a_ended,
    "play": _a_play,
    "player_error": _a_player_error,
    "pause": _a_pause,
    "mute": _a_mute,
    "unmute": _a_unmute,
    "captions_on": _a_captions_on,
    "captions_off": _a_captions_off,
    "volume_up": _a_volume_up,
    "volume_down": _a_volume_down,
    "set_volume": _a_set_volume,
    "restart": _a_restart,
    "close": _a_close,
}


def apply_action(action: str, payload: dict = None) -> dict:
    p = payload or {}
    db = _load()

    # V2-632 — «este vídeo me gusta: sigue al autor» names nobody; the CURRENT video's channel is the obvious
    # referent, and demanding the name back is an argument the sentence never fills (the V2-609 class).
    if action == "follow_channel" and not str(p.get("channel") or p.get("name") or p.get("item") or "").strip():
        cur = str(db.get("channel") or "").strip()
        if cur:
            p = dict(p); p["channel"] = cur
    handler = ACTIONS.get(action) if isinstance(action, str) else None
    if handler is not None:
        return handler(action, p, db)
    r = account.apply(action, p, db)                     # the ACCOUNT layer (V2-597, account.py)
    if r is not None:
        return r

    r = channels.apply(action, p, db) or library.apply(action, p, db)   # channel pages · V2-604 library
    if r is not None:
        return r

    return {"ok": False, "error": "unknown_action", "action": action}
