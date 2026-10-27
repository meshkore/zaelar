"""V2-792 — «I didn't catch what you said before the pause» is said only when his words really reached no turn.

The class, as measured: a long dictation (a minute and a half, many fragments) was held open by the acoustic layer
and handed to the accumulator as ONE string that began with the very fragment the buffer already held. The gap
since that fragment's offer was over `MAX_GAP_S`, so the gap valve discarded it — and the turn then ran with every
word of it. The operator heard «didn't catch what you said before the pause» over a request that was being handled,
and answered «I didn't say anything before the pause».

The door is `Accumulator.offer`: a discard whose words still travel in the text the turn runs with (or in the buffer
it keeps holding) is not a loss, so `dropped` comes back empty and neither the timeline line nor the spoken notice
fires (`_acc_notice_plan`). A fragment that really reaches no turn is still reported.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.input import stt as acc
from voice.engine.llm.providers.acc_notices import _acc_notice_plan

HELD = {"es": "Entonces, quiero que me organices ese viaje con una propuesta, vamos dos adultos, dos niños, quiero",
        "en": "So, I want you to plan that trip with a proposal, we are two adults, two kids, I want"}
REST = {"es": " ver qué trayectos haremos cada día, y me creas ese documento y me lo enseñas. Cuando lo tengas, "
              "me avisas.",
        "en": " to see which legs we drive each day, and you make me that document and show it. Tell me when it is ready."}
OTHER = {"es": "¿Qué tiempo hace mañana en Soria?", "en": "What's the weather tomorrow in Soria?"}


async def _ends_with_a_stop(text: str) -> tuple[str, str]:
    return ("complete", "") if text.rstrip().endswith((".", "?")) else ("incomplete", "")


@pytest.fixture(autouse=True)
def _judge():
    acc.set_predicate(lambda t: (t.rstrip().endswith((".", "?")), ""))
    acc.set_judge(_ends_with_a_stop)
    yield
    acc.set_predicate(None)
    acc.set_judge(None)


def _offer(a, text, now):
    return asyncio.run(a.offer(text, now=now))


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_held_turn_handed_back_whole_after_the_gap_drops_nothing(lang):
    a = acc.Accumulator()
    assert _offer(a, HELD[lang], 100.0)[0] == "hold"
    action, text, _why, dropped = _offer(a, HELD[lang] + REST[lang], 100.0 + acc.MAX_GAP_S + 70)
    assert action == "act" and HELD[lang].split()[0] in text and text.endswith(REST[lang].split()[-1])
    assert dropped == "", "every held word is in the text the turn runs with — nothing was lost"
    assert _acc_notice_plan(action, dropped, 1) == (False, False), "no «didn't catch that» is spoken"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_grown_turn_still_held_after_the_gap_drops_nothing(lang):
    a = acc.Accumulator()
    _offer(a, HELD[lang], 100.0)
    action, _t, _w, dropped = _offer(a, HELD[lang] + " y además,", 100.0 + acc.MAX_GAP_S + 5)
    assert action == "hold" and dropped == "", "the buffer still holds those words"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_fragment_that_reaches_no_turn_is_still_reported(lang):
    a = acc.Accumulator()
    _offer(a, HELD[lang], 100.0)
    action, text, _why, dropped = _offer(a, OTHER[lang], 100.0 + acc.MAX_GAP_S + 5)
    assert action == "act" and text == OTHER[lang]
    assert dropped == HELD[lang], "his earlier words reached nothing: the notice is owed"
    assert _acc_notice_plan(action, dropped, 1)[0] is True


def test_carried_is_exact_and_contiguous():
    assert acc._carried("Vamos dos adultos,", "vale. vamos DOS adultos y dos niños")
    assert not acc._carried("vamos dos adultos", "vamos tres adultos")
    assert not acc._carried("vamos dos adultos", "adultos dos vamos")
    assert not acc._carried("", "anything")
