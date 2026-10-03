"""Demo pass 53 (2026-09-29), R3: «find me five days in her vacation where i'm free and tell me the dates» → the
model read the agenda and said «Okay… let me look at your calendar across that stretch.»; the read's second pass,
told «if what you already said answers it, reply SKIP», said nothing — the promise hung and the dates were never
given. The instruction now says that announcing a look is not an answer, and a SKIP leaves a line on the timeline
(it was silent, so the cause could not be confirmed from the run)."""
from tests import voice_turn_source as _vts
import pathlib

SRC = _vts.read(pathlib.Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py")


def test_a_look_announced_is_not_an_answer():
    i = SRC.index("responde exactamente SKIP y nada más.")
    assert "Anunciar que vas a mirar o que lo estás" in SRC[i:i + 200]


def test_a_skip_is_visible():
    assert "🤐 segundo pase: SKIP — lo ya dicho contestaba" in SRC


def test_what_was_just_read_wins_over_what_was_said_before_reading():
    """Demo pass 84, Z1: «tomorrow's … calendar's clear — nothing booked» was said BEFORE the agenda was read; the
    read returned four meetings and the second pass, told «don't contradict it», answered SKIP. The words said before
    the read are corrected, never protected."""
    i = SRC.index("responde exactamente SKIP y nada más.")
    block = SRC[i - 500:i]
    assert "los datos mandan" in block and "corrígelo" in block
    assert "no lo repitas ni lo contradigas" not in SRC
