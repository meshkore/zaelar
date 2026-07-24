"""VAD family — voice activity detection."""
from __future__ import annotations

from ...core.config import SETTINGS
from ...core.registry import Registry

registry = Registry("VAD")


def build_vad():
    return registry.create(SETTINGS.vad_provider)


from . import silero  # noqa: E402,F401

__all__ = ["build_vad", "registry"]
