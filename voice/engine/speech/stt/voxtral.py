"""Voxtral Realtime STT (Mistral) — remote streaming. Needs a VAD to flush turns."""
from __future__ import annotations

from livekit.plugins import mistralai

from ...core import langs
from ...core.config import SETTINGS
from . import registry


@registry.register("voxtral")
def build(vad=None):
    kwargs = {}
    # PRIMERA EJECUCIÓN → OMITIR el idioma: para Voxtral el parámetro es "el idioma si YA se conoce", y sin él
    # transcribe en auto. Es lo que necesita la autodetección de `i18n.init.detect` para leer la primera frase
    # del operador tal cual la dijo (ver `langs.first_run_auto`). Con idioma elegido, el de siempre: LIVE, y el
    # cambio aplica al reconectar.
    if not langs.first_run_auto():
        kwargs["language"] = langs.current_code()
    return mistralai.STT(
        model=SETTINGS.stt_model_voxtral,
        api_key=SETTINGS.mistral_api_key or None,
        vad=vad,
        **kwargs,
    )
