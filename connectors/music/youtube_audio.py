"""connectors/music/youtube_audio.py — proveedor de música GRATIS, en el navegador (V2-041).

Fallback cuando NO hay Spotify: resuelve una canción a un vídeo de YouTube y reproduce **solo su AUDIO**, oculto,
DENTRO del widget `musica` (nunca el widget de YouTube — son cosas distintas). No controla un dispositivo remoto
como Spotify: la reproducción vive en el navegador, así que su "surface" es el widget (el cliente monta un iframe
oculto y aplica los comandos). Este proveedor es la CARA-servidor: resuelve el `videoId` y deja el comando en el
store del widget `musica`; el `widget.js` lo aplica.

Siempre disponible (sin login) → es el proveedor por DEFECTO cuando Spotify no está conectado, para que "pon música"
SIEMPRE suene algo. Resolución del vídeo: **YouTube Data API** si hay `YOUTUBE_API_KEY` (rápida y fiable), si no un
scrape stdlib de la página de resultados (best-effort, fail-open) — copia PROPIA, no toca el widget de YouTube.
"""
from __future__ import annotations

import logging
import os
import re
import urllib.parse
import urllib.request

from .base import MusicProvider, MusicResult, NowPlaying, Track

logger = logging.getLogger("zaelar.music.youtube")

_WID = "musica"                              # el AUDIO oculto vive en el widget de MÚSICA (no el de YouTube)
_MSG = {
    "es": {"play": "Suena {label}.", "pause": "Pausado.", "resume": "Sigo.", "volume": "Volumen al {n} por ciento.",
           "no_track": "No he encontrado «{q}».", "unsupported": "Con esta fuente gratis no puedo saltar de canción; "
                        "dime qué pongo.", "done": "Hecho.",
           "already": "Ya está sonando {label}.", "queued": "Vale, después pongo {label}."},
    "en": {"play": "Now playing {label}.", "pause": "Paused.", "resume": "Resuming.", "volume": "Volume at {n} percent.",
           "no_track": "I couldn't find \"{q}\".", "unsupported": "I can't skip tracks on the free source; tell me what "
                       "to play.", "done": "Done.",
           "already": "{label} is already playing.", "queued": "Got it, I'll play {label} next."},
}


def _norm_q(s: str) -> str:
    """Normaliza una query para comparar (F5 no-restart): minúsculas, sin acentos, sin espacios extra."""
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


# ── resolución query → (videoId, title) ──────────────────────────────────────────────────────────────────
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


def _resolve_scrape(query: str) -> tuple:
    try:
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query + " audio")
        req = urllib.request.Request(url, headers={
            "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"),
            "Accept-Language": "es-ES,es;q=0.9"})
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
    if vid:
        return vid, title
    return _resolve_scrape(query)


_YT_URL_RE = re.compile(r"(?:v=|youtu\.be/|/embed/|^)([0-9A-Za-z_-]{11})")


def _extract_id(uri: str) -> str:
    m = _YT_URL_RE.search((uri or "").replace("yt:", ""))
    return m.group(1) if m else ""


# ── estado en el store del widget musica (bloque 'yt') ─────────────────────────────────────────────────────
def _load_yt() -> dict:
    try:
        from widgets import store
        db = store.load(_WID, {})
        return dict(db.get("yt") or {})
    except Exception:
        return {}


def _save_yt(yt: dict) -> None:
    """Persiste el bloque 'yt' en el store del widget musica (dispara SSE → el widget re-renderiza y aplica)."""
    try:
        from widgets import store
        db = store.load(_WID, {})
        db["yt"] = yt
        store.save(_WID, db)               # ÚNICO punto que emite "cambió el widget" (V2-017)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"no pude escribir el estado yt del widget musica: {e!r}")


def _bump(yt: dict, cmd: str) -> dict:
    yt["last_cmd"] = cmd
    yt["cmd_seq"] = int(yt.get("cmd_seq") or 0) + 1
    _save_yt(yt)
    return yt


