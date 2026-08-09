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
        # PRIMERA EJECUCIÓN → `"multi"` (nova-3 multilingüe, con code-switching): sin idioma elegido todavía no
        # podemos clavar uno, o la autodetección de `i18n.init.detect` recibiría la frase del operador transcrita
        # a través del modelo equivocado y no habría nada que clasificar. OJO: aquí no vale omitir el parámetro
        # —el servidor de Deepgram cae a en-US, que no es auto—; hay que pedir "multi" explícitamente.
        # Con idioma ya elegido, el de siempre: LIVE, y el cambio aplica al reconectar.
        language="multi" if langs.first_run_auto() else langs.current_code(),
        interim_results=True,
    )
