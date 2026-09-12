"""connectors/music/youtube_audio.py — FREE in-browser music provider (V2-041).

Fallback when Spotify is NOT available: resolves a song to a YouTube video and plays **only its AUDIO**, hidden,
INSIDE the `musica` widget (never the YouTube widget — these are separate things). It does not control a remote
device like Spotify: playback lives in the browser, so its "surface" is the widget (the client mounts a hidden iframe
and applies commands). This provider is the server-side FACE: resolves the `videoId` and leaves the command in the
`musica` widget store; `widget.js` applies it.

Always available (no login) -> DEFAULT provider when Spotify is not connected, so "play music" ALWAYS plays
something. Video resolution: **YouTube Data API** if `YOUTUBE_API_KEY` exists (fast and reliable), otherwise a stdlib
scrape of the results page (best-effort, fail-open) — OWN copy, does not touch the YouTube widget.
"""
from __future__ import annotations

import logging
import os
import re
import urllib.parse
import urllib.request

from .base import MusicProvider, MusicResult, NowPlaying, Track

logger = logging.getLogger("zaelar.music.youtube")

_WID = "musica"                              # hidden AUDIO lives in the MUSIC widget (not the YouTube widget)

def _yt_thumb(video_id: str) -> str:
    """Cover art for a YouTube-resolved track, for FREE: the video's own thumbnail, at a fixed CDN URL derived
    from the id alone — no network call on our side, no API key, no latency added to playback (V2-629).
    `hqdefault.jpg` (480x360) is the one size YouTube guarantees for every public video; `maxresdefault`/
    `sddefault` do not exist for a lot of uploads and come back as a grey placeholder or a 404. It is not
    always the album's real artwork (a lyric video's thumbnail is a still frame), but for the common case —
    an "Official Audio"/"Official Video" upload — the thumbnail IS the cover, and it is available the INSTANT
    a videoId is known, which `_track_from_resolved` (widgets/musica/data.py) then carries into recent/top."""
    vid = str(video_id or "").strip()
    return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else ""

_MSG = {
    "es": {"play": "Suena {label}.", "pause": "Pausado.", "resume": "Sigo.", "volume": "Volumen al {n} por ciento.",
           "no_track": "No he encontrado «{q}».", "done": "Hecho.",
           "no_next": "No hay más canciones en la cola; dime qué pongo.",
           "no_prev": "No hay canción anterior a la que volver.",
           "already": "Ya está sonando {label}.", "queued": "Vale, después pongo {label}."},
    "en": {"play": "Now playing {label}.", "pause": "Paused.", "resume": "Resuming.", "volume": "Volume at {n} percent.",
           "no_track": "I couldn't find \"{q}\".", "done": "Done.",
           "no_next": "Nothing else queued; tell me what to play.",
           "no_prev": "There is no previous track to go back to.",
           "already": "{label} is already playing.", "queued": "Got it, I'll play {label} next."},
}


def _norm_q(s: str) -> str:
    """Normalize a query for comparison (F5 no-restart): lowercase, no accents, no extra spaces."""
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _lang() -> str:
    try:
        from voice.engine.core import langs
        code = (langs.current_code() or "es").lower()
        return code if code in _MSG else "es"
    except Exception:
        return "es"


def _t(key: str, **kw) -> str:
    return _MSG[_lang()][key].format(**kw)


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
            "Accept-Language": _accept_language()})
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


# ── state in the musica widget store ('yt' block) ─────────────────────────────────────────────────────────
def _load_yt() -> dict:
    try:
        from widgets import store
        db = store.load(_WID, {})
        return dict(db.get("yt") or {})
    except Exception:
        return {}


def _save_yt(yt: dict) -> None:
    """Persist the 'yt' block in the musica widget store (fires SSE -> widget re-renders and applies)."""
    try:
        from widgets import store
        db = store.load(_WID, {})
        db["yt"] = yt
        store.save(_WID, db)               # ONLY point that emits "widget changed" (V2-017)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"no pude escribir el estado yt del widget musica: {e!r}")


def _bump(yt: dict, cmd: str) -> dict:
    yt["last_cmd"] = cmd
    yt["cmd_seq"] = int(yt.get("cmd_seq") or 0) + 1
    _save_yt(yt)
    return yt


def _push_history(yt: dict) -> None:
    """Remember the track being REPLACED so previous() can go back to it (V2-631). Only a real, resolved track
    (with a videoId) enters; capped at 20 so the store never grows unbounded."""
    vid = yt.get("videoId")
    if not vid:
        return
    hist = list(yt.get("history") or [])
    hist.append({"videoId": vid, "title": yt.get("title") or "", "query": yt.get("query") or ""})
    yt["history"] = hist[-20:]


