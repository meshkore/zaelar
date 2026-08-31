"""Silero VAD (bundled ONNX, no runtime download). Local in both profiles."""
from __future__ import annotations

import os

from livekit.plugins import silero as _silero

from . import registry


@registry.register("silero")
def build():
    # Two levers, both env-overridable, in tension (anti-clipping vs. anti-noise):
    #   · prefix_padding_duration — how much audio BEFORE the detected onset is prepended to the turn. 0.8s recovers the
    #     first word during a fast start (fix for "you eat the first word"). It is KEPT at 0.8 → even if
    #     we raise the threshold, the onset is not lost because the padding already captures it.
    #   · activation_threshold — VOICE probability (Silero, 0-1) required to start capturing. 2026-07-12: 0.4→0.5
    #     (background-noise robustness requested by the operator): at 0.4, "almost-voice" noise triggered a turn; 0.5 requires
    #     something more clearly human. DO NOT raise it further (0.55+ started eating soft onsets despite the padding). The
    #     MAIN filter for DISTANT noise is the RMS energy gate (`stt_rms_gate`=0.02): this complements it.
    return _silero.VAD.load(
        prefix_padding_duration=float(os.getenv("ZAELAR_VAD_PREFIX_PAD", "0.8")),
        activation_threshold=float(os.getenv("ZAELAR_VAD_ACTIVATION", "0.5")),
    )
