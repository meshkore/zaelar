"""A `[SISTEMA]` note glued to the turn never makes his order read as a «meta question».

Measured 2026-09-27 (verification after the demo pass): «Show me the monitors.» arrived with two system notes
behind it («Has abierto una gestión nueva… doy por terminada la anterior…»). The meta-question guard read the
COMPOSED turn, took the note for «why did you open X?», and dropped the show (`🚫 show ignorado (pregunta META…)`):
the reply was «Sorry, I lost that». The same rule as V2-678 — a decider reads his half, never our notes.
"""
from tests import voice_turn_source as _vts
from pathlib import Path

from voice import brain_notes
from voice.engine.llm.providers.nucleo import _norm_nfkd
from voice.engine.llm.providers.widget_intent import _is_meta_widget_question

SRC = Path(__file__).resolve().parents[4] / "voice" / "engine" / "llm" / "providers" / "nucleo.py"

TURN = brain_notes.compose_turn("Show me the monitors.", [
    "[SISTEMA] Has abierto una gestión nueva con la misma persona, así que doy por terminada la anterior: "
    "«confirm with Rowan that tomorrow catch-up works for him»"])


def test_his_half_is_not_a_meta_question():
    assert _is_meta_widget_question(_norm_nfkd(TURN)), "the premise: read whole, the note trips the guard"
    assert not _is_meta_widget_question(_norm_nfkd(brain_notes.operator_half(TURN)))


def test_both_call_sites_read_his_half():
    src = _vts.read(SRC)
    assert "_is_meta_widget_question(_norm_nfkd(_bnotes.operator_half(text)))" in src
    assert "_widget_fallback(_bnotes.operator_half(text)," in src
