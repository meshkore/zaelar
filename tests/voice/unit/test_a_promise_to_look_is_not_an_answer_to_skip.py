"""Demo pass 53 (2026-09-29), R3: «find me five days in her vacation where i'm free and tell me the dates» → the
model read the agenda and said «Okay… let me look at your calendar across that stretch.»; the read's second pass,
told «if what you already said answers it, reply SKIP», said nothing — the promise hung and the dates were never
given. The instruction now says that announcing a look is not an answer, and a SKIP leaves a line on the timeline
(it was silent, so the cause could not be confirmed from the run)."""
import pathlib

SRC = (pathlib.Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")


def test_a_look_announced_is_not_an_answer():
    i = SRC.index("responde exactamente SKIP y nada más.")
    assert "Anunciar que vas a mirar o que lo estás" in SRC[i:i + 200]


def test_a_skip_is_visible():
    assert "🤐 segundo pase: SKIP — lo ya dicho contestaba" in SRC
