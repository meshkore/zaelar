"""Two acts asked, one done: the mouth says the rest is not done (V2-854 F4, I4).

Measured on his engine (2026-11-05): «mark Rakel as a favorite AND add her aliases» → one call (`set_favorite`),
the act landed, reply «Done.» — the aliases never came and nothing said so. The turn's brief reads how many acts his
words ask (`acts_asked`, any language); when it is sure he asked several and the doors ran exactly one, the mouth says
— after the model's words, in his language — that only part was done and on which card.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import canvas_focus
from nucleo.circuit import verdict as V
from nucleo.turn import acts_asked, brief, reply, verdicts


class _Done:
    def __init__(self, res):
        self._r = res

    def done(self):
        return True

    def cancelled(self):
        return False

    def result(self):
        return self._r


OK = {"ok": True, "result": {"contact": {"name": "Nerea Solís"}}}
SP = type("S", (), {"sanitize": staticmethod(lambda t, **_: t)})


@pytest.fixture
def turn(monkeypatch):
    st = {"choice": acts_asked.SEVERAL, "conf": 0.93}
    monkeypatch.setattr(verdicts, "read", lambda h, key, fb, min_confidence=None:
                        (st["choice"], {"confidence": st["conf"]})
                        if key == acts_asked.KEY and st["conf"] >= (min_confidence or 0) else (fb, None))
    monkeypatch.setattr(canvas_focus, "this_turn_acts", lambda: [])
    monkeypatch.setattr("nucleo.turn.brief_turn.of_this_turn", lambda: {})
    return st


def _say(tasks, said="Done."):
    out = []
    text = asyncio.run(reply.after_acts(tasks, said, out.append, SP))
    return text, out


def test_the_brief_asks_how_many_acts():
    assert acts_asked.KEY in brief.keys() and acts_asked.KEY in brief.build("hola")


@pytest.mark.parametrize("lang, word", [("en", "part"), ("es", "parte")])
def test_several_asked_one_ran_says_the_rest_is_not_done(turn, monkeypatch, lang, word):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    text, out = _say([("contactos::set_favorite", _Done(OK))])
    assert out and word in out[-1], f"«Done.» stood alone over half the order: {out}"
    assert text.startswith("Done.")


def test_two_acts_that_ran_owe_nothing(turn):
    _t, out = _say([("contactos::set_favorite", _Done(OK)), ("contactos::set_alias", _Done(OK))])
    assert not any("part" in o for o in out), out


def test_a_card_act_counts_as_an_act(turn, monkeypatch):
    monkeypatch.setattr(canvas_focus, "this_turn_acts", lambda: [("contactos", "show", "show")])
    _t, out = _say([("contactos::set_favorite", _Done(OK))])
    assert not any("part" in o for o in out), out


@pytest.mark.parametrize("choice, conf", [(acts_asked.ONE, 0.95), (acts_asked.SEVERAL, 0.6)])
def test_one_act_asked_or_a_doubt_says_nothing(turn, choice, conf):
    turn["choice"], turn["conf"] = choice, conf
    _t, out = _say([("contactos::set_favorite", _Done(OK))])
    assert not any("part" in o for o in out), out


def test_the_line_is_an_unmet_verdict_always_said(turn):
    got = acts_asked.left_undone([("agenda::add", None)], brief={})
    assert len(got) == 1 and got[0].verdict == V.UNMET.name and got[0].said
