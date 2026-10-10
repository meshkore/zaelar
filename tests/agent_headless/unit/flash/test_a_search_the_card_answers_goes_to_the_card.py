"""A web search on a turn the card ANSWERS goes to the card, not to the web (demo pass 109, C2, 2026-10-05).

«find me a free 45 minutes tomorrow afternoon to talk with rowan, after my last meeting» — the verdict read
`agenda:find_free` at 1.00, and the model called `web_search`. The results were timer websites, the reply said
«those results were just time and timer tools… tell me when your last meeting finishes», and only afterwards a
repair ran the find_free nobody then heard. When the verdict SURELY names an action whose result IS the reply
(`output.answer`), the search is not run: the card's pass decides the call (or the read) instead, in both channels.
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def verdict(monkeypatch):
    from nucleo.flash import turn_brief as _tb
    state = {"target": ("agenda:find_free", 1.0)}

    def read(_brief, key, fallback, *, min_confidence=None):
        if key != _tb.TARGET_KEY:
            return fallback, None
        choice, conf = state["target"]
        if conf < (min_confidence or 0.0):
            return fallback, None
        return choice, {"confidence": conf, "used": True}
    monkeypatch.setattr(_tb, "read", read)
    return state


@pytest.fixture
def card_pass(monkeypatch):
    from nucleo.flash import act_repair
    seen = {}

    async def fake(operator_text, commission, widget_id, spec=None, **kw):
        seen.update(widget_id=widget_id, commission=commission, **kw)
        return {"kind": "call", "widget_id": widget_id, "action": kw.get("verdict_action") or "find_free",
                "payload": {"date": "2026-10-06", "duration_min": 45, "from": "afternoon", "after_last": True}}
    monkeypatch.setattr(act_repair, "call_or_read_for_commission", fake)
    return seen


def _run(**kw):
    from nucleo.flash import card_commission as cc
    return asyncio.run(cc.instead_of_a_search("free 45 minutes tomorrow afternoon after last meeting", brief=object(),
                                              operator_text="find me a free 45 minutes tomorrow afternoon", spec=None,
                                              **kw))


def test_a_sure_answering_action_takes_the_search(verdict, card_pass):
    got = _run()
    assert got and got["kind"] == "call" and (got["widget_id"], got["action"]) == ("agenda", "find_free"), got
    assert card_pass["verdict_action"] == "find_free"


def test_an_unsure_verdict_keeps_the_search(verdict, card_pass):
    verdict["target"] = ("agenda:find_free", 0.6)
    assert _run() is None and not card_pass


def test_an_action_that_does_not_answer_keeps_the_search(verdict, card_pass):
    verdict["target"] = ("agenda:add_meeting", 1.0)
    assert _run() is None and not card_pass


def test_both_channels_ask_before_they_search():
    """The voice asks in the words phase, which runs before the light lanes where the web search is made."""
    words = open("nucleo/flash/post_stream_words.py", encoding="utf-8").read()
    post = open("nucleo/flash/post_stream.py", encoding="utf-8").read()
    probe = open("nucleo/flash/probe_after.py", encoding="utf-8").read()
    assert "voice_instead_of_a_search(" in words and "instead_of_a_search(" in probe
    assert post.index("hold_the_model_to_its_words(") < post.index("run_the_light_lanes("), \
        "the card is asked BEFORE the web"
    assert probe.index("instead_of_a_search(") < probe.index("_ws.search, _sq")
