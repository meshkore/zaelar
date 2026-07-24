"""LiveKit local semantic turn detector (ONNX, CPU). Non-silence-only.

Deprecated-but-local ``MultilingualModel``; the ``inference.TurnDetector`` route
was rejected on purpose (needs LiveKit's hosted gateway, absent on a self-hosted
dev server). pipecat's smart-turn isn't runnable inside LiveKit.
"""
from __future__ import annotations

from . import registry


@registry.register("livekit")
def build():
    from livekit.plugins.turn_detector.multilingual import MultilingualModel

    return MultilingualModel()
