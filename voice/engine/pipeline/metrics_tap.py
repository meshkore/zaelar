"""metrics_tap.py — what a `metrics_collected` event becomes: an observer line + Energy usage reports.

Extracted from `agent.py`'s handler byte-for-byte (2026-09-10, paying the newborn-size ratchet; the CALLER
stays the session's `metrics_collected` event). Everything here is the 2026-07-12 anti-flood rule plus the
remote STT/TTS forwarding — see the inline comments, which moved with the code.
"""
from __future__ import annotations

from ..core.config import SETTINGS
from ..core.logging import logger  # noqa: F401  (kept for parity with agent.py's imports)


def metric_line(m) -> str:
    parts = []
    for attr, label in (("ttft", "ttft"), ("duration", "dur"), ("ttfb", "ttfb"),
                        ("end_of_utterance_delay", "eou"), ("audio_duration", "audio")):
        v = getattr(m, attr, None)
        if isinstance(v, (int, float)) and v > 0:
            parts.append(f"{label}={v:.2f}s")
    return f"{type(m).__name__}: " + " ".join(parts) if parts else type(m).__name__


def on_metrics(ev, emit) -> None:
    # ANTI-FLOOD (2026-07-12): metrics WITHOUT real latencies (especially VADMetrics, ~2/s continuously —
    # more with background noise) are NOT logged: they provide no useful data and each event caused 2
    # SYNCHRONOUS file writes in the voice thread + flooded SSE. `metric_line` adds "=" only when there are
    # numbers (ttft/dur/ttfb/eou/audio) → without "=", it is a bare name and is discarded.
    line = metric_line(ev.metrics)
    if "=" in line:
        emit("metric", line, role="system")
    # Forward REMOTE STT/TTS latency into the observer stream too — Cartesia/Deepgram/Voxtral run entirely
    # inside their LiveKit plugin (no zaelar call site to instrument directly), so LiveKit's own per-provider
    # metric is the only place this ever surfaces. Local backends (Kokoro/whisper_local) already emit their
    # own tts_ms/stt_ms at the exact call site (more precise: text/backend attached) — skip here to avoid a
    # duplicate row for the same utterance.
    m = ev.metrics
    kind = type(m).__name__
    if kind == "TTSMetrics" and SETTINGS.tts_provider != "kokoro_local":
        dur = getattr(m, "duration", None)
        if dur:
            # SAFE to label with active() (source audit 2026-08-16): a TTS metric describes audio synthesized
            # for text the turn ALREADY generated — its trace exists. Unlike STTMetrics (below, untouched):
            # that describes recognition of what the operator is saying NOW, which almost always precedes the
            # trace of the turn it will trigger.
            from voice import trace as _trace
            _tid = _trace.active()
            emit("tts", f"🔊 {SETTINGS.tts_provider}", extra={"tts_ms": round(dur * 1000),
                 **({"trace": _tid} if _tid else {})})
        from nucleo import energy_meter as _energy
        # The PROVIDER is passed, not looked up inside the meter: the rate has to follow whatever
        # backend actually produced this audio, and this hook is the only place that knows it.
        _energy.report_tts_usage(characters=getattr(m, "characters_count", None),
                                 provider=SETTINGS.tts_provider)
    elif kind == "STTMetrics" and SETTINGS.stt_provider != "whisper_local":
        dur = getattr(m, "duration", None)
        if dur:
            emit("stt", f"👂 {SETTINGS.stt_provider}", extra={"stt_ms": round(dur * 1000)})
        from nucleo import energy_meter as _energy
        _energy.report_stt_usage(audio_seconds=getattr(m, "audio_duration", None),
                                 provider=SETTINGS.stt_provider)
