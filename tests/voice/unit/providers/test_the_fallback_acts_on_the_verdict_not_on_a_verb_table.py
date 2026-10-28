"""The widget fallback acts on the turn's canvas VERDICT, never on a verb stem plus a catalogue noun (V2-807 T-07).

Measured: while he corrected a draft's signature — «put the .com website in too… this message doesn't look right» —
the messaging card opened by itself. The fallback matched the open stem «pon» and `identify` found the messaging
card through its nouns («firma», «mensaje»); the turn's own verdict was `canvas=neither` at 0.96 and nobody read it.

The class: a verb-stem table plus a catalogue-noun match is not an order. The fallback acts only on a SURE canvas
verdict; a show also needs a card his words NAME (never one found «by context»). Absent or unsure verdict → nothing.
"""
from __future__ import annotations

import threading

import pytest

from voice.engine.llm.providers import widget_intent as WI


def _brief(canvas, conf=0.96):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [], "result": {"canvas": {"choice": canvas, "confidence": conf}}}


def _collect():
    events: list[tuple] = []

    def emit(kind, action, text=None, role=None, extra=None):
        events.append((kind, action, dict(extra or {})))
    return events, emit


SIGNATURE_EDITS = [
    "Nombre completo está bien, y pon también la web de punto com",
    "¿Puedes poner los interlineados? No queda bien este mensaje con la firma",
    "Put the dot-com website in the signature of this message too",
    "署名にウェブサイトも入れて、このメッセージはよくない",
]


@pytest.mark.parametrize("said", SIGNATURE_EDITS)
def test_an_edit_inside_a_card_opens_nothing_when_the_verdict_says_neither(said, monkeypatch):
    monkeypatch.setattr(WI, "_identify_named", lambda text: "mensajeria")    # the noun DOES name a card
    events, emit = _collect()
    assert WI._widget_fallback(said, emit, brief=_brief("neither")) is False
    assert events == []


@pytest.mark.parametrize("brief", [None, _brief("show", conf=0.2)])
def test_no_sure_verdict_means_no_fallback(brief, monkeypatch):
    monkeypatch.setattr(WI, "_identify_named", lambda text: "mensajeria")
    events, emit = _collect()
    assert WI._widget_fallback("pon la mensajería", emit, brief=brief) is False
    assert events == []


def test_a_sure_show_with_a_named_card_still_opens_it(monkeypatch):
    monkeypatch.setattr(WI, "_identify_named", lambda text: "agenda")
    monkeypatch.setattr(WI._cvis, "is_open", lambda wid, known=None: False)
    events, emit = _collect()
    assert WI._widget_fallback("ábreme la agenda", emit, brief=_brief("show")) is True
    assert ("widget", "show") in [(k, a) for k, a, _x in events]


def test_a_sure_show_that_names_no_card_opens_nothing(monkeypatch):
    monkeypatch.setattr(WI, "_identify_named", lambda text: None)
    events, emit = _collect()
    assert WI._widget_fallback("ábrelo", emit, brief=_brief("show")) is False
    assert events == []


def test_the_turn_passes_its_brief_to_the_fallback():
    src = (WI.__file__.rsplit("/", 1)[0] + "/turn_after.py")
    assert "brief=_brief):" in open(src, encoding="utf-8").read().split("_p._widget_fallback(", 1)[1][:260]


def test_disarmed_a_fallback_that_ignores_the_verdict_opens_the_messages_again(monkeypatch):
    """RED proof: with the verdict read as «show» whatever it said — by the fallback AND by the canvas door, the two
    readers of it — the signature edit opens the messaging card, so the tests above measure the verdict reading."""
    from nucleo import canvas_arbiter
    monkeypatch.setattr(WI, "_identify_named", lambda text: "mensajeria")
    monkeypatch.setattr(WI._cvis, "is_open", lambda wid, known=None: False)
    monkeypatch.setattr(WI, "_canvas_order", lambda brief: "show")
    monkeypatch.setattr(canvas_arbiter, "request_of", lambda brief=None, text=None, **k: {
        "text": "", "turn_credit": True, "last_reply": "", "verdict": {"canvas": ("show", 0.9)}})
    events, emit = _collect()
    WI._widget_fallback(SIGNATURE_EDITS[0], emit, brief=_brief("neither"))
    assert events, "the disarm did not land"
    monkeypatch.undo()
    monkeypatch.setattr(WI, "_identify_named", lambda text: "mensajeria")
    events, emit = _collect()
    assert WI._widget_fallback(SIGNATURE_EDITS[0], emit, brief=_brief("neither")) is False   # green again
    assert events == []
