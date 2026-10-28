"""A row that does not carry what he asked about is not glued to the reply as news (node 2.700).

search-buy-vinyl EN (2026-10-14, sandbox 104623-en): after «are any of them actually original pressings? and what
condition are they in» and «no need to show it again, just let me know when you have the pressing and condition
details», the delivery backstop appended «Actually, there are already candidates on the results sheet: …» three
times — titles and prices, nothing about pressing or condition — once right after the model's «I won't push the
sheet on you again». A row carries what he asked when its title names it or one of its facts VERIFIES it.
"""
from __future__ import annotations

import pytest

from nucleo.flash import asked_fact_hold as H
from nucleo.flash import delivery, live_blocks

COMMISSION = "Find me an original pressing of 'The Dark Side of the Moon' in good condition for under $70."
ASKED = "prices look fine, but are any of them actually original pressings? and what condition are they in"
ROWS = ["Pink Floyd 'DARK SIDE OF THE… — 37.82", "Pink Floyd the Dark Side of the… — 45.37"]
BARE = [{"title": "Pink Floyd 'DARK SIDE OF THE…", "price": "37.82",
         "facts": [{"label": "Rating", "value": "99.8"}, {"label": "Origin", "value": "network agent"}]},
        {"title": "Pink Floyd the Dark Side of the…", "price": "45.37", "facts": []}]
VERIFIED = [{"title": "Pink Floyd 'DARK SIDE OF THE…", "price": "37.82",
             "facts": [{"label": "original pressing (1973 first press)", "value": "yes — Harvest SMAS-11163"},
                       {"label": "good condition", "value": "no — graded G+"}]},
            {"title": "Pink Floyd the Dark Side of the…", "price": "45.37",
             "facts": [{"label": "original pressing (1973 first press)", "value": "? — not stated"}]}]
WAIT = "I'll let you know as soon as I have the pressing and condition details — I'm pushing on that now."


def _window(*his):
    return [{"role": "user", "content": t} for t in his]


@pytest.fixture
def vinyl(monkeypatch):
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: (COMMISSION, ROWS[:n]))
    monkeypatch.setattr(delivery, "_speaks_en", lambda: True)
    delivery.forget_announced()
    return monkeypatch


def test_what_he_asked_is_his_commission_said_again():
    said = [COMMISSION, "San Francisco", ASKED]
    assert H.asked(COMMISSION, said) == {"origin", "pressi", "condit"}
    assert H.asked(COMMISSION, [COMMISSION]) == set(), "the commission itself asks nothing new"
    assert H.asked(COMMISSION, [COMMISSION, "show me the cheapest under $70"]) == set(), "short words are no ask"


def test_a_shortlist_does_not_name_a_row_that_lacks_it(monkeypatch):
    monkeypatch.setattr(H, "recent_his_sentences", lambda limit=12: [COMMISSION, ASKED])
    kept = H.items_owed(COMMISSION, VERIFIED, H.recent_his_sentences())
    assert [i["price"] for i in kept] == ["37.82"]


def test_the_unprompted_first_rows_notice_holds_them_too(monkeypatch):
    from i18n import langs
    from nucleo.turn import first_rows_notice as frn
    frn.forget()
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("en"))
    now = 1_000_000.0
    talk = [{"t_ms": now - 200_000, "kind": "brain", "wall": "you", "role": "user", "text": COMMISSION},
            {"t_ms": now - 100_000, "kind": "brain", "wall": "you", "role": "user", "text": ASKED + ", let me know"},
            {"t_ms": now - 90_000, "kind": "brain", "wall": "agent", "role": "assistant", "text": WAIT}]
    errand = {"id": "v1", "request": COMMISSION, "secs": 300, "sheet": "v1-ls1"}
    bare = [dict(i, url=f"https://ebay.com/{n}") for n, i in enumerate(BARE)]
    said, why = frn.decide("v1-ls1", {"items": bare}, errand=errand, events=talk, now_ms=now)
    assert said == "" and why == "rows lack what he asked about", (said, why)
    said, why = frn.decide("v1-ls1", {"items": [dict(i, url=f"https://ebay.com/{n}") for n, i in enumerate(VERIFIED)]},
                           errand=errand, events=talk, now_ms=now)
    assert "DARK SIDE OF THE" in said and "45.37" not in said, (said, why)
    frn.forget()
