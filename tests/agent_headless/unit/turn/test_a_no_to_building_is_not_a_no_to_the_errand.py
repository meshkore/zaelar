"""A «no» to BUILDING a card is not a «no» to the errand (docs-single-recipe-not-a-list EN, 2026-10-14).

Sandbox 20261014-120418-en: the build gate asked «Shall I build you a new card?»; he answered «just the recipe is
fine, no need to build anything», and the model re-escalated the same recipe with no card to build. The «no»
resolved the gate and the re-escalation was dropped as «the errand the answer resolved» — nothing wrote the recipe.
After a «no» to a build, the same errand asked without the build still starts; a «yes», a «no» to anything that is
not a build, and a re-send that is still a build stay dropped, as before. Both channels call this rule.
"""
from __future__ import annotations

from nucleo.turn import errands_of_a_turn as eot

PARKED = "Build me a new widget that shows the classic carbonara recipe with guanciale, eggs and pecorino"
AGAIN = "Show the classic carbonara recipe with guanciale, eggs and pecorino on the document sheet"


def test_the_scene_is_one_errand_and_the_parked_one_was_a_build():
    from nucleo import errand_kind
    assert eot.same_errand(AGAIN, PARKED)
    assert errand_kind.code_change(PARKED) == "create" and errand_kind.code_change(AGAIN) == ""


def test_after_a_no_to_the_build_the_errand_without_it_starts():
    assert eot.beside_an_answer(PARKED, [AGAIN], declined=True) == [AGAIN]


def test_a_yes_keeps_the_old_rule():
    assert eot.beside_an_answer(PARKED, [AGAIN]) == []


def test_a_re_sent_build_after_a_no_stays_dropped():
    assert eot.beside_an_answer(PARKED, [PARKED + " please"], declined=True) == []


def test_a_no_to_an_errand_that_was_not_a_build_drops_its_re_send():
    errand = "cancel the gym subscription before the charge on Friday"
    assert eot.beside_an_answer(errand, [errand + " now"], declined=True) == []


def test_the_voice_channel_keeps_it_too():
    req = {"v": AGAIN, "more": []}
    eot.keep_beside_an_answer(req, PARKED, declined=True)
    assert req["v"] == AGAIN


def test_the_probe_channel_threads_the_answer():
    from nucleo.flash import probe_after
    calls = [{"name": "escalate_to_slowbrain", "args": {"request": AGAIN, "surface": "informe"}}]
    kept, _surf, _left = probe_after._the_turns_errands(calls, "just the recipe, no need to build anything", "",
                                                        resolved=PARKED, declined=True)
    assert kept == [AGAIN]
