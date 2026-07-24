"""Silero VAD (bundled ONNX, no runtime download). Local in both profiles."""
from __future__ import annotations

import os

from livekit.plugins import silero as _silero

from . import registry


@registry.register("silero")
def build():
    # Dos palancas, ambas env-overridable, en tensión (anti-clip vs anti-ruido):
    #   · prefix_padding_duration — cuánto audio ANTES del onset detectado se antepone al turno. 0.8s recupera la
    #     primera palabra en un arranque rápido (fix del "te comes la primera palabra"). Se MANTIENE en 0.8 → aunque
    #     subamos el umbral, el onset no se pierde porque el padding ya lo captura.
    #   · activation_threshold — probabilidad de VOZ (Silero, 0-1) para empezar a capturar. 2026-07-12: 0.4→0.5
    #     (robustez al ruido de fondo pedida por el operador): con 0.4 un ruido "casi-voz" disparaba turno; 0.5 exige
    #     algo más claramente humano. NO subimos más (0.55+ empezaba a comerse onsets suaves pese al padding). El
    #     filtro PRINCIPAL de ruido LEJANO es el gate de energía RMS (`stt_rms_gate`=0.02): esto lo complementa.
    return _silero.VAD.load(
        prefix_padding_duration=float(os.getenv("ZAELAR_VAD_PREFIX_PAD", "0.8")),
        activation_threshold=float(os.getenv("ZAELAR_VAD_ACTIVATION", "0.5")),
    )
