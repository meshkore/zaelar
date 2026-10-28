"""connectors/music/youtube_audio.py — FREE in-browser music provider (V2-041).

Fallback when Spotify is NOT available: resolves a song to a YouTube video and plays **only its AUDIO**, hidden,
INSIDE the `musica` widget (never the YouTube widget — these are separate things). It does not control a remote
device like Spotify: playback lives in the browser, so its "surface" is the widget (the client mounts a hidden iframe
and applies commands). This provider is the server-side FACE: resolves the `videoId` and leaves the command in the
`musica` widget store; `widget.js` applies it.

Always available (no login) -> DEFAULT provider when Spotify is not connected, so "play music" ALWAYS plays something.
"""
from __future__ import annotations

import logging
import random

from .base import MusicProvider, MusicResult, NowPlaying, Track
# `_accept_language` and `is_a_count_not_a_name` are read through this module by tests → kept importable here.
from .youtube_resolve import _accept_language, _extract_id, _resolve, is_a_count_not_a_name  # noqa: F401

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

def _norm_q(s: str) -> str:
    """Normalize a query for comparison (F5 no-restart): lowercase, no accents, no extra spaces."""
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _t(key: str, **kw) -> str:
    from i18n import langs as _langs
    return _langs.words(f"music.youtube.{key}", default="").format(**kw)


