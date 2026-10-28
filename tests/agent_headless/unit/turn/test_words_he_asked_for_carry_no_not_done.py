"""A turn whose act WAS the words owes no «No lo he hecho» (refactor2710-99, node 2.896).

Use case `docs-single-recipe-not-a-list__es` (2026-10-28): turn 2 told the recipe from memory — what he asked for — and
the mouth appended «No lo he hecho: desde aquí no he podido ejecutarlo.», because the brief read the turn as an `order`
and nothing ran. An order whose deliverable is WORDS (`wants_words = tell`, sure) is kept by the reply itself. The receipt
stays for an act owed and not done: an order for something to be DONE, or an errand.

Disarm: make `promise_kept.words_were_the_act` return False and the first test goes red.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.turn import brief, promise_kept


def _brief(**answers):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": [],
            "result": {k: {"choice": c, "confidence": p} for k, (c, p) in answers.items()}}


@pytest.fixture(autouse=True)
def _a_line(monkeypatch):
    monkeypatch.setattr(promise_kept, "_not_kept_line", lambda: "NOT-DONE")
    monkeypatch.setattr(promise_kept, "_state_holds", lambda open_ids=None: False)


def test_an_order_for_words_told_in_words_owes_no_receipt():
    b = _brief(**{brief.REQUEST_KEY: ("order", 0.95), brief.WORDS_KEY: ("tell", 0.95)})
    assert promise_kept.honest_line("Aquí tienes la receta…", None, acted=False, brief=b) == ""
    assert promise_kept.honest_line("…", {"kind": promise_kept.CANNOT}, acted=False, brief=b) == "", \
        "a repair pass that could not act over a card he did not ask for is no «not done» either"


@pytest.mark.parametrize("answers", [
    {brief.REQUEST_KEY: ("order", 0.95), brief.WORDS_KEY: ("act", 0.95)},                        # something to be DONE
    {brief.REQUEST_KEY: ("order", 0.95), brief.WORDS_KEY: ("tell", 0.6)},                        # unsure it was words
    {brief.ESCALATE_KEY: ("escalate", 0.9), brief.WORDS_KEY: ("tell", 0.95)},                    # an errand was owed
])
def test_an_owed_act_not_done_keeps_its_receipt(answers):
    assert promise_kept.honest_line("Hecho.", None, acted=False, brief=_brief(**answers)) == "NOT-DONE"
