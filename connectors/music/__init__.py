"""connectors/music/ — capa COMPARTIDA de música, agnóstica del proveedor (V2-041).

Fachada única que usan el FlashBrain (tool `play_music`) y —pieza SEPARADA, más adelante— el widget de música.
Enruta la intención ("pon música", "ponme a Frank Sinatra", "pausa", "sube el volumen") al proveedor CONECTADO
(hoy Spotify; el seam admite cualquier conector de streaming). Nunca lanza al llamante: devuelve un `MusicResult`
con una frase hablable. I/O de red → el llamante la corre con `asyncio.to_thread` (respeta V2-011).
"""
from __future__ import annotations

import logging

from . import registry
from .base import MusicProvider, MusicResult, NowPlaying, Track

logger = logging.getLogger("zaelar.music")

# Acciones de control SIN datos (todas menos 'play', que puede llevar query/uri).
_CONTROL = {"pause", "resume", "next", "previous", "stop"}
_VOLUME = {"volume_up", "volume_down", "set_volume"}

# Mensajes hablables por idioma del operador (monolingüe, V2-013; es/en son los idiomas con voz verificada). El
# proveedor rellena sus propios `message`; estos cubren los casos del seam (sin proveedor / sin idioma soportado).
_MSG = {
    "es": {
        "no_provider": ("No tengo ninguna cuenta de música conectada. Conéctame Spotify (u otra) desde la "
                        "configuración y podré ponerte lo que quieras."),
        "done": "Hecho.",
    },
    "en": {
        "no_provider": ("I don't have a music account connected yet. Connect Spotify (or another) from settings "
                        "and I'll play whatever you like."),
        "done": "Done.",
    },
}


def _lang() -> str:
    try:
        from voice.engine.core import langs
        code = (langs.current_code() or "es").lower()
        return code if code in _MSG else "es"
    except Exception:
        return "es"


def _msg(key: str) -> str:
    return _MSG[_lang()][key]


def active_provider(prefer: str = "") -> "MusicProvider | None":
    return registry.active(prefer)


def available() -> "list[str]":
    """Nombres de los proveedores conectados ahora mismo."""
    return [p.name for p in registry.available()]


def control(action: str, query: str = "", uri: str = "", percent: int = 0, prefer: str = "") -> MusicResult:
    """Ejecuta UNA acción de música contra el proveedor activo. `action`: play|pause|resume|next|previous|stop|
    volume_up|volume_down|set_volume. Fachada del FlashBrain — fail-safe, nunca lanza."""
    action = (action or "play").strip().lower()
    prov = active_provider(prefer)
    if prov is None:
        return MusicResult(ok=False, action=action, reason="no_provider", message=_msg("no_provider"))
    try:
        if action == "play":
            return prov.play(query=query, uri=uri)
        if action == "pause":
            return prov.pause()
        if action in ("resume", "reanuda", "sigue"):
            return prov.resume()
        if action == "next":
            return prov.next()
        if action in ("previous", "prev", "back"):
            return prov.previous()
        if action == "stop":                       # 'stop' = pausar (parar la música, no matar procesos)
            return prov.pause()
        if action == "queue":                       # V2-047 F4: añade a la cola (una detrás de otra)
            return prov.enqueue(query=query, uri=uri)
        if action == "ended":                       # V2-047 F4: el widget avisa que terminó → siguiente de la cola
            return prov.on_ended()
        if action == "volume_up":
            np = prov.now_playing()
            cur = (np.volume if np and np.volume is not None else 60)
            return prov.set_volume(min(100, cur + 15))
        if action == "volume_down":
            np = prov.now_playing()
            cur = (np.volume if np and np.volume is not None else 60)
            return prov.set_volume(max(0, cur - 15))
        if action == "set_volume":
            return prov.set_volume(max(0, min(100, int(percent or 0))))
    except Exception as e:  # noqa: BLE001 — un fallo del proveedor nunca rompe la voz
        logger.warning(f"music.control({action}) falló: {e!r}")
        return MusicResult(ok=False, provider=prov.name, action=action, reason="error",
                           message=_msg("done"))
    return MusicResult(ok=False, provider=prov.name, action=action, reason="error", message=_msg("done"))


def now_playing(prefer: str = "") -> "NowPlaying | None":
    prov = active_provider(prefer)
    if prov is None:
        return None
    try:
        return prov.now_playing()
    except Exception:  # noqa: BLE001
        return None


def status() -> dict:
    """Estado de TODOS los proveedores conocidos (para la UI/wizard/diagnóstico)."""
    out = {}
    for p in registry.providers():
        try:
            out[p.name] = p.status()
        except Exception:  # noqa: BLE001
            out[p.name] = {"provider": p.name, "connected": False}
    return {"providers": out, "available": available()}


__all__ = ["control", "now_playing", "status", "available", "active_provider",
           "MusicProvider", "MusicResult", "NowPlaying", "Track", "registry"]
