"""One canvas door: every show and close crosses `nucleo.acts.canvas.apply`, judged by the ARMED arbiter (refactor2710-04 T-02).

A vetoed act never reaches the canvas and the door says so — its caller does not record it as done. An allowed act is
the `widget` event the canvas obeys, with its provenance, and its verdict is on the stream armed (`shadow: false`,
with `verdict` and `source`). Ops the arbiter does not license (minimize, fullscreen, move) cross the same door as they
are. The sheet of an errand the turn reopened belongs to that errand (`recall:<card>`), not to the model's words.
"""
from __future__ import annotations

import pytest

from nucleo import canvas_arbiter as arb
from nucleo.acts import canvas

NOTHING = {"text": "mm, vale", "turn_credit": True, "last_reply": "", "verdict": {}}


@pytest.fixture
def stream(monkeypatch):
    import voice.observer as obs
    out = []
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None:
                        out.append((kind, label, dict(extra or {}))))
    return out


def _sink(out):
    return lambda kind, label, extra=None, **k: out.append((kind, label, dict(extra or {})))


def test_a_vetoed_show_never_reaches_the_canvas_and_the_door_says_so(stream):
    widget = []
    assert canvas.apply("show", "agenda", src="flash", request=NOTHING, emit=_sink(widget)) is False
    assert widget == [], "a veto must not put the card on screen"
    v = [e for e in stream if e[0] == "arbiter"][-1]
    assert v[2]["allow"] is False and v[2]["shadow"] is False and v[2]["source"] == "flash"


def test_an_ordered_close_reaches_the_canvas_with_its_provenance(stream):
    widget = []
    req = {**NOTHING, "verdict": {"canvas": ("close", 0.9)}}
    assert canvas.apply("close", "musica", src="flash", request=req, emit=_sink(widget)) is True
    assert widget == [("widget", "close", {"id": "musica", "src": "flash"})]
    v = [e for e in stream if e[0] == "arbiter"][-1]
    assert v[1] == "✅ permitida · verdict-close" and v[2]["verdict"] == {"canvas": {"choice": "close", "confidence": 0.9}}


def test_a_close_of_everything_has_no_id_and_ops_the_tree_does_not_license_pass_as_they_are(stream):
    widget = []
    assert canvas.apply("close", "", src="flash", request={**NOTHING, "verdict": {"canvas": ("close", 0.9)}},
                        emit=_sink(widget)) is True
    assert widget[-1] == ("widget", "close", {"src": "flash"}), "a close with no id is the canvas's close-all"
    assert canvas.apply("minimize", "agenda", src="flash", request=NOTHING, emit=_sink(widget)) is True
    assert widget[-1][1] == "minimize"


def test_the_sheet_of_a_reopened_errand_is_that_errands(stream):
    widget = []
    assert canvas.apply("show", "results::g", src="recall:results::g", request=NOTHING, emit=_sink(widget)) is True
    assert widget[-1][2]["src"] == "recall:results::g"


def test_the_door_does_not_judge_twice(stream):
    """The shadow tap hears the event the door emits; it must not file a second verdict for it."""
    canvas.apply("close", "musica", src="flash", request={**NOTHING, "verdict": {"canvas": ("close", 0.9)}})
    assert len([e for e in stream if e[0] == "arbiter"]) == 1


def test_disarm_a_door_that_skips_the_arbiter_lets_the_unlicensed_show_through(monkeypatch, stream):
    monkeypatch.setattr(canvas, "JUDGED", ())
    widget = []
    assert canvas.apply("show", "agenda", src="flash", request=NOTHING, emit=_sink(widget)) is True
    assert widget, "the disarm did not land"


def test_a_broken_arbiter_fails_open_with_its_verdict_on_record(monkeypatch, stream):
    monkeypatch.setattr(arb, "_decide", lambda *a, **k: 1 / 0)
    widget = []
    assert canvas.apply("show", "agenda", src="flash", request=NOTHING, emit=_sink(widget)) is True
    assert [e for e in stream if e[0] == "arbiter"][-1][2]["rule"] == "arbiter-error"
