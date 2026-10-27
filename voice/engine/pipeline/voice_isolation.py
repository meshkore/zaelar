"""Agent-side voice isolation on the room's audio input (V2-812 T-08).

The browser's own processing (echo cancellation, noise suppression, gain control) runs on the user's device and is
as good as that device makes it: a phone on a car's dashboard hands the engine road noise and other passengers. The
LiveKit Agents SDK can run a noise-cancellation filter on the agent's side of the room, on every inbound audio frame,
before VAD and STT see it. This module decides whether that filter is attached.

The mechanism, one setting, default OFF:

    ZAELAR_VOICE_ISOLATION = off | nc | bvc
        off  — nothing is attached; the session is exactly what it was before this module existed.
        nc   — noise cancellation (stationary and non-stationary noise).
        bvc  — background voice cancellation: noise AND voices other than the main speaker.

It FAILS OPEN. The filter is `livekit-plugins-noise-cancellation`, whose models run only against a LiveKit Cloud
project — a self-hosted `livekit-server` cannot serve them. So when the setting is on but the room is not on LiveKit
Cloud, the plugin is missing, or it cannot load on this platform, the session starts exactly as with `off` and ONE
warning per process says why. A voice session that does not come up because of an optional filter would be a far
worse failure than the noise it was meant to remove.

ORDER MATTERS: register the plugin BEFORE the room connects (`preload`, called right before `ctx.connect()`).
Importing the plugin registers it with the FFI, and the FFI initialises (authenticates) every registered filter
for a room once, at connect time. A plugin registered after connect is never initialised for that room, so the
stream's filter fails with «noise cancellation was not initialized for this connection» (code 209) and the
session runs unfiltered. Newer FFI builds re-run that step for rooms already connected; ours does not, and the
order is right on every version.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

logger = logging.getLogger("zaelar.voice_isolation")

FILTERS = {"nc": "NC", "bvc": "BVC"}   # mode → the plugin's constructor; «off» is the absence of one
_CLOUD_SUFFIX = ".livekit.cloud"
_warned: set[str] = set()


def _warn_once(reason: str, msg: str, *args) -> None:
    if reason in _warned:
        return
    _warned.add(reason)
    logger.warning("voice isolation requested but NOT applied — " + msg, *args)


def is_livekit_cloud(url: str) -> bool:
    """True when the LiveKit URL points at a LiveKit Cloud project (the only transport that serves the filter)."""
    host = (urlparse(url or "").hostname or "").lower()
    return host.endswith(_CLOUD_SUFFIX)


def _plugin():
    """The noise-cancellation plugin module, imported lazily: it loads a native library on import."""
    from livekit.plugins import noise_cancellation
    return noise_cancellation


def noise_filter(mode: str, livekit_url: str, *, load=_plugin):
    """The filter to attach to the room's audio input, or None for «run as today».

    `load` is the plugin import, injectable so the fail-open branches are testable without the native library."""
    mode = (mode or "off").strip().lower()
    if mode == "off":
        return None
    if mode not in FILTERS:
        _warn_once("mode", "unknown ZAELAR_VOICE_ISOLATION=%r (expected off, %s)", mode, ", ".join(FILTERS))
        return None
    if not is_livekit_cloud(livekit_url):
        # The default is on, so a self-hosted server is the ordinary case here, not a misconfiguration: say it once,
        # quietly.
        if "transport" not in _warned:
            _warned.add("transport")
            logger.info("voice isolation skipped: it needs a LiveKit Cloud project (LIVEKIT_URL=%r)", livekit_url)
        return None
    try:
        nc = load()
        return getattr(nc, FILTERS[mode])()
    except Exception as e:   # ImportError when not installed, OSError/RuntimeError when the native lib cannot load
        _warn_once("plugin", "livekit-plugins-noise-cancellation unavailable (%s: %s)", type(e).__name__, e)
        return None


def preload(mode: str, livekit_url: str, *, load=_plugin) -> bool:
    """Register the plugin with the FFI so the next room connect initialises it. Call BEFORE `ctx.connect()`.

    Same gates and same fail-open as `noise_filter`; True when the plugin is registered. Idempotent: the import is
    cached, so every session after the first pays nothing."""
    return noise_filter(mode, livekit_url, load=load) is not None


def room_options(mode: str, livekit_url: str, *, load=_plugin) -> dict:
    """Extra `AgentSession.start` kwargs: `room_options` with the filter when one applies, else nothing at all."""
    f = noise_filter(mode, livekit_url, load=load)
    if f is None:
        return {}
    from livekit.agents.voice import room_io
    logger.info("voice isolation ON (%s) on the room's audio input", mode)
    return {"room_options": room_io.RoomOptions(audio_input=room_io.AudioInputOptions(noise_cancellation=f))}
