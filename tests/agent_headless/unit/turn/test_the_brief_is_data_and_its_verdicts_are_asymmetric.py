"""The brief's questions are DATA, and a verdict is read asymmetrically (refactor2710-07).

`nucleo/turn/brief.QUESTIONS` is the one list of what a turn asks; `build()` and `keys()` derive from it. A verdict may
license an act at `LICENCE`, may refuse what the model CALLED only at `VETO`, and between the two a disagreement is asked
(`consent.ASK_WHICH`) — «Para todo» read `keep` at 0.65 against the model's `stop_worker` is asked, never refused in
silence (the ficha's asymmetry case).

Disarm: make `against_the_model` return `veto` for any disagreement and the asymmetry test goes red.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.request import stop
from nucleo.turn import brief, verdicts


def _brief(**answers) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": [],
            "result": {k: {"choice": c, "confidence": p} for k, (c, p) in answers.items()}}


def test_every_question_is_a_declared_row_and_the_keys_derive_from_it():
    keys = brief.keys()
    assert len(keys) == len(set(keys)) == len(brief.QUESTIONS)
    for k in (brief.REQUEST_KEY, brief.ESCALATE_KEY, brief.TARGET_KEY, brief.CATALOG_KEY, stop.KEY):
        assert k in keys, k


def test_the_brief_asks_what_its_rows_say(monkeypatch):
    qs = brief.build("put some jazz on", open_ids=[], has_workers=False)
    assert brief.REQUEST_KEY in qs and brief.ESCALATE_KEY in qs
    assert stop.KEY not in qs, "the stop question is asked only while an errand runs"
    with_workers = brief.build("put some jazz on", open_ids=[], has_workers=True)
    assert stop.KEY in with_workers and with_workers[stop.KEY]["criteria"] == stop.CHOICES
    assert brief.build("", open_ids=[]) == {}


def test_a_question_that_cannot_be_built_never_costs_the_others(monkeypatch):
    def _boom(_ctx):
        raise RuntimeError("x")
    monkeypatch.setattr(brief, "QUESTIONS", ((brief.CANVAS_KEY, None, _boom),) + brief.QUESTIONS[1:])
    qs = brief.build("put some jazz on", open_ids=[])
    assert brief.CANVAS_KEY not in qs and brief.REQUEST_KEY in qs


@pytest.mark.parametrize("answer,expected", [
    (("keep", 0.65), "ask_which"),     # the ficha's case: «Para todo», keep 0.65 → asked, never refused silently
    (("keep", 0.9), "veto"),           # a sure verdict refuses what the model called
    (("stop", 0.6), "run"),            # the verdict agrees
    (("keep", 0.3), "run"),            # a shrug is no verdict: the model's call runs
])
def test_the_asymmetric_read(answer, expected):
    assert verdicts.against_the_model(_brief(**{stop.KEY: answer}), stop.KEY, stop.ends) == expected


def test_the_stop_gate_reads_it_and_keeps_the_grammar_only_without_a_verdict():
    assert stop.model_stop(_brief(**{stop.KEY: ("keep", 0.65)}), grammar=False) == "ask_which"
    assert stop.model_stop(_brief(**{stop.KEY: ("stop", 0.95)}), grammar=False) == "run"
    assert stop.model_stop(None, grammar=False) == "veto", "no verdict and no order in his words: context bleed"
    assert stop.model_stop(None, grammar=True) == "run"


def test_a_licence_is_read_at_the_licence_floor():
    choice, info = verdicts.read(_brief(**{brief.REQUEST_KEY: ("order", 0.55)}), brief.REQUEST_KEY, "")
    assert choice == "order" and info["used"]
    choice, info = verdicts.read(_brief(**{brief.REQUEST_KEY: ("order", 0.45)}), brief.REQUEST_KEY, "")
    assert choice == "" and not info["used"]
    assert brief.read is not verdicts.read and brief.read(_brief(**{brief.REQUEST_KEY: ("order", 0.55)}),
                                                          brief.REQUEST_KEY, "")[0] == "order"
