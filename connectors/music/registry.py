"""connectors/music/registry.py — registro de proveedores de música (V2-041).

Un solo sitio donde viven las implementaciones de `MusicProvider`. Los proveedores de fábrica se cargan de forma
PEREZOSA (`_ensure_loaded`) para no acoplar el import del seam a ningún conector concreto (ni pagar su coste si
nadie lo usa). Añadir un proveedor nuevo = registrarlo en `_BUILTIN`.

`active()` elige el proveedor a usar ESTE turno: el primero CONECTADO (preferencia opcional por nombre, p.ej. la
que el operador tenga fijada). Determinista y barato — sin red (solo mira credenciales/sesión en disco).
"""
from __future__ import annotations

import logging

from .base import MusicProvider

logger = logging.getLogger("zaelar.music")

# nombre → factoría (callable sin args → instancia). Perezoso: no se importa el conector hasta que hace falta.
# ORDEN = PRIORIDAD de `active()`: Spotify PRIMERO (si hay sesión) → YouTube-audio como fallback GRATIS (siempre
# disponible, sin login, en el navegador). Así "pon música" SIEMPRE suena algo aunque no haya cuenta conectada.
_BUILTIN: "dict[str, str]" = {
    "spotify": "connectors.spotify:provider",
    "youtube": "connectors.music.youtube_audio:YouTubeAudioProvider",
}

_PROVIDERS: "dict[str, MusicProvider]" = {}
_loaded = False


def register(provider: MusicProvider) -> None:
    """Registra una instancia de proveedor (idempotente por `name`)."""
    if provider and getattr(provider, "name", ""):
        _PROVIDERS[provider.name] = provider


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    for name, target in _BUILTIN.items():
        if name in _PROVIDERS:
            continue
        try:
            mod_name, attr = target.split(":", 1)
            mod = __import__(mod_name, fromlist=[attr])
            prov = getattr(mod, attr)
            prov = prov() if callable(prov) and not isinstance(prov, MusicProvider) else prov
            register(prov)
        except Exception as e:  # noqa: BLE001 — un proveedor roto no tumba el resto ni la voz
            logger.warning(f"proveedor de música '{name}' no cargó: {e!r}")


def providers() -> "list[MusicProvider]":
    _ensure_loaded()
    return list(_PROVIDERS.values())


def get(name: str) -> "MusicProvider | None":
    _ensure_loaded()
    return _PROVIDERS.get((name or "").strip().lower())


def available() -> "list[MusicProvider]":
    """Los proveedores CONECTADOS ahora mismo (pueden reproducir ya)."""
    out = []
    for p in providers():
        try:
            if p.connected():
                out.append(p)
        except Exception:  # noqa: BLE001
            pass
    return out


def active(prefer: str = "") -> "MusicProvider | None":
    """El proveedor a usar este turno: el preferido si está conectado, si no el primer conectado. None = ninguno."""
    avail = available()
    if not avail:
        return None
    prefer = (prefer or "").strip().lower()
    if prefer:
        for p in avail:
            if p.name == prefer:
                return p
    return avail[0]
