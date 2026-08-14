#
# youtube — EMBEDDED YouTube player in the canvas (a real <iframe> that PLAYS, not a capture).
# Video is controlled by VOICE: FlashBrain calls apply_action (tool widget_data) and here we store desired
# STATE/command in the store; the client (widget.js) applies it to the player through postMessage (YouTube IFrame API,
# NO library). data.py is pure server code (stdlib) — it never touches the player.
#
import re
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


# Requests the MOST RECENT video (e.g. "the latest video by Jose Luis Carpatos") → sort by upload date.
_LATEST_RE = re.compile(r"\b(?:[uú]ltim[oa]s?|m[aá]s\s+recientes?|reciente|nuevo|last|latest|newest)\b", re.I)


def _unesc(s: str) -> str:
    """Decode \\uXXXX sequences that YouTube sometimes embeds in JSON, without touching already decoded UTF-8."""
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s or "")


def _search_id(q: str) -> dict:
    """Best-effort: resolve a phrase ("Messi goal") to the first YouTube video. Stdlib, 6s, fail-open.
    If the phrase asks for someone's MOST RECENT video ("the latest from ..."), sort by upload date.
    Returns {videoId,title,channel,published,latest} — publication date lets the operator VERIFY it is the correct
    video (V2-057: do not execute blindly; deliver a checkable result at a glance)."""
    q = (q or "").strip()
    out = {"videoId": "", "title": "", "channel": "", "published": "", "latest": False}
    if not q:
        return out
    latest = bool(_LATEST_RE.search(q))
    out["latest"] = latest
    try:
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(q)
        if latest:                                       # sort by upload date (sp=CAI%3D)
            url += "&sp=CAI%3D"
        req = urllib.request.Request(url, headers={
            "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"),
            "Accept-Language": "es-ES,es;q=0.9",
        })
        html = urllib.request.urlopen(req, timeout=6).read().decode("utf-8", "ignore")
        m = re.search(r'"videoId":"([0-9A-Za-z_-]{11})"', html)
        if not m:
            return out
        vid = m.group(1)
        out["videoId"] = vid
        # videoRenderer block for THIS video: title, channel, and publication date are extracted from it.
        blk = html[m.start(): m.start() + 2500]
        t = re.search(r'"title":\{"runs":\[\{"text":"([^"]{2,140})"', blk) \
            or re.search(r'"videoId":"' + re.escape(vid) + r'".*?"text":"([^"]{3,120})"', html)
        out["title"] = _unesc(t.group(1)) if t else q
        ch = re.search(r'"(?:ownerText|longBylineText)":\{"runs":\[\{"text":"([^"]{1,80})"', blk)
        out["channel"] = _unesc(ch.group(1)) if ch else ""
        pub = re.search(r'"publishedTimeText":\{"simpleText":"([^"]{2,40})"', blk)
        out["published"] = _unesc(pub.group(1)) if pub else ""
        return out
    except Exception:
        return out


def _load() -> dict:
    db = store.load(WID, dict(_SEED))
    for k, v in _SEED.items():                          # normalize missing fields (old store)
        db.setdefault(k, v)
    return db


def view_data(q: str = "") -> dict:
    try:
        return _load()
    except Exception as e:
        return {**_SEED, "error": str(e)[:120]}


def _bump(db: dict, cmd: str) -> dict:
    db["last_cmd"] = cmd
    db["cmd_seq"] = int(db.get("cmd_seq") or 0) + 1
    store.save(WID, db)
    return {"ok": True, "cmd": cmd, "videoId": db.get("videoId"), "title": db.get("title"),
            "volume": db.get("volume"), "muted": db.get("muted"), "paused": db.get("paused")}


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
        db["videoId"] = vid
        db["url"] = "https://www.youtube.com/watch?v=" + vid
        db["title"] = title or db["url"]
        db["channel"] = channel                          # V2-057: VERIFIABLE metadata in the card
        db["published"] = published                      # e.g. "2 days ago" — confirms it is the correct one
        db["latest"] = latest                            # most recent requested (date order)
        db["paused"] = False
        return _bump(db, "load")

    if action == "play":
        db["paused"] = False
        return _bump(db, "play")
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
        return _bump(db, "close")

    return {"ok": False, "error": "unknown_action", "action": action}
