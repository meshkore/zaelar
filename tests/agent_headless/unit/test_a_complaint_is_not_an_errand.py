"""V2-707 F6 · A complaint about what already happened is not an order to do it.

## The session

`080b96a7`, 2026-09-16. Nine agenda rows had just been deleted and he spent six turns trying to say so.
Each of those turns opened a Brain Worker task:

    i=10804  «No. You did delete all»                                  → i=10820 backstop → task 2
    i=10829  «No. You did delete all day, and I just set three of them.» → i=10856 backstop → task 3
    i=10873  «Are you stupid? You just did delete.»                      → i=10918 backstop → task 5
    i=11064  «…items that you did delete without my permission.»         → merged into a live task

Each one then parked at the irreversibles gate and was discarded («🚫 tarea irreversible descartada por el
operador»), and while that happened surfaces opened on his canvas — `navegador::t1`, `results::b8ed90-4` —
so his answer to «what did you do to my calendar» was a browser and a results sheet. His words, unprompted
at i=10937: «Do not open a fucking widget for this.»

The classifier behind all of it is `danger.is_dangerous`, read by TWO decision points — the voice
backstop (`providers/nucleo.py`, which the typed channel runs too) and `dispatch._run_session`'s own gate — and it
matched the verb in a sentence whose grammar says the act is in the PAST and was not asked for.

## The fix is a subtraction, and it uses the technique already in that module

`danger.py` already strips a clause before looking for a verb, twice: `_REMINDER_RE` so «recuérdame
pagar…» is not an order to pay, and `_AMOUNT_QUESTION_RE` so «¿cuánto hay que pagar?» is not either. This
is the same shape for a third case — an accusation in the past tense, and a question about whether it
happened. Fixing it at the classifier rather than at the backstop is deliberate: the readers must
never disagree about whether something is an order.

The clause ends at the next `. ! ? ; ,` — at the COMMA on purpose, so a turn that complains AND THEN orders
keeps its order. That case is pinned below in both languages, because a subtraction that swallows a real
order would be a worse defect than the one it fixes.
"""
from __future__ import annotations


import pytest

from nucleo import danger

# ── 1 · the four turns he actually said ─────────────────────────────────────────────────────────────────

MEASURED = [
    "No. You did delete all",
    "No. You did delete all day, and I just set three of them.",
    "Are you stupid? You just did delete.",
    "What appointments are you talking about? We are talking about items that you did delete without my "
    "permission.",
]


@pytest.mark.parametrize("text", MEASURED)
def test_the_measured_complaints_are_not_orders(text):
    assert danger.is_dangerous(text) is False, text
    assert danger.about_a_past_act(text) is True, "and the timeline must be able to say WHY"


# ── 2 · the class, not just those four sentences: its phrase cases are in the is_dangerous table of
#      test_the_gate_reads_the_order_not_the_words.py (`test_a_past_act_is_discussed_not_ordered[n]`).

# ── 3 · what must NOT move: a real order still stops ────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "delete my account",
    "can you delete my account",
    "borra mi cuenta de Spotify",
    "pay the electricity bill before the 5th",
    "paga la factura de la luz",
    "you have to pay the bill",                    # «have to» is not a past participle
    "publica el anuncio",
    "unsubscribe me from that",
    "dame de baja de la suscripción",
    "cancela la suscripción",
    "buy it now",
])
def test_an_order_is_still_an_order(text):
    assert danger.is_dangerous(text) is True, text
    assert danger.about_a_past_act(text) is False


# A complaint that ENDS IN AN ORDER keeps the order — those rows are in the same table
# (`test_a_complaint_that_ENDS_IN_AN_ORDER_keeps_the_order[n]`).


def test_the_money_and_commitment_readers_agree_with_the_gate():
    """`moves_money` picks the sentence the operator HEARS and `ends_a_commitment` decides another gate.
    Reading the same text with different rules is how a backstop and a door start contradicting each other
    — the exact shape of V2-707's measured incident, one layer up."""
    assert danger.moves_money("Why did you pay that? I never asked you to.") is False
    assert danger.moves_money("pay the bill") is True
    assert danger.ends_a_commitment("You already cancelled my subscription") is False
    assert danger.ends_a_commitment("cancela mi suscripción") is True


# ── 4 · the wiring: the backstop that opened the three tasks reads THIS classifier ───────────────────────


@pytest.mark.parametrize("text", MEASURED)
def test_the_worker_gate_lets_a_complaint_through_and_still_stops_an_order(text):
    """The worker gate's door (`errand.class_of` → `asks_first`, read by `dispatch._run_session`): with no class
    verdict, a complaint about a past act is no danger and starts nothing that asks; a real order still asks."""
    from nucleo.acts import errand
    assert errand.class_of(None, text) == "none"
    assert errand.asks_first(errand.class_of(None, text), confirmed=False) is False
    assert errand.asks_first(errand.class_of(None, "delete my account"), confirmed=False) is True
