"""The card on screen that his words name closes, whatever a single-choice names verdict said (demo sandbox
2026-10-29, pass 2, C6; V2-831 T-19 R4c).

«close the calendar and the messages», with the agenda open and the messages not. The brief read canvas=close 1.00,
screen_action=none 0.51 and names_a_card=elsewhere 0.80, even with the mixed criterion of #101. The model called
nothing and said «— done, both closed». Every close reader asked `names_elsewhere` and stood down, and the agenda
stayed open. The promise was detected, and no honest line followed: the previous turn's card was still on screen,
and `promise_kept.owed` read that as «the reply describes the screen».

  · `brief_screen.names_elsewhere` never holds when the judged sentence calls a card open at fire time by its
    catalogue NAME (outside a «keep» clause): the screen outranks a choice that cannot say «this one AND another».
  · `promise_kept.owed`: a sure canvas gesture with nothing run is never «what the screen shows».

Disarm: make `_calls_a_card_on_screen` answer False, or let `owed` excuse a sure gesture by the held screen. The
real-turn close tests and the honest-line test go red.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.turn import brief as tb, brief_screen

MIXED = {"en": ("close the calendar and the messages", "— done, both closed."),
         "es": ("cierra la agenda y los mensajes", "— hecho, cerradas las dos.")}
PASS2 = {"canvas": ["close", 1.0], "screen_action": ["none", 0.51], "names_a_card": ["elsewhere", 0.80],
         "wants_words": ["act", 1.0], "escalate_or_inline": ["handle_inline", 1.0], "request_type": ["order", 0.9]}


def _handle(judged, open_ids, names=("elsewhere", 0.9)):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": list(open_ids), "judged": judged,
            "result": {tb.NAMES_KEY: {"choice": names[0], "confidence": names[1], "probs": {names[0]: names[1]}}}}


@pytest.mark.parametrize("lang", ["en", "es"])
def test_a_card_on_screen_his_words_name_is_never_elsewhere(lang):
    h = _handle(MIXED[lang][0], ["agenda", "results"])
    assert brief_screen.names_elsewhere(h) is False and brief_screen.names_elsewhere(h, against_a_call=True) is False


@pytest.mark.parametrize("said", ["close the weekend", "cierra el finde", "close the messages", "close the messages, "
                                  "keep the calendar up"])
def test_the_verdict_stands_when_no_card_on_screen_is_named(said):
    assert brief_screen.names_elsewhere(_handle(said, ["agenda", "results"])) is True


# ── the real headless turn ────────────────────────────────────────────────────────────────────────────────────
def _turn(lang, phrase, say, open_ids):
    from tests.brain import harness
    case = {"id": f"r4c-{lang}", "lang": lang, "phrase": phrase, "source": "demo sandbox 2026-10-29 pass 2 C6",
            "screen": {"open": list(open_ids)}, "model": {"say": say, "tools": []}, "brief": dict(PASS2),
            "expect": "close agenda", "forbid": ["data-op"]}
    return harness.run_case(case)


@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_named_card_on_screen_closes_and_the_absent_one_is_not_used(lang):
    out = _turn(lang, *MIXED[lang], ["agenda", "results"])
    assert out.decision == "close agenda", (out.decision, out.also, out.reply)
    assert "close mensajeria" not in out.all_decisions and not [d for d in out.all_decisions if d.startswith("data-op")]


@pytest.mark.parametrize("lang", ["en", "es"])
def test_both_named_cards_on_screen_both_close(lang):
    out = _turn(lang, *MIXED[lang], ["agenda", "mensajeria"])
    assert {"close agenda", "close mensajeria"} <= set(out.all_decisions), out.all_decisions


def test_nothing_named_on_screen_closes_nothing_and_says_so():
    out = _turn("en", "close the weekend", "Done.", ["agenda", "results"])
    assert out.decision == "talk" and "haven't done it" in out.reply, (out.decision, out.reply)


# ── the honest line ───────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def held_screen(monkeypatch):
    from nucleo.turn import promise_kept, reply
    monkeypatch.setattr(promise_kept, "_state_holds", lambda open_ids=None: True)
    monkeypatch.setattr(reply, "owes_an_act", lambda brief: "order")
    return promise_kept


def _gesture_brief(verb):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": ["agenda"],
            "result": {tb.CANVAS_KEY: {"choice": verb, "confidence": 1.0, "probs": {verb: 1.0}}}}


def test_a_sure_gesture_left_undone_owes_the_honest_line_over_a_held_screen(held_screen):
    assert held_screen.owed(_gesture_brief("close")) is True
    assert held_screen.owed(_gesture_brief("neither")) is False, "a reply describing the held screen still owes nothing"
