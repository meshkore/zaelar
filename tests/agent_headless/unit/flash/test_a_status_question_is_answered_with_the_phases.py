"""A status question over live errands is answered with where each one is, never an empty wait (three-tasks, EN).

Measured on the EN twin (sandbox 20261010-145237-en, turn i=151). Three errands live — the report «elaborating
the report with all the documentation», the game «creando un widget…», the monitor — and the operator said «And the
monitor, no more than $150. How's everything going?». The model called `send_to_worker` twice and said nothing;
the text channel filled the silence with OUR holding line: «Alright, give me a moment to look into that.» An
empty wait, to a status question, while the turn's own state carried each errand's phase. The judge marked it:
«use the real progress the engine context already carries instead of generic placeholders».

When the turn verdict says he expects to be TOLD something (`wants_words=tell`, or a `question`), and the model
went mute over a worker call, the line is the live errands and their phase — the same data the prompt had. The voice
turn (and the typed channel, which runs it) calls `errands_of_a_turn.status_owed`.
"""
from __future__ import annotations

import asyncio
import pathlib
import threading
import types

import pytest

from nucleo.turn import errands_of_a_turn as E

ENGINE = pathlib.Path(__file__).resolve().parents[4]
SAID = "And the monitor, no more than $150. How's everything going?"


def _brief(**verdicts):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {k: {"choice": c, "confidence": 0.99, "probs": {c: 0.99}}
                                    for k, c in verdicts.items()}, "_call_id": "t", "turn_id": "t", "open_ids": []}


@pytest.fixture
def three_live(monkeypatch):
    from nucleo import dispatch
    live = [{"id": "1", "request": "Produce a report on electric cars for city driving", "phase":
             "Elaborating the report with all the documentation", "waiting_on": ""},
            {"id": "2", "request": "Build a Super Mario style platformer canvas game", "phase": "creando un widget…",
             "waiting_on": ""},
            {"id": "3", "request": "Find real marketplace listings for: cheap used monitor", "phase": "",
             "waiting_on": ""}]
    labels = {"1": "Electric cars for city driving report", "2": "Super Mario platformer game", "3": ""}
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: live)
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label=labels.get(str(tid), "")))
    return live


def test_a_status_question_gets_every_live_errand_and_its_phase(three_live):
    line = E.status_owed(SAID, _brief(wants_words="tell", request_type="question"))
    assert "Electric cars for city driving report" in line and "Elaborating the report" in line
    assert "Super Mario platformer game" in line
    # the engine's Spanish phase never reaches an English ear (round 20:00, the language gate flagged it)
    assert "creando un widget" not in line and "under way" in line
    assert "cheap used monitor" in line, "an errand with no phase yet is still named"


def test_an_order_that_asks_for_nothing_gets_no_status(three_live):
    assert E.status_owed("make it jump higher", _brief(wants_words="act", request_type="order")) == ""
    assert E.status_owed(SAID, None) == "", "no verdict, no status: the line is owed only when the turn asked"


def test_nothing_live_is_no_status(monkeypatch):
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [])
    assert E.status_owed(SAID, _brief(wants_words="tell")) == ""


def test_the_typed_turn_says_the_status_instead_of_the_holding_line(three_live):
    """Through the typed channel, which runs the voice turn: the model sends to the workers and says nothing."""
    from tests.brain import harness as H
    case = {"id": "status", "lang": "en", "phrase": SAID, "source": "test", "screen": {"open": []}, "expect": "talk",
            "brief": {"wants_words": ("tell", 0.99), "request_type": ("question", 0.99)},
            "model": {"tools": [{"name": "send_to_worker", "args": {"which": "the monitor", "message": SAID}},
                                {"name": "send_to_worker", "args": {"which": "all", "message": SAID}}]}}
    with H.Isolated("en") as iso:
        iso.seed(case)
        from nucleo.cli import turn
        try:
            res = asyncio.run(turn.run_turn(SAID, sid="status", ingest=False))
        finally:
            turn.reset("status")
    assert "Elaborating the report" in res["reply"], res
    assert "give me a moment" not in res["reply"].lower()


def test_the_voice_turn_asks_it():
    # the voice turn reaches `status_owed` through `split_by_errand.status_with_refined`, which adds the errands a
    # send reached (2.644)
    assert "_sbe.status_with_refined(" in (ENGINE / "nucleo/flash/post_stream_settle.py").read_text(encoding="utf-8")
    assert "_eot.status_owed(" in (ENGINE / "nucleo/turn/split_by_errand.py").read_text(encoding="utf-8")
