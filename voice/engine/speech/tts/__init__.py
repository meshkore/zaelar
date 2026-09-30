"""TTS family — streaming, interruptible text-to-speech (remote or local).

V2-778 F0-7 — the table's `tts.failover` row is a MECHANISM, not a note. `build_tts()` builds the selected provider
AND the table's stand-in; when both build, LiveKit's own `FallbackAdapter` switches to the stand-in the moment a
synthesis fails for good (a 402 from a provider out of credit is exactly that), and when the selected one cannot
even be built (a missing key raises `ValueError` in the plugin) the stand-in serves alone. Before this, a missing
`INWORLD_API_KEY` failed the prewarm and a 402 left the voice mute until someone switched the panel by hand.

`active_provider()` names the backend that is producing audio NOW, so the metering hook bills the one that spoke.
"""
from __future__ import annotations

import logging

from ...core.config import SETTINGS
from ...core.registry import Registry

registry = Registry("TTS")
logger = logging.getLogger("zaelar.tts")

_ACTIVE: dict = {"name": ""}


def _stand_in(primary: str) -> str:
    """The table's failover provider for the voice, when it is a different provider we can build."""
    try:
        from config import models as _models
        row = _models.failover("tts") or {}
    except Exception:  # noqa: BLE001 — no table row means no stand-in, never a boot failure
        return ""
    name = str(row.get("provider") or "").strip()
    return name if name and name != primary and name in registry.names() else ""


def active_provider() -> str:
    """The provider producing audio now: the selected one until the adapter gave up on it."""
    return _ACTIVE["name"] or SETTINGS.tts_provider


def _note(msg: str, **extra) -> None:
    logger.warning(msg)
    try:
        from voice.observer import emit
        emit("alert", msg, role="system", extra={"cat": "tts", **extra})
    except Exception:  # noqa: BLE001
        pass


def build_tts():
    primary = SETTINGS.tts_provider
    _ACTIVE["name"] = primary
    backup = _stand_in(primary)
    try:
        first = registry.create(primary)
    except Exception as e:  # noqa: BLE001 — e.g. ValueError: the plugin found no API key
        if not backup:
            raise
        try:
            only = registry.create(backup)
        except Exception:  # noqa: BLE001
            raise e from None
        _ACTIVE["name"] = backup
        _note(f"🔇 TTS «{primary}» could not be built ({type(e).__name__}: {e}) — speaking with «{backup}»",
              provider=primary, stand_in=backup)
        return only
    if not backup:
        return first
    try:
        second = registry.create(backup)
    except Exception as e:  # noqa: BLE001 — a stand-in without its key is simply not offered
        logger.info("TTS stand-in «%s» not available (%s): %s", backup, type(e).__name__, e)
        return first
    return _with_failover([(primary, first), (backup, second)])


def _with_failover(pairs):
    from livekit.agents.tts import FallbackAdapter

    class _Adapter(FallbackAdapter):
        def prewarm(self) -> None:
            for t in self._tts_instances:
                pw = getattr(t, "prewarm", None)
                if callable(pw):
                    try:
                        pw()
                    except Exception:  # noqa: BLE001
                        pass

    names = [n for n, _ in pairs]
    adapter = _Adapter([t for _, t in pairs], max_retry_per_tts=1)

    def _changed(ev) -> None:
        try:
            i = [t for _, t in pairs].index(ev.tts)
        except ValueError:
            return
        if not ev.available and _ACTIVE["name"] == names[i]:
            nxt = next((names[j] for j, s in enumerate(adapter._status) if s.available), names[i])
            _ACTIVE["name"] = nxt
            _note(f"🔇 TTS «{names[i]}» failed — speaking with «{nxt}»", provider=names[i], stand_in=nxt)
        elif ev.available and i == 0:
            _ACTIVE["name"] = names[0]

    adapter.on("tts_availability_changed", _changed)
    return adapter


def available() -> list[str]:
    return registry.names()


from . import cartesia, elevenlabs, inworld, kokoro  # noqa: E402,F401

__all__ = ["build_tts", "available", "registry", "active_provider"]
