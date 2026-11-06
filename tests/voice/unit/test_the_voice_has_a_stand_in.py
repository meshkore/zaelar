"""V2-778 F0-7 — the table's TTS failover row is a mechanism, not a note.

`voice/engine/speech/tts/__init__.py` built exactly ONE provider: a missing `INWORLD_API_KEY` raised at prewarm and
a 402 from a provider out of credit left the voice mute until someone switched the panel by hand, while
`config/models.default.json` named ElevenLabs as the stand-in. Now:

  · the selected provider cannot be built (the plugin raises `ValueError` without a key) → the stand-in serves alone;
  · both build → LiveKit's `FallbackAdapter` switches to the stand-in when a synthesis fails for good;
  · `active_provider()` follows the switch, so the metering hook bills the backend that actually spoke.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from livekit.agents import tts as lk_tts
from livekit.agents.tts.fallback_adapter import AvailabilityChangedEvent

from voice.engine.speech import tts as T

ENGINE = Path(__file__).resolve().parents[3]


class _Fake(lk_tts.TTS):
    def __init__(self, name):
        super().__init__(capabilities=lk_tts.TTSCapabilities(streaming=False), sample_rate=24000, num_channels=1)
        self.name = name

    def synthesize(self, text, **kw):  # pragma: no cover — never called here
        raise NotImplementedError


def _no_key():
    raise ValueError("INWORLD_API_KEY is required")


@pytest.fixture
def table(monkeypatch):
    builders = dict(T.registry._builders)
    monkeypatch.setattr(T.registry, "_builders", builders)
    monkeypatch.setattr(T, "SETTINGS", dataclasses.replace(T.SETTINGS, tts_provider="inworld"))
    from config import models
    monkeypatch.setattr(models, "failover", lambda name: {"provider": "elevenlabs"} if name == "tts" else None)
    return builders


def test_a_missing_key_speaks_with_the_stand_in(table):
    table["inworld"] = _no_key
    table["elevenlabs"] = lambda: _Fake("elevenlabs")
    built = T.build_tts()
    assert isinstance(built, _Fake) and built.name == "elevenlabs"
    assert T.active_provider() == "elevenlabs", "the meter must bill the one that speaks"


def test_without_a_stand_in_the_error_is_still_the_titulars(table):
    table["inworld"] = _no_key

    def _also_no_key():
        raise ValueError("ELEVENLABS_API_KEY is required")
    table["elevenlabs"] = _also_no_key
    with pytest.raises(ValueError, match="INWORLD"):
        T.build_tts()


def test_both_built_fail_over_at_synthesis(table):
    a, b = _Fake("inworld"), _Fake("elevenlabs")
    table["inworld"] = lambda: a
    table["elevenlabs"] = lambda: b
    built = T.build_tts()
    assert isinstance(built, lk_tts.FallbackAdapter)
    assert T.active_provider() == "inworld"
    built._status[0].available = False
    built.emit("tts_availability_changed", AvailabilityChangedEvent(tts=a, available=False))
    assert T.active_provider() == "elevenlabs", "after the titular gave up (a 402), the stand-in is the one speaking"


def test_the_meter_reads_the_active_provider():
    src = (ENGINE / "voice" / "engine" / "pipeline" / "metrics_tap.py").read_text(encoding="utf-8")
    assert "provider=_tts.active_provider()" in src


_spec = __import__("importlib.util").util.find_spec


def test_a_local_voice_that_cannot_sound_here_is_never_offered_as_the_stand_in(table, monkeypatch):
    """No Metal, no Kokoro server, no kokoro-onnx (a cloud container): Kokoro refuses to build, so the titular serves
    alone instead of failing over to a stand-in that would stop the voice at its first sentence (2026-11-06)."""
    from voice.engine.speech.tts import kokoro
    monkeypatch.setattr(T, "_stand_in", lambda primary: "kokoro_local")
    monkeypatch.setattr(kokoro.accel, "has_metal", lambda: False)
    monkeypatch.delenv("ZAELAR_KOKORO_URL", raising=False)
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: None if name == "kokoro_onnx" else _spec(name, *a))
    table["inworld"] = lambda: _Fake("inworld")
    table["kokoro_local"] = kokoro.build
    built = T.build_tts()
    assert isinstance(built, _Fake) and built.name == "inworld" and T.active_provider() == "inworld"
