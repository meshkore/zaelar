"""Two gaps the demo pass of 2026-09-28 (full18) found in the same stretch.

C2: «find me a free 45 minutes tomorrow afternoon…» ran `agenda:find_free`, got the slots back and said NOTHING —
the verdict read the sentence as an order, and only a question's op had its data spoken. An action declared
`output.answer` exists to answer: its data is the reply whatever the verdict reads.

E3: «send the invoice to quinn…» — the model called `reply` (to the invoice's sender); the outward-act gate ran
the verdict's `forward` with the reply's payload, which has no recipient, and the forward was refused. The person
his sentence names, from the directory, fills an empty `contact`."""
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[3]


def test_find_free_is_declared_an_answer_and_the_turn_speaks_it(monkeypatch):
    from widgets import effects as fx
    assert fx.carries("agenda", "find_free", fx.OUTPUT_ANSWER)
    from tests.voice.unit.test_a_question_answered_by_a_view_gets_its_answer import _ops_answer_door
    slots = {"ok": True, "slots": ["15:00-15:45", "16:30-17:15"]}
    said = _ops_answer_door(monkeypatch, slots, "agenda", "find_free", kind="order")   # an ORDER, not a question
    assert said and "15:00-15:45" in said[0]["system"], "a declared answer is spoken whatever the verdict reads"
    real = fx.carries
    fx.carries = lambda w, a, eff: False if eff == fx.OUTPUT_ANSWER else real(w, a, eff)
    try:                                            # disarm: without the declaration the order stays silent
        assert _ops_answer_door(monkeypatch, slots, "agenda", "find_free", kind="order") == [], "disarm did not land"
    finally:
        fx.carries = real


@pytest.fixture
def directory(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Quinn", "email": "quinn@example.com"})
    cd.apply_action("add_contact", {"name": "Rowan", "email": "rowan@example.com"})


def test_the_one_person_he_names_fills_an_empty_recipient(directory):
    from nucleo.flash import direct_action as da
    words = "send the invoice to quinn, tell him to book it"
    assert da.person_fill("mensajeria", "forward", {"n": 6, "text": "hi"}, words) == {"contact": "Quinn"}
    assert da.person_fill("mensajeria", "forward", {"contact": "Rowan"}, words) == {}, "a recipient is never edited"
    assert da.person_fill("mensajeria", "forward", {}, "send it to quinn and rowan") == {}, "two named: ask"
    assert da.person_fill("agenda", "show_day", {}, words) == {}, "only an action that takes a contact"
