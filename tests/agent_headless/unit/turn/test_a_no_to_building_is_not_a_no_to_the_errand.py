"""A «no» to BUILDING a card is not a «no» to the errand (docs-single-recipe-not-a-list EN, 2026-10-14).

Sandbox 20261014-120418-en: the build gate asked «Shall I build you a new card?»; he answered «just the recipe is
fine, no need to build anything», and the model re-escalated the same recipe with no card to build. The «no»
resolved the gate and the re-escalation was dropped as «the errand the answer resolved» — nothing wrote the recipe.
After a «no» to a build, the same errand asked without the build still starts; a «yes», a «no» to anything that is
not a build, and a re-send that is still a build stay dropped, as before. Both halves are STATE (V2-851 F4): the gate
parked it, and this turn's brief says whether the re-send is card code — never his words.
"""
from __future__ import annotations

import pytest

from nucleo.request import kind as _kind
from nucleo.turn import declined_build, errands_of_a_turn as eot

PARKED = "Build me a new widget that shows the classic carbonara recipe with guanciale, eggs and pecorino"
AGAIN = "Show the classic carbonara recipe with guanciale, eggs and pecorino on the document sheet"


@pytest.fixture(autouse=True)
def _gate_parked_the_build(monkeypatch):
    monkeypatch.setattr(declined_build, "_ASKED", [])
    declined_build.asked(PARKED)


def _this_turn(monkeypatch, choice: str) -> None:
    monkeypatch.setattr(_kind, "verdict", lambda b: {"choice": choice, "confidence": 0.95})


def test_after_a_no_to_the_build_the_errand_without_it_starts(monkeypatch):
    _this_turn(monkeypatch, _kind.GENERIC)
    assert eot.beside_an_answer(PARKED, [AGAIN], declined=True) == [AGAIN]


def test_a_yes_keeps_the_old_rule():
    assert eot.beside_an_answer(PARKED, [AGAIN]) == []


def test_a_re_sent_build_after_a_no_stays_dropped(monkeypatch):
    _this_turn(monkeypatch, _kind.BUILD)
    assert eot.beside_an_answer(PARKED, [PARKED + " please"], declined=True) == []


def test_a_no_to_an_errand_that_was_not_a_build_drops_its_re_send(monkeypatch):
    _this_turn(monkeypatch, _kind.GENERIC)
    errand = "cancel the gym subscription before the charge on Friday"
    assert eot.beside_an_answer(errand, [errand + " now"], declined=True) == []


def test_the_voice_channel_keeps_it_too(monkeypatch):
    _this_turn(monkeypatch, _kind.GENERIC)
    req = {"v": AGAIN, "more": []}
    eot.keep_beside_an_answer(req, PARKED, declined=True)
    assert req["v"] == AGAIN
