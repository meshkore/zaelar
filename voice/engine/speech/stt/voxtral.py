"""Voxtral Realtime STT (Mistral) — remote streaming. Needs a VAD to flush turns."""
from __future__ import annotations

from livekit.plugins import mistralai

from ...core import langs
from ...core.config import SETTINGS
from . import registry


@registry.register("voxtral")
def build(vad=None):
    return mistralai.STT(
        model=SETTINGS.stt_model_voxtral,
        api_key=SETTINGS.mistral_api_key or None,
        language=langs.current_code(),   # LIVE active language (switch applies on reconnect)
        vad=vad,
    )
