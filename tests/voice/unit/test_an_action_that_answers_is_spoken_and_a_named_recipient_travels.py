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


def test_find_free_is_declared_an_answer_and_the_turn_speaks_it():
    from widgets import effects as fx
    assert fx.carries("agenda", "find_free", fx.OUTPUT_ANSWER)
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    assert "_answers = any(_fx_ans.carries(_w, _a, _fx_ans.OUTPUT_ANSWER)" in src
    assert "if _answers or (_wi is not None" in src


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


def test_the_outward_act_gate_carries_the_named_recipient():
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    assert "_vpay.update(_direct_action.person_fill(wid, _vdis, _vpay, _bnotes.operator_half(text)))" in src
