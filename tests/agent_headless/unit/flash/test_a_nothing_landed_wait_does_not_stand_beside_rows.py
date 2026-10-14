"""A wait that denies in other words — «nothing landed yet», «still nothing», «no luck», «todavía nada» — is cut when
the delivery backstop hands over the errand's rows, and a «Right now:» that introduced it goes with it (node 2.660).

search-buy-boat-multicountry EN (2026-10-14, sandbox 093848-en): the replies «Not yet — no luck on Boat Trader so far,
nothing has landed yet» and «Will do. Right now: still on Boat Trader, nothing landed yet.» were the model's own
lines. `nothing_claims` knew «nothing yet» and «there is nothing», not these, so with rows on the sheet the backstop
would have glued the boats after a sentence saying none had landed.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.flash import delivery, live_blocks, nothing_claims

ERRAND = "Find me a used Lagoon 440 catamaran for under $325,000, in the US, Canada or Mexico."
ROWS = ["2004 Lagoon 440, Cancun Mexico — $149,995 — https://www.boats.com/sailing-catamarans/2004-lagoon-440/",
        "2007 Lagoon 440 — $289,000 — https://www.yachtworld.com/yacht/2007-lagoon-440/"]


def _brief() -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": [], "_call_id": "t",
            "result": {"wants_words": {"choice": "tell", "confidence": 1.0},
                       "escalate_or_inline": {"choice": "handle_inline", "confidence": 1.0}}}


@pytest.fixture
def boats(monkeypatch):
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
    monkeypatch.setattr(delivery, "_speaks_en", lambda: True)
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: (ERRAND, ROWS[:n]))
    delivery.forget_announced()


@pytest.mark.parametrize("reply", [
    "Will do. Right now: still on Boat Trader, nothing landed yet.",
    "Not yet — no luck on Boat Trader so far, nothing has landed yet.",
    "Still nothing on the sheet — I'm working the browser and hitting blocks on the listing sites right now.",
])
def test_the_rows_replace_a_wait_that_says_none_landed(boats, reply):
    out = delivery.apply_to_reply(reply, [], heard_now="hmm ok, lmk if anything pops up", brief=_brief())
    assert "Cancun" in out, out
    low = out.lower()
    assert "nothing landed" not in low and "nothing has landed" not in low and "no luck" not in low, out
    assert "still nothing" not in low, out
    assert "Right now:" not in out, "the colon that announced the denial does not dangle before the rows"


@pytest.mark.parametrize("reply", [
    "Todavía nada: sigue buscando.", "De momento nada, sigo mirando portales.",
    # search-buy-camper ES (2026-10-14): the model's own wording, said over a sheet the door had emptied
    "Sigue sin haber resultados: el rastreo de anuncios de camper continúa y de momento no ha soltado nada que darte.",
])
def test_the_spanish_forms_are_cut_too(reply):
    out = nothing_claims.reconcile(reply, "Bueno, de hecho ya hay candidatos en la hoja: «Lagoon 440 — 299.000 €».")
    assert "nada" not in out.lower() and "sin haber" not in out.lower() and "Lagoon 440 — 299.000 €" in out, out


@pytest.mark.parametrize("reply", ["Still no results — the listing sites keep blocking me.",
                                   "The search hasn't turned up anything yet."])
def test_the_english_forms_of_the_same_denial_are_cut(reply):
    out = nothing_claims.reconcile(reply, "Actually, there are already candidates: «Lagoon 440 — $289,000».")
    assert out.startswith("There are already candidates"), out


def test_a_wait_without_a_denial_keeps_its_words():
    reply = "Will do — I'll flag it the second a boat lands."
    out = nothing_claims.reconcile(reply, "Actually, there are already candidates: «Lagoon 440 — $289,000».")
    assert out.startswith(reply), out
