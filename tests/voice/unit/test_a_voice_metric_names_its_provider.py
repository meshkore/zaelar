"""A voice metric names its provider as a FIELD, and so does a decision read (capture gaps, 2026-11-06).

The TTS row carried the provider only in its label («🔊 inworld») and the STT metric none at all — the lanes of the
operator console and the ◷ viewer read `provider`, never a label. Now `metrics_tap` stamps `provider` (and the audio length in
ms) on the `metric` rows of STT and TTS and on the per-phrase `stt`/`tts` rows; Jev's row carries `provider` too.

Disarm: drop `provider` from any of those `extra` dicts → red.
"""
from __future__ import annotations

import dataclasses
from types import SimpleNamespace

from voice.engine.pipeline import metrics_tap


class STTMetrics:
    def __init__(self):
        self.duration, self.audio_duration = 0.42, 5.0


class TTSMetrics:
    def __init__(self):
        self.duration, self.audio_duration, self.characters_count, self.speech_id = 0.31, 3.2, 40, "s1"


def _rows(monkeypatch, metrics):
    out: list[dict] = []
    monkeypatch.setattr(metrics_tap, "SETTINGS", dataclasses.replace(metrics_tap.SETTINGS, stt_provider="deepgram",
                                                                     tts_provider="inworld"))
    from nucleo.energy import meter
    monkeypatch.setattr(meter, "report_stt_usage", lambda **k: None)
    monkeypatch.setattr(meter, "report_tts_usage", lambda **k: None)
    from voice.engine.speech import tts as _tts
    monkeypatch.setattr(_tts, "active_provider", lambda: "inworld")
    metrics_tap.on_metrics(SimpleNamespace(metrics=metrics), lambda kind, label, text="", role="", extra=None:
                           out.append({"kind": kind, "label": label, **(extra or {})}))
    return out


def test_the_stt_metric_and_its_latency_row_name_the_provider(monkeypatch):
    rows = _rows(monkeypatch, STTMetrics())
    metric = next(r for r in rows if r["kind"] == "metric")
    assert metric["provider"] == "deepgram" and metric["audio_ms"] == 5000
    stt = next(r for r in rows if r["kind"] == "stt")
    assert stt["provider"] == "deepgram" and stt["stt_ms"] == 420


def test_the_tts_metric_and_its_latency_row_name_the_provider(monkeypatch):
    rows = _rows(monkeypatch, TTSMetrics())
    metric = next(r for r in rows if r["kind"] == "metric")
    assert metric["provider"] == "inworld" and metric["audio_ms"] == 3200
    tts = next(r for r in rows if r["kind"] == "tts")
    assert tts["provider"] == "inworld" and tts["tts_ms"] == 310


def test_a_decision_read_names_where_it_ran(monkeypatch):
    out: list[dict] = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None: out.append({"kind": kind, "label": label, **(extra or {})}))
    from nucleo import jev
    jev._emit("say hi", choice="smalltalk", confidence=0.9, probs={}, latency_ms=120, question_id="request-type")
    assert out and out[0]["provider"] == jev.PROVIDER == "typesafe"
