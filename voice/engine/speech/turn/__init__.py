"""Turn-detection family — intelligent end-of-turn (not silence-only)."""
from __future__ import annotations

from ...core.config import SETTINGS
from ...core.registry import Registry

registry = Registry("TURN")


def build_turn_detection():
    provider = SETTINGS.turn_provider
    if provider in ("", "disabled", "none"):
        return None
    return registry.create(provider)


from . import livekit  # noqa: E402,F401
from . import semantic  # noqa: E402,F401  (V2-095: end of turn by MEANING, not only by silence)

__all__ = ["build_turn_detection", "registry"]
