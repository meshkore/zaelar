"""A sure `screen_action = none` is the opposite of «a sure order on a card»: no guard may read it as one (node 2.919).

Live, 2026-10-28 17:48 (T22): «…I want to be sure it will be showed here, and in what channel. I have netflix, hbo,
prime, disney» — the brief read `none` at 1.00; the model proposed a web search (in Spanish, sharing no word with his
English turn); `a_search_is_his` took the sure `none` for a sure card order and dropped the search; the turn ended
with nothing to say and the mouth fell back to «Sorry, I lost that. Could you say it again?».

Disarm: with `_action_sure` ignoring the choice again, the first test goes red.
"""
from __future__ import annotations

import threading

from nucleo.flash import direct_action as _da
from nucleo.flash import tool_executor_calls as calls
from nucleo.turn import brief as _tb


def _brief(answers: dict):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": ["mensajeria"],
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}


def _overlap(a, b):
    return len({w for w in a.lower().split() if len(w) > 3} & {w for w in b.lower().split() if len(w) > 3})


def test_a_search_in_another_language_survives_a_sure_none():
    b = _brief({_tb.TARGET_KEY: ("none", 1.0)})
    said = "of course, I want to be sure it will be showed here, and in what channel. I have netflix, hbo, prime, disney"
    assert calls.a_search_is_his("Dexter Resurrection temporada 2 estreno España dónde ver", said, b, _overlap)
    assert _da._action_sure(b, floor=0.9) is False


def test_a_sure_card_order_still_drops_a_search_sharing_nothing():
    b = _brief({_tb.TARGET_KEY: ("documento:goto", 0.96)})
    assert not calls.a_search_is_his("proveedores de internet en Sevilla", "go to the second page", b, _overlap)
    assert _da._action_sure(b, floor=0.9) is True


def test_a_search_sharing_a_word_with_his_turn_is_his_whatever_the_card():
    b = _brief({_tb.TARGET_KEY: ("documento:goto", 0.96)})
    assert calls.a_search_is_his("Dexter premiere date", "verify this: Dexter premiere", b, _overlap)
