"""V2-666 · a pending notice WAITS its turn — the operator's words open the turn, the system notes follow.

Measured live, session 53de97d4, 10:58:33: «Johnny, ¿a qué hora tengo la cita con Hacienda?» reached the model
behind three `[SISTEMA]` notes about a dead Bitcoin task, two of them ordering «Díselo en ESTE turno», and the
reply opened «Primero, Ricardo, te debo una cosa pendiente: el gráfico de Bitcoin…». His question came last.

The operator's rule is the inverse: the order is served first; the news waits until the order is answered.
A model reads what comes first as the frame of its answer, so the frame has to be his.
"""
from __future__ import annotations

import re
from pathlib import Path

from voice import brain_notes

_Q = "Johnny, ¿a qué hora tengo la cita con Hacienda?"
_NOTES = ["[SISTEMA] Brain worker · Tarea sin completar: No pude crear el widget.",
          "[SISTEMA] La tarea de fondo «Genera un widget…» ha MUERTO sin resultado."]


def _code(rel: str) -> str:
    src = Path(rel).read_text(encoding="utf-8")
    return re.sub(r"(?m)^\s*#.*$", "", src)


def test_his_words_open_the_turn_and_the_notes_follow():
    out = brain_notes.compose_turn(_Q, _NOTES)
    assert out.startswith(_Q), "the operator's words must be the first thing the model reads"
    for n in _NOTES:
        assert n in out and out.index(n) > out.index(_Q)


def test_the_notes_ride_under_a_header_that_says_when_they_may_be_spoken():
    out = brain_notes.compose_turn(_Q, _NOTES)
    head = out[len(_Q):out.index(_NOTES[0])]
    assert "cuando hayas atendido" in head.lower() and "después" in head.lower()
    assert "nunca abras con ello" in head.lower()


def test_no_notes_means_his_words_untouched():
    assert brain_notes.compose_turn(_Q, []) == _Q
    assert brain_notes.compose_turn(_Q, ["", "  "]) == _Q


def test_notes_with_no_operator_words_still_reach_the_model():
    """A proactive turn with nothing from him (a delivery, a dead task) must not lose its notes."""
    out = brain_notes.compose_turn("", _NOTES)
    assert all(n in out for n in _NOTES)


def test_the_voice_provider_composes_through_the_one_seam():
    code = _code("voice/engine/llm/providers/nucleo.py")
    assert "brain_notes.compose_turn(text, notes)" in code
    assert '"\\n".join(notes) + "\\n\\n" + text' not in code, "the old glue-in-front is gone"


def test_no_writer_orders_the_note_to_open_the_turn():
    """The two writers whose text said «Díselo en ESTE turno» now defer to his request. A note's own wording must
    not undo the order the composition establishes."""
    for rel in ("voice/proactive.py", "nucleo/workers/ended.py"):
        code = _code(rel)
        assert "Díselo en ESTE turno con tus palabras — todavía" not in code, rel
        assert "Díselo EN ESTE TURNO con tus" not in code, rel
        assert "DESPUÉS de contestar" in code, rel
