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
