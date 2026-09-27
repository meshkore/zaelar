"""V2-774 — Inworld is the default cloud TTS, ElevenLabs the second, and every surface that names a TTS knows it.

A provider that is buildable but missing from one surface fails SILENTLY, never loudly: dropped from the ⚙
(`_ENGINE_TTS` filters unknown values out of settings.json), billed at the catch-all (no tariff row), or shown
as «ok» with no key (voice_api). So this pins each surface, plus the per-variant voices that were measured.
"""
from __future__ import annotations

import json
import os

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def test_the_table_names_inworld_first_and_elevenlabs_second():
    t = json.load(open(os.path.join(ENG, "config/models.default.json")))["services"]["tts"]
    assert t["titular"]["provider"] == "inworld"
    assert t["titular"]["key_env"] == "INWORLD_API_KEY"
    assert t["failover"]["provider"] == "elevenlabs"


def test_the_engine_can_build_it():
    from voice.engine.speech import tts
    assert "inworld" in tts.available()
    assert "elevenlabs" in tts.available()          # second, still selectable


def test_every_surface_knows_the_provider():
    from config import settings
    from nucleo import energy_tariffs
    from voice.engine.core import profile
    assert "inworld" in settings._ENGINE_TTS
    assert "inworld" in settings._TTS_LABELS
    assert energy_tariffs.DEFAULT_TTS_USD_PER_1K_CHARS["inworld"] > 0
    assert profile._DEFAULTS["remote"]["tts"] == "inworld"


def test_each_variant_speaks_with_its_measured_voice():
    from voice.engine.speech import voices as V
    assert V.default_voice_for("inworld", "es", "ES") == "Alvaro"
    assert V.default_voice_for("inworld", "es", "419") == "Salvador"
    assert V.default_voice_for("inworld", "en", "US") == "Reed"
    assert V.default_voice_for("inworld", "en", "GB") == "Freddie"
    assert V.default_voice_for("inworld", "en", "") == "Reed"     # no region → the language's first variant


def test_a_language_switch_realigns_the_voice():
    from voice.engine.speech import voices as V
    assert V.voice_is_aligned("inworld", "Alvaro", "es", "ES")
    assert not V.voice_is_aligned("inworld", "Alvaro", "en", "US")      # a Castilian voice never speaks English
    assert not V.voice_is_aligned("inworld", "Alvaro", "es", "419")     # nor Latin American Spanish
    assert not V.voice_is_aligned("inworld", "Reed", "en", "GB")


def test_the_picker_only_offers_native_voices():
    from voice.engine.speech import voices as V
    for lang in ("es", "en"):
        rows = V.voices_for("inworld", lang)
        assert rows and all(r["lang"] == lang and r["native"] for r in rows)
    assert V.voices_for("inworld", "sw") == []       # no table for it → the builder keeps the plugin default


def test_the_live_voice_swap_can_repoint_it():
    """`live_tts.apply_voice` asks the plugin's signature for `voice_id`/`voice`; Inworld's is `voice`."""
    import inspect
    from livekit.plugins import inworld
    params = inspect.signature(inworld.TTS.update_options).parameters
    assert "voice" in params and "language" in params


# ── V2-775 — Cartesia had ONE voice (a Castilian one) for every language ────────────────────────────────────


def test_cartesia_speaks_each_variant_with_a_native_voice():
    """The operator heard US English with a Spanish accent: Inworld was out of credits, the TTS fell to
    Cartesia, and Cartesia's only default was `CARTESIA_VOICE_ID` = Marcos (Castilian) for every language."""
    from voice.engine.speech import voices as V
    marcos = "13ff5deb-2591-42ad-a356-63a04e524411"
    assert V.default_voice_for("cartesia", "es", "ES") == marcos
    assert V.default_voice_for("cartesia", "es", "419") == "2fc4f1ec-bfd0-46f1-8e6d-d4279eaaf838"   # Mateo
    assert V.default_voice_for("cartesia", "en", "US") == "47c38ca4-5f35-497b-b1a3-415245fb35e1"    # Daniel
    assert V.default_voice_for("cartesia", "en", "GB") == "4bc3cb8c-adb9-4bb8-b5d5-cbbef950b991"    # George
    assert not V.voice_is_aligned("cartesia", marcos, "en", "US")      # a language switch realigns it


def test_the_cartesia_builder_asks_the_language_before_the_env():
    """The env id must be the LAST rung, below the variant's pin — it was the only one."""
    import inspect
    from voice.engine.speech.tts import cartesia
    src = inspect.getsource(cartesia.build)
    assert src.index("cartesia_default_voice") < src.index("SETTINGS.tts_voice_id")


def test_every_provider_has_a_native_voice_for_the_four_variants():
    from voice.engine.speech import voices as V
    for prov in ("inworld", "cartesia", "elevenlabs"):
        for lang, region in (("es", "ES"), ("es", "419"), ("en", "US"), ("en", "GB")):
            v = V.default_voice_for(prov, lang, region)
            assert v, (prov, lang, region)
            assert V.voice_is_aligned(prov, v, lang, region), (prov, lang, region, v)