class YouTubeAudioProvider(MusicProvider):
    name = "youtube"

    def connected(self) -> bool:
        return True                        # gratis, sin login → SIEMPRE disponible (es el fallback por defecto)

    def search(self, query: str, limit: int = 5) -> "list[Track]":
        vid, title = _resolve(query)
        return [Track(id=vid, uri=f"yt:{vid}", title=title)] if vid else []

    def play(self, query: str = "", uri: str = "") -> MusicResult:
        vid = _extract_id(uri)
        title = ""
        yt = _load_yt()
        # GUARD NO-REINICIAR (V2-047 F5): si el operador pide reproducir con la MISMA query que ya está sonando
        # (una queja o un re-lanzamiento del modelo no-razonador: T27/T31 sesión 23:15 reiniciaban la canción),
        # NO re-resolvemos ni recargamos el iframe → no se corta la música. Determinista sobre la query normalizada
        # (no una tabla de palabras): "Shakira"==query previa → no-op; "otra de Shakira" ≠ → sí reproduce nueva.
        nq = _norm_q(query)
        if nq and not uri and nq == _norm_q(yt.get("query") or "") and yt.get("videoId") and not yt.get("paused"):
            return MusicResult(ok=True, provider=self.name, action="play",
                               track=Track(id=yt.get("videoId", ""), title=yt.get("title", "")),
                               message=_t("already", label=yt.get("title") or query),
                               extra={"surface": "widget", "widget": _WID, "videoId": yt.get("videoId"),
                                      "noop": True})
        if not vid and query:
            vid, title = _resolve(query)
        if not vid:
            return MusicResult(ok=False, provider=self.name, action="play", reason="no_track",
                               message=_t("no_track", q=query or uri))
        yt.update({"videoId": vid, "title": title or query or vid, "query": query or "", "paused": False,
                   "muted": False, "volume": int(yt.get("volume") or 70)})
        _bump(yt, "load")
        return MusicResult(ok=True, provider=self.name, action="play",
                           track=Track(id=vid, uri=f"yt:{vid}", title=title or query or vid),
                           message=_t("play", label=title or query or "la música"),
                           extra={"surface": "widget", "widget": _WID, "videoId": vid})

    def enqueue(self, query: str = "", uri: str = "") -> MusicResult:
        """Añade a la cola del store (V2-047 F4). Si NO hay nada sonando, arranca ya (encolar sin reproducir sería
        mudo). Si suena algo, se queda en cola y el evento `ended` del widget la avanzará."""
        q = (query or uri or "").strip()
        if not q:
            return MusicResult(ok=False, provider=self.name, action="queue", reason="no_track",
                               message=_t("no_track", q=""))
        yt = _load_yt()
        if not yt.get("videoId"):
            return self.play(query=query, uri=uri)      # nada sonando → reproducir en vez de encolar
        queue = list(yt.get("queue") or [])
        queue.append(q)
        yt["queue"] = queue
        _bump(yt, "queue")
        return MusicResult(ok=True, provider=self.name, action="queue",
                           message=_t("queued", label=q, n=len(queue)),
                           extra={"surface": "widget", "widget": _WID, "queued": q, "queue_len": len(queue)})

    def on_ended(self) -> MusicResult:
        """La pista terminó (lo avisa el widget) → reproduce la siguiente de la cola. Si la cola está vacía, no
        hace nada (deja el último tema cargado, en pausa implícita al acabar)."""
        yt = _load_yt()
        queue = list(yt.get("queue") or [])
        if not queue:
            return MusicResult(ok=True, provider=self.name, action="ended", reason="empty_queue",
                               extra={"surface": "widget", "widget": _WID})
        nxt = queue.pop(0)
        vid, title = _resolve(nxt)
        if not vid:
            # esa no se pudo resolver → sáltala y prueba la siguiente (recursivo acotado por el pop)
            yt["queue"] = queue
            _save_yt(yt)
            return self.on_ended()
        yt.update({"videoId": vid, "title": title or nxt, "query": nxt, "paused": False,
                   "muted": False, "queue": queue})
        _bump(yt, "load")
        return MusicResult(ok=True, provider=self.name, action="ended",
                           track=Track(id=vid, uri=f"yt:{vid}", title=title or nxt),
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
        return MusicResult(ok=False, provider=self.name, action="next", reason="unsupported",
                           message=_t("unsupported"))

    def previous(self) -> MusicResult:
        return MusicResult(ok=False, provider=self.name, action="previous", reason="unsupported",
                           message=_t("unsupported"))

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
                          track=Track(id=yt.get("videoId", ""), title=yt.get("title", "")), provider=self.name)

    def status(self) -> dict:
        return {"provider": self.name, "connected": True, "kind": "in_browser_audio"}
