"""A «?» in his text never turns his order into a question: only the verdict reads whether he asked (V2-845).

Live 2026-11-03: he pasted a page («…Any material changes in your team, progress, or fundraising? …») and wrote «Add
an alarm in my calendar that day». The verdict leaned order/act, unsure; the old clause read the PAGE's «?» under a
sure «no action on screen», kept `agenda:add_meeting` unwritten, and the reply «I'll put it in your agenda» stood.

Disarm: restore the «?» clause in `question_keeps_unwritten` and the first test goes red.
"""
from __future__ import annotations

from nucleo.acts import card
from nucleo.turn import brief as tb, verdicts

PASTED = ('I have sent an application:\n"""\nAny material changes in your team, progress, or fundraising? '
          'Submit an update.\n"""\n\nAdd an alarm in my calendar that day to be sure I got an answer before.')


def _brief(monkeypatch, **sure):
    def read(brief, key, fallback="", **_k):
        return (sure[key], {"used": True}) if key in sure else (fallback, {"used": False})
    monkeypatch.setattr(verdicts, "read", read)
    monkeypatch.setattr(tb, "read", read)


def test_a_pasted_question_mark_does_not_keep_his_order_unwritten(monkeypatch):
    _brief(monkeypatch, **{tb.TARGET_KEY: "none"})
    assert not card.question_keeps_unwritten("agenda", "add_meeting", PASTED, {"x": 1})


def test_his_own_question_mark_is_not_the_reader_either(monkeypatch):
    _brief(monkeypatch, **{tb.TARGET_KEY: "none"})
    assert not card.question_keeps_unwritten("agenda", "add_meeting", "can you add the dentist on friday?", {"x": 1})


def test_a_sure_question_verdict_still_keeps_the_write_unrun(monkeypatch):
    _brief(monkeypatch, **{tb.TARGET_KEY: "none", tb.REQUEST_KEY: "question"})
    assert card.question_keeps_unwritten("agenda", "add_meeting", PASTED, {"x": 1})
