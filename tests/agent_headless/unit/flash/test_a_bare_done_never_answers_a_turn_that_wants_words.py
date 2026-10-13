"""A mute data-op under a turn that WANTS WORDS is not answered with a bare «Done.» (node 2.604).

best-plumber-same-day EN (2026-10-14, turn 10): «hey, I need to know if any of them are top-rated and can actually
come today — that's the whole point, not just names and numbers». No question mark, so `widget_data_turn` took it
for an order and the text channel said «Done.» over a repaired op («wait, "Done"? I still don't know…»). The brief
read `wants_words=tell` at 1.00: the question shape a missing «?» hides is in the verdict, and the ack reads it —
it tells what the card holds (`named_ack`) or composes from the op's answer (`answer_in_words`).
"""
from __future__ import annotations

import threading

import pytest

from nucleo.flash import delivery_repeat, widget_data_turn as WDT

HEARD = ("hey, I need to know if any of them are top-rated and can actually come today — that's the whole point, "
         "not just names and numbers")
_OK = {"executed": "widget_data", "widget": "results", "act": "progress", "ops": [{"widget": "results", "act": "progress"}]}


def _brief(words: str) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": [], "_call_id": "t",
            "result": {"wants_words": {"choice": words, "confidence": 1.0}}}


@pytest.fixture(autouse=True)
def _labels(monkeypatch):
    from widgets import refs
    monkeypatch.setattr(refs, "_ref_index", lambda wid: (
        [{"id": "1", "label": "Ace Plumbing & Rooter, Inc. — +1 415-824-6444"},
         {"id": "2", "label": "Mr. Rooter Plumbing of San Francisco — +1 415-906-2456"}] if wid == "results" else []))


def test_the_measured_turn_gets_what_the_sheet_holds_not_done():
    out = WDT.named_ack(_OK, "Done.", HEARD, asked=delivery_repeat.wants_words(_brief("tell")))
    assert "Ace Plumbing" in out and out != "Done.", out


def test_without_the_verdict_a_sentence_with_no_question_mark_keeps_the_plain_ack():
    assert WDT.named_ack(_OK, "Done.", HEARD, asked=delivery_repeat.wants_words(_brief("act"))) == "Done."
    assert WDT.named_ack(_OK, "Done.", HEARD, asked=delivery_repeat.wants_words(None)) == "Done."


def test_the_probe_reads_the_brief_for_both_acks():
    import inspect
    from nucleo.flash import probe_after
    src = inspect.getsource(probe_after.the_words_it_owes)
    assert "answer_in_words(return_extra_exec, text, spec, asked=_asked)" in src
    assert "named_ack(return_extra_exec, _lg.data_ack, text, asked=_asked)" in src
    assert "_ww(brief)" in src