def _clock(seconds: float) -> str:
    """«2:07» — a position said the way a player writes it, never in raw seconds."""
    total = max(0, int(seconds))
    return f"{total // 60}:{total % 60:02d}"



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
    # V2-717 — «load» means a DIFFERENT song is now in the player, so a seek that was never applied belonged
    # to the previous one and must not follow it across. The local player's block is rebuilt from scratch on
    # every play and needs no equivalent; this one is updated in place, which is where a stale command hides.
    if cmd == "load":
        yt.pop("seek", None)
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
    plays_in_page = True                   # in the page of the screen that shows the music card (V2-812)

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
                           message=_t("play", label=title or query) if (title or query) else _t("play_untitled"),
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
        """The track ended (reported by the widget) -> what the play modes say comes next (V2-795): the same song
        again under «repeat one», otherwise the next queued one — at random under shuffle — with the song that
        just ended going to the back of the queue under «repeat all». An empty queue with no repeat does nothing
        (the last track stays loaded, implicitly paused after ending)."""
        return self._advance(manual=False)

    def _advance(self, manual: bool) -> MusicResult:
        yt = _load_yt()
        if not manual and yt.get("repeat") == "one" and yt.get("videoId"):
            return self._restart(yt, "ended")
        queue = list(yt.get("queue") or [])
        cur_q = (yt.get("query") or yt.get("title") or "").strip()
        if yt.get("repeat") == "all" and cur_q and yt.get("videoId"):
            queue.append(cur_q)              # the song that ends goes to the back: the queue never runs dry
        if not queue:
            return MusicResult(ok=True, provider=self.name, action="ended", reason="empty_queue",
                               extra={"surface": "widget", "widget": _WID})
        i = random.randrange(len(queue)) if (yt.get("shuffle") and len(queue) > 1) else 0
        nxt = queue.pop(i)
        vid, title = _resolve(nxt)
        if not vid:
            # that one could not be resolved -> skip it and try the next (recursion bounded by the pop)
            yt["queue"] = queue
            if yt.get("repeat") == "all" and cur_q and queue and queue[-1] == cur_q:
                queue.pop()                  # do not let the recursion append the current song once more
            _save_yt(yt)
            return self._advance(manual)
        if vid == yt.get("videoId"):         # «repeat all» over a one-song queue: the same video again
            yt["queue"] = queue
            return self._restart(yt, "ended")
        _push_history(yt)
        yt.update({"videoId": vid, "title": title or nxt, "query": nxt, "paused": False,
                   "muted": False, "queue": queue, "art": _yt_thumb(vid)})
        _bump(yt, "load")
        return MusicResult(ok=True, provider=self.name, action="ended",
                           track=Track(id=vid, uri=f"yt:{vid}", title=title or nxt, art=_yt_thumb(vid)),
                           message=_t("play", label=title or nxt),
                           extra={"surface": "widget", "widget": _WID, "videoId": vid, "queue_len": len(queue)})

    def _restart(self, yt: dict, action: str) -> MusicResult:
        """The SAME video from the top: a seek to 0 plus a play command — the iframe is never reloaded."""
        prev = dict(yt.get("seek") or {})
        yt["seek"] = {"n": int(prev.get("n") or 0) + 1, "to": 0.0}
        yt["paused"] = False
        _bump(yt, "seek")
        return MusicResult(ok=True, provider=self.name, action=action,
                           track=Track(id=yt.get("videoId", ""), title=yt.get("title", ""), art=yt.get("art") or ""),
                           extra={"surface": "widget", "widget": _WID, "videoId": yt.get("videoId"), "repeat": True})

    # ── play modes and the queue as a list (V2-795) ───────────────────────────────────────────────────────
    def set_shuffle(self, on: bool) -> MusicResult:
        yt = _load_yt()
        yt["shuffle"] = bool(on)
        _save_yt(yt)                         # no command bump: the player has nothing to do until the song ends
        return MusicResult(ok=True, provider=self.name, action="shuffle", message=_t("done"),
                           extra={"surface": "widget", "widget": _WID, "shuffle": bool(on)})

    def set_repeat(self, mode: str) -> MusicResult:
        mode = mode if mode in ("off", "one", "all") else "off"
        yt = _load_yt()
        yt["repeat"] = mode
        _save_yt(yt)
        return MusicResult(ok=True, provider=self.name, action="repeat", message=_t("done"),
                           extra={"surface": "widget", "widget": _WID, "repeat": mode})

    def queue_items(self) -> "list[Track]":
        return [Track(title=q, uri="") for q in (_load_yt().get("queue") or []) if str(q).strip()]

    def queue_edit(self, op: str, index: int = -1, to: int = -1) -> MusicResult:
        """The queue is ours (a list of query strings in the store), so all three edits are real here. Nothing
        is reloaded: `cmd_seq` is not bumped, so the song that is playing is never touched."""
        yt = _load_yt()
        queue = list(yt.get("queue") or [])
        act = "queue_" + str(op or "")
        if op == "clear":
            queue = []
        elif op in ("remove", "move"):
            if not 0 <= index < len(queue):
                return MusicResult(ok=False, provider=self.name, action=act, reason="no_track",
                                   message=_t("no_track", q=str(index + 1)))
            item = queue.pop(index)
            if op == "move":
                queue.insert(max(0, min(len(queue), to)), item)
        else:
            return MusicResult(ok=False, provider=self.name, action=act, reason="unsupported")
        yt["queue"] = queue
        _save_yt(yt)
        return MusicResult(ok=True, provider=self.name, action=act, message=_t("done"),
                           extra={"surface": "widget", "widget": _WID, "queue_len": len(queue)})

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
        if not (yt.get("queue") or []) and yt.get("repeat") != "all":
            return MusicResult(ok=False, provider=self.name, action="next", reason="empty_queue",
                               message=_t("no_next"))
        res = self._advance(manual=True)     # the natural end's advance, minus «repeat one» (a skip is a skip)
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
                           message=_t("play", label=yt["title"]) if yt["title"] else _t("play_untitled"),
                           extra={"surface": "widget", "widget": _WID, "videoId": vid})

    def seek(self, seconds: float = 0.0, relative: bool = False) -> MusicResult:
        """Move the playhead (V2-717) — by leaving an INTENTION in the store, not by moving anything here.

        This provider is the odd one: the sound is made by a hidden iframe inside the operator's page, and
        the only clock that knows where the song is lives there too. So a seek travels the same road every
        other command on this provider travels — written into the `yt` block, noticed by the widget on the
        next SSE render, applied by the player that actually has the playhead.

        It carries a counter of its OWN (`seek.n`) rather than riding on `cmd_seq`: a seek that re-applied
        itself every time a later pause or volume command bumped the shared sequence would be a song that
        jumps backwards whenever you touch the volume.
        """
        yt = _load_yt()
        if not yt.get("videoId"):
            return MusicResult(ok=False, provider=self.name, action="seek", reason="no_track",
                               message=_t("no_track", q=""))
        secs = float(seconds or 0.0)
        prev = dict(yt.get("seek") or {})
        cmd = {"n": int(prev.get("n") or 0) + 1}
        if relative:
            cmd["by"] = secs
        else:
            cmd["to"] = max(0.0, secs)
        yt["seek"] = cmd
        _bump(yt, "seek")
        msg = _t("seek") if relative else _t("seek_to", t=_clock(max(0.0, secs)))
        return MusicResult(ok=True, provider=self.name, action="seek", message=msg,
                           extra={"surface": "widget", "widget": _WID})

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
                          provider=self.name, shuffle=bool(yt.get("shuffle")),
                          repeat=str(yt.get("repeat") or "off"))

    def status(self) -> dict:
        return {"provider": self.name, "connected": True, "kind": "in_browser_audio"}
