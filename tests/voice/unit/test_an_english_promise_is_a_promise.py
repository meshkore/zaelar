"""The promise detector speaks English (V2-776 K4, 2026-09-29).

`promises_action` was a Spanish table: «Yep — putting Madonna on.», «I'll get that email drafted to Andrew now.»
and «Sending that off to Andrew now.» returned False, so every consumer — the act-repair gate, the promise
backstops, `a_promise_left_hanging` — paid a second model pass or missed its backstop on the English demo. The
English half lives in its own module (the ratchet says `router_guards.py` only shrinks); `promises_action`
composes both. Twenty replies measured on demo passes 33-58.
"""
import pytest

from nucleo.flash import router_guards as g

PROMISES = [
    "Yep — putting Madonna on.",
    "I'll get that email drafted to Andrew now.",
    "Sending that off to Andrew now.",
    "Switching it to Like a Prayer now.",
    "On it — I'll pull together a five-day warm-weather trip and bring it up when it's ready.",
    "Let me pull that up — the Helix Nebula shot by Tyler Young.",
    "Right away — opening the Samsung ViewFinity S7, the $179.99 one.",
    "I'll hunt down three 27-inch 4K monitors under about 400 and show you the options.",
    "Let me find that one for you.",
    "Give me a moment to look into that.",
    "Me pongo a buscarte las dos entradas.",
]
NOT_PROMISES = [
    "I can't send it myself — sending mail isn't something I can do on my end.",
    "Want me to write that to Andrew?",
    "Done.",
    "Back to normal size.",
    "Apple's at 338.40 USD, down 0.78% today — the chart's right there on your screen.",
    "You have no meetings at all tomorrow, September 30th — the whole day is free.",
    "March 12, 2027 — that's when your Tesla insurance renews.",
    "I don't have a Johnny here — it's just me, Zaelar.",
    "I won't send anything until you give me the time.",
]


@pytest.mark.parametrize("reply", PROMISES)
def test_a_first_person_promise_in_english_is_a_promise(reply):
    assert g.promises_action(reply) is True, reply


@pytest.mark.parametrize("reply", NOT_PROMISES)
def test_a_denial_a_question_a_fact_or_a_negated_promise_is_not(reply):
    assert g.promises_action(reply) is False, reply
