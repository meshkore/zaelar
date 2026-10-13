"""His words reach a worker's door from either channel, and a system note is never his words.

A worker acts minutes after the turn and only carries the brief the model wrote («Buscar y CONTACTAR…» for a
turn that only asked to find, best-plumber-same-day ES). `nucleo/his_words` keeps what HE said, fed by
`dialog.push_user` — the one function the voice provider and the text probe both call for his turn.

A note glued in front of a turn can quote a worker («el proceso pregunta: ¿escribo a Fontanero X?»); taken as
his words it would name the very recipient it asks about, and the question would answer itself.
"""
import time
from pathlib import Path

import pytest

from nucleo import his_words
from nucleo.flash import dialog

ENGINE = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _clean():
    his_words.reset()
    yield
    his_words.reset()


def test_a_turn_pushed_into_the_window_is_recorded_with_its_time():
    t0 = time.time()
    dialog.push_user([], "necesito un fontanero hoy")
    assert his_words.since(t0 - 1) == ["necesito un fontanero hoy"]
    assert his_words.since(time.time() + 60) == []


def test_a_note_is_not_his_words():
    dialog.push_user([], "[SISTEMA] Aviso para el operador: el proceso pregunta: ¿escribo a Fontanero Urgencia "
                         "Madrid?\nvale, sí")
    said = his_words.since(0)
    assert all("Fontanero Urgencia" not in s for s in said), said


def test_a_turn_that_is_only_notes_records_nothing():
    dialog.push_user([], "[SISTEMA] Brain worker · Tarea completada: escribí a Fontaurgencias 24h")
    assert his_words.since(0) == []


@pytest.mark.parametrize("path", ["nucleo/flash/probe.py", "voice/engine/llm/providers/turn_after.py"])
def test_both_channels_record_his_turn_through_the_one_function(path):
    assert "push_user(" in (ENGINE / path).read_text(encoding="utf-8"), f"{path} no longer records his turn"
