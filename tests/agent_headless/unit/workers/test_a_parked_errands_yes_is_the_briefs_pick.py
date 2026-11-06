"""A parked errand's question is answered by the brief's pick among its two DECLARED answers (node 2.1624, V2-857
review). P0-1 put the question on the row but declared no answers, and its rerun dropped the pick: his yes was read
by the word reader (`_says_yes` → `classify_reply`) first — the class CRIT-C13 forbids.
"""
from __future__ import annotations

import pytest

from nucleo.dispatch import confirm as dc
from tests.agent_headless.unit.workers.test_a_parked_errand_waits_on_its_own_row import gate  # noqa: F401 — fixture


def test_the_question_declares_its_two_answers(gate):
    from nucleo.request.consent_ask import yes_no
    dc.make_durable("k1", gate.rec)
    _uid, entry = gate.asked[0]
    assert entry["candidates"] == entry["options"] == yes_no() and len(yes_no()) == 2


@pytest.mark.parametrize("lang,words", [("es", "venga, adelante con eso"), ("en", "go on then, do it")])
def test_the_briefs_yes_pick_relaunches_whatever_his_words(gate, lang, words):
    """«venga, adelante con eso» is no plain yes to the word reader: the brief's `#0` is the answer that binds."""
    from nucleo.request import inline_ask
    dc.make_durable("k1", gate.rec)
    _uid, entry = gate.asked[0]
    import asyncio
    assert asyncio.run(inline_ask.rerun("row-1", entry, words, choice=0))["ok"] is True
    assert len(gate.launched) == 1


def test_the_briefs_no_pick_ends_the_row_even_over_a_yes_word(gate):
    from nucleo.request import inline_ask
    dc.make_durable("k1", gate.rec)
    _uid, entry = gate.asked[0]
    import asyncio
    assert asyncio.run(inline_ask.rerun("row-1", entry, "sí… bueno, mejor no", choice=1))["ok"] is False
    assert not gate.launched and gate.settled[0]["state"] == "cancelled"
