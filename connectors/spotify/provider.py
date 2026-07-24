"""connectors/spotify/provider.py — Spotify como `MusicProvider` (V2-041).

Implementa el contrato agnóstico de `connectors.music.base` sobre `client.py` + `auth.py`. Traduce los resultados
de la Web API a `Track`/`NowPlaying`/`MusicResult` con frases HABLABLES en el idioma del operador, y resuelve el
caso NO_ACTIVE_DEVICE (busca un dispositivo Spotify Connect y le manda la orden) sin molestar al operador salvo que
no haya ninguno. Fail-safe: nunca lanza; cualquier fallo → `MusicResult(ok=False,...)` con una frase amable.
"""
from __future__ import annotations

import logging

from connectors.music.base import MusicProvider, MusicResult, NowPlaying, Track

from . import auth, client
from .client import SpotifyError

logger = logging.getLogger("zaelar.music.spotify")

_M = {
    "es": {
        "play": "Suena {label}.",
        "resume": "Sigo con la música.",
        "pause": "Pausado.",
        "next": "Siguiente.",
        "previous": "Anterior.",
        "volume": "Volumen al {n} por ciento.",
        "no_track": "No he encontrado «{q}» en Spotify.",
        "no_device": ("No veo ningún dispositivo de Spotify activo. Abre Spotify en el móvil o el ordenador y te "
                      "lo pongo enseguida."),
        "premium": "Controlar la reproducción de Spotify necesita una cuenta Premium.",
        "not_connected": "Necesito que conectes tu cuenta de Spotify primero, desde la configuración.",
        "error": "No he podido con Spotify ahora mismo.",
    },
    "en": {
        "play": "Now playing {label}.",
        "resume": "Resuming.",
        "pause": "Paused.",
        "next": "Next track.",
        "previous": "Previous track.",
        "volume": "Volume at {n} percent.",
        "no_track": "I couldn't find \"{q}\" on Spotify.",
        "no_device": "I don't see an active Spotify device. Open Spotify on your phone or computer and I'll play it.",
        "premium": "Controlling Spotify playback needs a Premium account.",
        "not_connected": "Connect your Spotify account first, from settings.",
        "error": "Spotify didn't respond just now.",
    },
}


def _lang() -> str:
    try:
        from voice.engine.core import langs
        code = (langs.current_code() or "es").lower()
        return code if code in _M else "es"
    except Exception:
        return "es"


def _t(key: str, **kw) -> str:
    return _M[_lang()][key].format(**kw)


def _track_from(item: dict) -> "Track | None":
    if not item:
        return None
    artists = ", ".join(a.get("name", "") for a in (item.get("artists") or []) if a.get("name"))
    imgs = ((item.get("album") or {}).get("images") or [])
    return Track(
        id=item.get("id", ""),
        uri=item.get("uri", ""),
        title=item.get("name", ""),
        artist=artists,
        album=(item.get("album") or {}).get("name", ""),
        art=(imgs[0].get("url", "") if imgs else ""),
        duration_ms=int(item.get("duration_ms") or 0),
    )


class SpotifyProvider(MusicProvider):
    name = "spotify"

    def connected(self) -> bool:
        return bool(auth.client_id()) and auth.logged_in()

    # ── búsqueda ───────────────────────────────────────────────────────────────────────────────────────
    def search(self, query: str, limit: int = 5) -> "list[Track]":
        if not (query or "").strip():
            return []
        try:
            res = client.search(query, types="track", limit=limit)
        except SpotifyError as e:
            logger.warning(f"búsqueda Spotify falló: {e}")
            return []
        items = ((res or {}).get("tracks") or {}).get("items") or []
        return [t for t in (_track_from(i) for i in items) if t]

    # ── resolución de dispositivo (NO_ACTIVE_DEVICE) ─────────────────────────────────────────────────────
    def _pick_device(self) -> str:
        """id del dispositivo a usar: el activo, si no el primero disponible; '' si no hay ninguno."""
        try:
            devs = client.devices()
        except SpotifyError:
            return ""
        if not devs:
            return ""
        for d in devs:
            if d.get("is_active"):
                return d.get("id", "")
        return devs[0].get("id", "")

    def _run(self, fn, action: str, track: "Track | None" = None, msg_kw: dict = None) -> MusicResult:
        """Ejecuta una acción del reproductor con recuperación de NO_ACTIVE_DEVICE (reintenta con un device_id)."""
        msg_kw = msg_kw or {}
        try:
            fn("")
            return MusicResult(ok=True, provider=self.name, action=action, track=track,
                               message=_t(action, **msg_kw))
        except SpotifyError as e:
            if e.code == "no_device":
                dev = self._pick_device()
                if not dev:
                    return MusicResult(ok=False, provider=self.name, action=action, reason="no_device",
                                       message=_t("no_device"))
                try:
                    fn(dev)
                    return MusicResult(ok=True, provider=self.name, action=action, track=track,
                                       message=_t(action, **msg_kw))
                except SpotifyError as e2:
                    return self._fail(action, e2)
            return self._fail(action, e)

    def _fail(self, action: str, e: SpotifyError) -> MusicResult:
        reason = {"premium": "premium", "auth": "not_connected", "no_device": "no_device"}.get(e.code, "error")
        key = {"premium": "premium", "not_connected": "not_connected", "no_device": "no_device"}.get(reason, "error")
        logger.warning(f"Spotify {action} → {e}")
        return MusicResult(ok=False, provider=self.name, action=action, reason=reason, message=_t(key))

    # ── control ──────────────────────────────────────────────────────────────────────────────────────────
    def play(self, query: str = "", uri: str = "") -> MusicResult:
        track = None
        if query and not uri:
            hits = self.search(query, limit=1)
            if not hits:
                return MusicResult(ok=False, provider=self.name, action="play", reason="no_track",
                                   message=_t("no_track", q=query))
            track = hits[0]
            uri = track.uri
        if uri:
            return self._run(lambda dev: client.play(uris=[uri], device_id=dev), "play", track,
                             {"label": track.label() if track else uri})
        return self._run(lambda dev: client.resume(device_id=dev), "resume")

    def pause(self) -> MusicResult:
        return self._run(lambda dev: client.pause(device_id=dev), "pause")

    def resume(self) -> MusicResult:
        return self._run(lambda dev: client.resume(device_id=dev), "resume")

    def next(self) -> MusicResult:
        return self._run(lambda dev: client.next_track(device_id=dev), "next")

    def previous(self) -> MusicResult:
        return self._run(lambda dev: client.previous_track(device_id=dev), "previous")

    def set_volume(self, percent: int) -> MusicResult:
        pct = max(0, min(100, int(percent or 0)))
        return self._run(lambda dev: client.set_volume(pct, device_id=dev), "volume", None, {"n": pct})

    # ── estado ─────────────────────────────────────────────────────────────────────────────────────────
    def now_playing(self) -> "NowPlaying | None":
        try:
            st = client.playback_state()
        except SpotifyError:
            return None
        if not st:
            return NowPlaying(playing=False, provider=self.name)
        dev = st.get("device") or {}
        return NowPlaying(
            playing=bool(st.get("is_playing")),
            track=_track_from(st.get("item") or {}),
            device=dev.get("name", ""),
            volume=dev.get("volume_percent"),
            provider=self.name,
        )

    def status(self) -> dict:
        s = auth.status()
        s.update({"provider": self.name, "connected": self.connected()})
        return s
