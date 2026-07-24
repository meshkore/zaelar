"""Deepgram nova-3 STT — remote streaming (alternative to Voxtral)."""
from __future__ import annotations

from livekit.plugins import deepgram as _deepgram

from ...core import langs
from ...core.config import SETTINGS
from . import registry


@registry.register("deepgram")
def build(vad=None):
    return _deepgram.STT(
        model=SETTINGS.stt_model_deepgram,
        api_key=SETTINGS.deepgram_api_key or None,
        language=langs.current_code(),   # LIVE active language (switch applies on reconnect)
        interim_results=True,
    )
