"""TTS family — streaming, interruptible text-to-speech (remote or local)."""
from __future__ import annotations

from ...core.config import SETTINGS
from ...core.registry import Registry

registry = Registry("TTS")


def build_tts():
    return registry.create(SETTINGS.tts_provider)


def available() -> list[str]:
    return registry.names()


from . import cartesia, elevenlabs, kokoro  # noqa: E402,F401

__all__ = ["build_tts", "available", "registry"]
