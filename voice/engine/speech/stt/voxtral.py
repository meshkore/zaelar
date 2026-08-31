"""Voxtral Realtime STT (Mistral) — remote streaming. Needs a VAD to flush turns."""
from __future__ import annotations

from livekit.plugins import mistralai

from ...core import langs
from ...core.config import SETTINGS
from . import registry


@registry.register("voxtral")
def build(vad=None):
    kwargs = {}
    # FIRST RUN → OMIT the language: for Voxtral, the parameter means "the language if it is ALREADY known",
    # and without it, transcription is automatic. This is what `i18n.init.detect`'s autodetection needs in order
    # to read the operator's first phrase exactly as spoken (see `langs.first_run_auto`). Once a language is
    # selected, use the usual one: LIVE, and the change takes effect upon reconnection.
    if not langs.first_run_auto():
        kwargs["language"] = langs.current_code()
    return mistralai.STT(
        model=SETTINGS.stt_model_voxtral,
        api_key=SETTINGS.mistral_api_key or None,
        vad=vad,
        **kwargs,
    )
