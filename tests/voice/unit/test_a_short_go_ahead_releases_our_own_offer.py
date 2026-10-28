"""«Do it» after our offer is not a fragment: the errand the model proposes RESTATES our previous line, so the directive
came from our sentence and his short turn only released it (node 2.920).

Live, 2026-10-28 17:49 (T28): we had said «…the results don't explicitly confirm the Spain release, though it's listed
as the same Paramount+ Premium date, so I can dig into that specifically if you want.» He said «d oit». The model
proposed «Check for Richard (living in Spain) where and when Dexter: Resurrection Season 2…» and the fragment guard
annulled it because our offer carried no question mark (`answered_an_offer`). The reply was «Sorry, I didn't follow».

Disarm: with `restates_our_offer` answering False, the first test goes red.
"""
from __future__ import annotations

from nucleo.flash import escalation_guard, prior_line

OFFER = ("Got it — let me check where Dexter: Resurrection Season 2 will actually be available in Spain. The results "
         "don't explicitly confirm the Spain release, so I can dig into that specifically if you want.")
ERRAND = "Check for Richard (living in Spain) where and when Dexter: Resurrection Season 2 will be available"


def test_a_typo_go_ahead_whose_errand_restates_our_offer_is_not_a_fragment():
    assert escalation_guard.is_a_fragment("d oit", brief=None, last_reply=OFFER, errand=ERRAND) is False
    assert prior_line.restates_our_offer(OFFER, ERRAND)


def test_the_same_short_turn_with_an_errand_from_nowhere_is_still_a_fragment():
    assert escalation_guard.is_a_fragment("d oit", brief=None, last_reply=OFFER,
                                          errand="Book a table for two at a sushi place tonight") is True


def test_drop_if_fragment_keeps_the_commission_and_drops_the_stranger():
    req = {"v": ERRAND, "more": []}
    assert escalation_guard.drop_if_fragment(req, operator_text="vale", brief=None, last_reply=OFFER) is False
    assert req["v"] == ERRAND
    req = {"v": "Order groceries for the week", "more": []}
    assert escalation_guard.drop_if_fragment(req, operator_text="vale", brief=None, last_reply=OFFER) is True
    assert req["v"] is None
