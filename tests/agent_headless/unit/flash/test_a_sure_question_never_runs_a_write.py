"""A declared WRITE marks his real app, so it needs an ORDER: a turn the brief surely reads as a question never runs one
(node 2.908).

show-my-messages EN (2026-10-28): «show my messages» ran `mensajeria:unread`, a write that marks a message unread in his
real app, and no card came up. The old clause read his «?», which a voice turn rarely carries; the verdict is the reader.

Disarm: with `_asks_without_ordering` answering False, the first test goes red.
"""
from __future__ import annotations

import pytest

from nucleo.acts import card
from nucleo.turn import brief as tb, verdicts


def _brief(monkeypatch, **sure):
    """`sure` = {key: choice} the brief read surely; `target` = the screen_action verdict."""
    def read(brief, key, fallback="", **_k):
        return (sure[key], {"used": True}) if key in sure else (fallback, None)
    monkeypatch.setattr(verdicts, "read", read)
    monkeypatch.setattr(tb, "read", read)


@pytest.mark.parametrize("said", ["show my messages", "enséñame mis mensajes", "what's new in my inbox"])
def test_a_sure_question_does_not_mark_his_app(monkeypatch, said):
    _brief(monkeypatch, **{tb.REQUEST_KEY: "question"})
    assert card.question_keeps_unwritten("mensajeria", "unread", said, {"x": 1})
    _brief(monkeypatch, **{tb.WORDS_KEY: "tell"})
    assert card.question_keeps_unwritten("agenda", "add_meeting", said, {"x": 1})


def test_an_order_still_writes_and_a_lens_still_runs(monkeypatch):
    _brief(monkeypatch, **{tb.REQUEST_KEY: "order", tb.WORDS_KEY: "tell"})
    assert not card.question_keeps_unwritten("agenda", "add_meeting", "add the dentist and tell me when", {"x": 1})
    _brief(monkeypatch, **{tb.REQUEST_KEY: "question"})
    assert not card.question_keeps_unwritten("mensajeria", "show_view", "show my messages", {"x": 1})


def test_a_verdict_naming_this_write_runs_it_and_no_verdict_changes_nothing(monkeypatch):
    _brief(monkeypatch, **{tb.REQUEST_KEY: "question", tb.TARGET_KEY: "mensajeria:unread"})
    assert not card.question_keeps_unwritten("mensajeria", "unread", "mark it unread?", {"x": 1})
    _brief(monkeypatch)
    assert not card.question_keeps_unwritten("mensajeria", "unread", "show my messages", {"x": 1})
