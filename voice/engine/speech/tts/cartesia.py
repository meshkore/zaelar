"""Cartesia Sonic TTS — remote streaming. AgentSession auto-cancels on barge-in."""
from __future__ import annotations

from livekit.plugins import cartesia as _cartesia

from ...core import langs
from ...core.config import SETTINGS
from ..voices import selected_voice
from . import registry


@registry.register("cartesia")
def build():
    # Cartesia Sonic voices are multilingual; the language param (LIVE active language)
    # aligns the SAME voice to the current language — a switch applies on reconnect.
    kwargs = dict(
        model=SETTINGS.tts_model,
        api_key=SETTINGS.cartesia_api_key or None,
        language=langs.current_code(),
    )
    # Voice priority: the operator's ⚙-picked Cartesia voice > CARTESIA_VOICE_ID env > plugin default.
    voice = selected_voice("cartesia") or SETTINGS.tts_voice_id
    if voice:
        kwargs["voice"] = voice
    return _cartesia.TTS(**kwargs)