class YouTubeAudioProvider(MusicProvider):
    name = "youtube"

    def connected(self) -> bool:
        return True                        # free, no login -> ALWAYS available (default fallback)

    def search(self, query: str, limit: int = 5) -> "list[Track]":
        vid, title = _resolve(query)
        return [Track(id=vid, uri=f"yt:{vid}", title=title, art=_yt_thumb(vid))] if vid else []

    def play(self, query: str = "", uri: str = "") -> MusicResult:
        vid = _extract_id(uri)
        title = ""
        yt = _load_yt()
        # NO-RESTART GUARD (V2-047 F5): if the operator asks to play the SAME query already playing (a complaint or
        # a non-reasoning model re-launch: T27/T31 session 23:15 restarted the song), do NOT re-resolve or reload the
        # iframe -> music is not cut off. Deterministic on normalized query (not a word table): "Shakira" == previous
        # query -> no-op; "another by Shakira" != -> play a new one.
        nq = _norm_q(query)
        if nq and not uri and nq == _norm_q(yt.get("query") or "") and yt.get("videoId") and not yt.get("paused"):
            return MusicResult(ok=True, provider=self.name, action="play",
                               track=Track(id=yt.get("videoId", ""), title=yt.get("title", ""),
                                          art=yt.get("art") or _yt_thumb(yt.get("videoId", ""))),
                               message=_t("already", label=yt.get("title") or query),
                               extra={"surface": "widget", "widget": _WID, "videoId": yt.get("videoId"),
                                      "noop": True})
        if not vid and query:
            vid, title = _resolve(query)
        if not vid:
            return MusicResult(ok=False, provider=self.name, action="play", reason="no_track",
                               message=_t("no_track", q=query or uri))
        if yt.get("videoId") and yt.get("videoId") != vid:
            _push_history(yt)
        yt.update({"videoId": vid, "title": title or query or vid, "query": query or "", "paused": False,
                   "muted": False, "volume": int(yt.get("volume") or 70), "art": _yt_thumb(vid)})
        _bump(yt, "load")
        return MusicResult(ok=True, provider=self.name, action="play",
                           track=Track(id=vid, uri=f"yt:{vid}", title=title or query or vid, art=_yt_thumb(vid)),
                           message=_t("play", label=title or query or "la música"),
                           extra={"surface": "widget", "widget": _WID, "videoId": vid})

    def enqueue(self, query: str = "", uri: str = "") -> MusicResult:
        """Add to the store queue (V2-047 F4). If NOTHING is playing, start now (queueing without playback would be
        mute). If something is playing, it stays queued and the widget's `ended` event will advance it."""
        q = (query or uri or "").strip()
        if not q:
            return MusicResult(ok=False, provider=self.name, action="queue", reason="no_track",
                               message=_t("no_track", q=""))
        yt = _load_yt()
        if not yt.get("videoId"):
            return self.play(query=query, uri=uri)      # nothing playing -> play instead of queueing
        queue = list(yt.get("queue") or [])
        queue.append(q)
        yt["queue"] = queue
        _bump(yt, "queue")
        return MusicResult(ok=True, provider=self.name, action="queue",
                           message=_t("queued", label=q, n=len(queue)),
                           extra={"surface": "widget", "widget": _WID, "queued": q, "queue_len": len(queue)})

    def on_ended(self) -> MusicResult:
        """The track ended (reported by the widget) -> play the next from the queue. If the queue is empty, do
        nothing (leave the last track loaded, implicitly paused after ending)."""
        yt = _load_yt()
        queue = list(yt.get("queue") or [])
        if not queue:
            return MusicResult(ok=True, provider=self.name, action="ended", reason="empty_queue",
                               extra={"surface": "widget", "widget": _WID})
        nxt = queue.pop(0)
        vid, title = _resolve(nxt)
        if not vid:
            # that one could not be resolved -> skip it and try the next (recursion bounded by the pop)
            yt["queue"] = queue
            _save_yt(yt)
            return self.on_ended()
        _push_history(yt)
        yt.update({"videoId": vid, "title": title or nxt, "query": nxt, "paused": False,
                   "muted": False, "queue": queue, "art": _yt_thumb(vid)})
        _bump(yt, "load")
        return MusicResult(ok=True, provider=self.name, action="ended",
                           track=Track(id=vid, uri=f"yt:{vid}", title=title or nxt, art=_yt_thumb(vid)),
                           message=_t("play", label=title or nxt),
                           extra={"surface": "widget", "widget": _WID, "videoId": vid, "queue_len": len(queue)})

    def _cmd(self, cmd: str, action: str, msg_key: str, **msg_kw) -> MusicResult:
        yt = _load_yt()
        if not yt.get("videoId"):
            return MusicResult(ok=False, provider=self.name, action=action, reason="no_track",
                               message=_t("no_track", q=""))
        if cmd == "pause":
            yt["paused"] = True
        elif cmd == "resume":
            yt["paused"] = False
        _bump(yt, cmd)
        return MusicResult(ok=True, provider=self.name, action=action, message=_t(msg_key, **msg_kw),
                           extra={"surface": "widget", "widget": _WID})

    def pause(self) -> MusicResult:
        return self._cmd("pause", "pause", "pause")

    def resume(self) -> MusicResult:
        return self._cmd("resume", "resume", "resume")

    def next(self) -> MusicResult:
        """Skip to the next queued track (V2-631). The free source CAN skip: every track is an independent
        resolved video, and the queue on_ended() advances through is exactly the remainder of whatever
        play_playlist loaded. This used to return "unsupported" with a canned refusal — measured absurd live
        (session 7be94951, 2026-09-09): the agent repeated «Con esta fuente gratis no puedo saltar de
        canción» while the operator skipped by hand, double-clicking rows of the same queue."""
        yt = _load_yt()
        if not yt.get("videoId"):
            return MusicResult(ok=False, provider=self.name, action="next", reason="no_track",
                               message=_t("no_track", q=""))
        if not (yt.get("queue") or []):
            return MusicResult(ok=False, provider=self.name, action="next", reason="empty_queue",
                               message=_t("no_next"))
        res = self.on_ended()                # same advance the natural end of a track uses
        return MusicResult(ok=res.ok, provider=self.name, action="next", track=res.track,
                           message=res.message, reason=res.reason, extra=res.extra)

    def previous(self) -> MusicResult:
        """Go back to the track that played before this one (V2-631). The current one is put back at the
        FRONT of the queue, so next() returns to it — skipping back and forth loses nothing."""
        yt = _load_yt()
        hist = list(yt.get("history") or [])
        if not hist:
            return MusicResult(ok=False, provider=self.name, action="previous", reason="no_previous",
                               message=_t("no_prev"))
        prev = hist.pop()
        cur_q = (yt.get("query") or yt.get("title") or "").strip()
        queue = list(yt.get("queue") or [])
        if yt.get("videoId") and cur_q:
            queue.insert(0, cur_q)
        vid = prev.get("videoId", "")
        yt.update({"videoId": vid, "title": prev.get("title") or prev.get("query") or vid,
                   "query": prev.get("query") or "", "paused": False, "muted": False,
                   "history": hist, "queue": queue, "art": _yt_thumb(vid)})
        _bump(yt, "load")
        return MusicResult(ok=True, provider=self.name, action="previous",
                           track=Track(id=vid, uri=f"yt:{vid}", title=yt["title"], art=yt["art"]),
                           message=_t("play", label=yt["title"] or "la música"),
                           extra={"surface": "widget", "widget": _WID, "videoId": vid})

    def set_volume(self, percent: int) -> MusicResult:
        pct = max(0, min(100, int(percent or 0)))
        yt = _load_yt()
        if not yt.get("videoId"):
            return MusicResult(ok=False, provider=self.name, action="volume", reason="no_track",
                               message=_t("no_track", q=""))
        yt["volume"] = pct
        yt["muted"] = pct == 0
        _bump(yt, "set_volume")
        return MusicResult(ok=True, provider=self.name, action="volume", message=_t("volume", n=pct),
                           extra={"surface": "widget", "widget": _WID})

    def now_playing(self) -> "NowPlaying | None":
        yt = _load_yt()
        if not yt.get("videoId"):
            return NowPlaying(playing=False, provider=self.name)
        return NowPlaying(playing=not bool(yt.get("paused")), volume=yt.get("volume"),
                          track=Track(id=yt.get("videoId", ""), title=yt.get("title", ""),
                                     art=yt.get("art") or _yt_thumb(yt.get("videoId", ""))),
                          provider=self.name)

    def status(self) -> dict:
        return {"provider": self.name, "connected": True, "kind": "in_browser_audio"}
