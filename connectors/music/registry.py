"""connectors/music/registry.py — music provider registry (V2-041).

One place where `MusicProvider` implementations live. Built-in providers load LAZILY (`_ensure_loaded`) so seam
imports are not coupled to any specific connector (nor pay its cost if nobody uses it). Add a new provider =
register it in `_BUILTIN`.

`active()` chooses the provider to use THIS turn: the first CONNECTED one (optional preference by name, e.g. the one
set by the operator). Deterministic and cheap — no network (only checks credentials/session on disk).
"""
from __future__ import annotations

import logging

from .base import MusicProvider

logger = logging.getLogger("zaelar.music")

# name -> factory (zero-arg callable -> instance). Lazy: do not import the connector until needed.
# ORDER = PRIORITY for `active()`: Spotify FIRST (if session exists) -> YouTube-audio as FREE fallback (always
# available, no login, in the browser). This way "play music" ALWAYS plays something even with no connected account.
_BUILTIN: "dict[str, str]" = {
    "spotify": "connectors.spotify:provider",
    "youtube": "connectors.music.youtube_audio:YouTubeAudioProvider",
}

_PROVIDERS: "dict[str, MusicProvider]" = {}
_loaded = False


def register(provider: MusicProvider) -> None:
    """Register a provider instance (idempotent by `name`)."""
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
        except Exception as e:  # noqa: BLE001 — a broken provider does not take down the rest or voice
            logger.warning(f"proveedor de música '{name}' no cargó: {e!r}")


def providers() -> "list[MusicProvider]":
    _ensure_loaded()
    return list(_PROVIDERS.values())


def get(name: str) -> "MusicProvider | None":
    _ensure_loaded()
    return _PROVIDERS.get((name or "").strip().lower())


def available() -> "list[MusicProvider]":
    """Providers CONNECTED right now (can play immediately)."""
    out = []
    for p in providers():
        try:
            if p.connected():
                out.append(p)
        except Exception:  # noqa: BLE001
            pass
    return out


def active(prefer: str = "") -> "MusicProvider | None":
    """Provider to use this turn: preferred if connected, otherwise the first connected one. None = none."""
    avail = available()
    if not avail:
        return None
    prefer = (prefer or "").strip().lower()
    if prefer:
        for p in avail:
            if p.name == prefer:
                return p
    return avail[0]
