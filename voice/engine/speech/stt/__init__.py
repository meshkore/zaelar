"""STT family — streaming speech-to-text (remote or local)."""
from __future__ import annotations

from ...core.config import SETTINGS
from ...core.registry import Registry

registry = Registry("STT")


def build_stt(vad=None):
    return registry.create(SETTINGS.stt_provider, vad=vad)


def available() -> list[str]:
    return registry.names()


from . import deepgram, voxtral, whisper_local  # noqa: E402,F401

__all__ = ["build_stt", "available", "registry"]
