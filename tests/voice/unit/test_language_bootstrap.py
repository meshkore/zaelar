"""
Arranque IDIOMÁTICO del producto (2026-08-09). Dos invariantes que se rompieron por separado y que juntas
decidían si zaelar puede adaptarse al idioma de quien lo instala:

1. **El defecto es INGLÉS.** Una instalación limpia arrancaba con la UI en inglés (`store.lang()` cae a "en")
   y la VOZ en castellano (`langs.DEFAULT_LANG = "es"`) — incoherente, y contrario a la norma del operador.
2. **En primera ejecución el STT transcribe en AUTO.** La autodetección de `i18n.init.detect` clasifica la
   PRIMERA frase del operador; si el STT ya viene clavado a un idioma, esa frase llega transcrita por el modelo
   equivocado y no hay nada que clasificar. `whisper_local` lo hacía; los REMOTOS (deepgram/voxtral) NO — o sea
   que en el perfil de nube, el de producción, la autodetección no podía funcionar. Cada backend dice «auto» a
   su manera y por eso se comprueban los tres por separado: omitir el parámetro en Deepgram NO es auto (el
   servidor cae a en-US).
"""
from __future__ import annotations

import pytest

from voice.engine.core import langs


def test_product_default_language_is_english():
    assert langs.DEFAULT_LANG == "en"


def test_first_run_auto_follows_the_detector(monkeypatch):
    from i18n.init import detect

    monkeypatch.setattr(detect, "should_detect", lambda: True)
    assert langs.first_run_auto() is True
    monkeypatch.setattr(detect, "should_detect", lambda: False)
    assert langs.first_run_auto() is False


def test_first_run_auto_is_fail_closed(monkeypatch):
    """Si i18n revienta o no está, el STT se comporta como siempre (idioma fijo) — nunca al revés."""
    from i18n.init import detect

    def boom():
        raise RuntimeError("i18n no disponible")

    monkeypatch.setattr(detect, "should_detect", boom)
    assert langs.first_run_auto() is False


def _captured_stt_kwargs(monkeypatch, module, plugin_attr, plugin_mod):
    seen = {}

    class _Fake:
        def __init__(self, **kw):
            seen.update(kw)

    monkeypatch.setattr(plugin_mod, plugin_attr, _Fake)
    module.build()
    return seen


@pytest.mark.parametrize("detecting, expected", [(True, "multi"), (False, "es")])
def test_deepgram_asks_for_multi_only_while_detecting(monkeypatch, detecting, expected):
    from livekit.plugins import deepgram as _dg

    from voice.engine.speech.stt import deepgram as adapter

    monkeypatch.setattr(langs, "first_run_auto", lambda: detecting)
    monkeypatch.setattr(langs, "current_code", lambda: "es")
    kw = _captured_stt_kwargs(monkeypatch, adapter, "STT", _dg)
    assert kw["language"] == expected


@pytest.mark.parametrize("detecting", [True, False])
def test_voxtral_omits_language_only_while_detecting(monkeypatch, detecting):
    from livekit.plugins import mistralai as _mi

    from voice.engine.speech.stt import voxtral as adapter

    monkeypatch.setattr(langs, "first_run_auto", lambda: detecting)
    monkeypatch.setattr(langs, "current_code", lambda: "es")
    kw = _captured_stt_kwargs(monkeypatch, adapter, "STT", _mi)
    if detecting:
        assert "language" not in kw, "pasar un idioma en primera ejecución mata la autodetección"
    else:
        assert kw["language"] == "es"
