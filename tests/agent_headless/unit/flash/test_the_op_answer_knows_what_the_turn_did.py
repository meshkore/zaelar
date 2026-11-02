"""The pass that answers from what an op returned is told what the turn DID — and so stops narrating the rest (node 2.406).

V2-834 T17, use case `what-does-my-week-look-like__us` (sandbox, 2026-11-02): «yes please, delete it and add a clean
one with just the 9:30 start… then read it back» → the model called `agenda:cancel_meeting` only; the op-answer pass,
reading his words and the card after the delete, said «the Dentist appointment is deleted, and I've added a clean one»
— and the calendar had no dentist at all. The pass never knew which acts ran.

Measured offline with the exact pass (deepseek-flash, non-reasoning, 8 runs per language): the false «added» claim went
from 3/8 to 1/8 (EN) and 3/8 to 0/8 (ES) once the pass carries the line below. The label is language data.
"""
from __future__ import annotations

import pytest

from i18n import langs
from nucleo.flash import widget_read as w

SAID = {"en": "yes please, delete it and add a clean one with just the 9:30 start. then read it back to me",
        "es": "sí, bórrala y crea una limpia solo con el inicio a las 9:30. Luego léemela"}


@pytest.mark.parametrize("code", ["en", "es"])
def test_the_pass_carries_what_the_turn_did(code, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", code)
    label = langs.words("widget_read.did", code)
    assert label, f"{code}: no `widget_read.did` in the voice pack"
    got = w.op_answer_system("LOCK", SAID[code], "agenda", {"meetings": []}, [("agenda::x", "cancel_meeting")])
    assert f"{label}: agenda.cancel_meeting" in got, got


def test_no_ops_no_line():
    assert "agenda." not in w.op_answer_system("LOCK", SAID["en"], "agenda", {"meetings": []}, [])


class _Done:
    def __init__(self, res):
        self._r = res

    def done(self):
        return True

    def cancelled(self):
        return False

    def result(self):
        return self._r


def test_a_refused_op_is_not_what_the_turn_did(monkeypatch):
    """S1 audit H10: `data_done["ops"]` is filled when an op is LAUNCHED; one the widget then refused stayed in it, so the
    pass would narrate as done an act that was refused — the inverse of T17. The line is what LANDED."""
    from nucleo.flash import post_stream_acts as psa
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    ops = [("agenda", "cancel_meeting"), ("agenda", "add_meeting")]
    tasks = [("agenda", _Done({"ok": True})), ("agenda", _Done({"ok": False, "error": "slot_taken"}))]
    landed = psa._landed(ops, tasks)
    assert landed == [("agenda", "cancel_meeting")]
    got = w.op_answer_system("LOCK", SAID["en"], "agenda", {"meetings": []}, ops, landed=landed)
    assert "agenda.cancel_meeting" in got and "agenda.add_meeting" not in got, got
    assert psa._landed(ops, tasks[:1]) is None, "ops and tasks that do not line up: every op, as before"
