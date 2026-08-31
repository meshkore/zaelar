"""
Product LANGUAGE bootstrap (2026-08-09). Two invariants that broke separately and together
determined whether zaelar could adapt to the installer's language:

1. **The default is ENGLISH.** A clean installation started with the UI in English (`store.lang()` falls back to "en")
   and the VOICE in Spanish (`langs.DEFAULT_LANG = "es"`) — inconsistent and contrary to the operator's norm.
2. **On the first run, STT transcribes in AUTO.** The autodetection in `i18n.init.detect` classifies the
   operator's FIRST phrase; if STT is already locked to a language, that phrase arrives transcribed by the
   wrong model and there is nothing to classify. `whisper_local` did this; the REMOTE backends (deepgram/voxtral) DID NOT — meaning
   autodetection could not work in the cloud profile, the production one. Each backend handles «auto» in
   its own way, which is why all three are checked separately: omitting the parameter in Deepgram is NOT auto (the
   server falls back to en-US).
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
    """If i18n crashes or is unavailable, STT behaves as usual (fixed language) — never the other way around."""
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
        assert "language" not in kw, "passing a language on the first run kills autodetection"
    else:
        assert kw["language"] == "es"


# 3. **Locking the language MOVES THE MEMORY TOO.** The third invariant, added 2026-08-14 after the operator
#    asked what a brand-new account actually starts from. `lock()` persisted the setting, built the UI bundle
#    and told the frontend to switch — and left `state.language` untouched. That field is what
#    `nucleo/mem_processor._render` reads to pick the language every pill is written in, so a French operator
#    got French speech, French STT and a French UI while their memory was distilled, forever, into the default.
#    The memory is deliberately MONOLINGUAL in the operator's language; that only holds if detection moves it.

def test_a_brand_new_account_starts_in_english(monkeypatch):
    """The fourth place the bootstrap contract lives — and the one that was out of step, saying "es".

    Asserts the BEHAVIOUR instead of the literal since 2026-08-20. `memory.state._DEFAULT["language"]` is now None
    ("not yet chosen", like `mission`/`operator_name` beside it) and the language is RESOLVED at read time from the
    active configuration, because a frozen literal there was a PIN: the only writer of the field is `lock()` below,
    on the DETECTION path, and detection is skipped precisely when the operator already HAS a language configured
    (`should_detect` returns False once `settings.stt_language` is set). Measured in every use_cases sandbox:
    `ZAELAR_LANGUAGE=es`, Spanish conversation for 27 turns, every pill distilled into English.

    With nothing configured the answer this test was written to protect is unchanged: English."""
    from memory import state as mstate
    assert mstate._DEFAULT["language"] is None, "a literal here would once again be a PIN that nothing moves"
    monkeypatch.delenv("ZAELAR_LANGUAGE", raising=False)
    monkeypatch.setattr(langs, "_default_code", lambda: "en")
    assert mstate._active_language() == langs.DEFAULT_LANG == "en"


def test_locking_the_language_also_moves_the_memory(monkeypatch):
    import asyncio
    from i18n.init import detect

    written = {}
    monkeypatch.setattr(detect, "_should_cache", None, raising=False)
    # Isolate the three side effects we are NOT testing here (settings file, bundle generation, SSE).
    import config.settings as cs
    monkeypatch.setattr(cs, "update", lambda d: None)
    import i18n.init as i18n_init

    async def _noop(code):
        return None

    monkeypatch.setattr(i18n_init, "prepare", _noop)
    from memory import api as memapi
    monkeypatch.setattr(memapi, "set_state", lambda fields: written.update(fields))

    res = asyncio.run(detect.lock("fr"))
    assert res["ok"] is True
    assert written.get("language") == "fr", (
        "detection moved the voice and the UI but not the memory: pills would keep being written in the "
        "previous language forever"
    )


def test_the_memory_language_is_never_hardcoded_to_spanish():
    """Both readers used to fall back to a literal "es" when the state had no language yet — which is exactly
    the state a cold first run is in. The fallback has to be the engine's single source of truth."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[3]
    for rel in ("nucleo/mem_processor.py", "nucleo/memllm.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert 'or "es"' not in src, f"{rel} still hardcodes Spanish as the fallback language"
