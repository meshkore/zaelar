"""V2-852 T08 · A browser step never asks for a click that sends nothing (invariant I5).

Measured in his session of 2026-11-05: a car search on a listing site asked his OK for «Eliminar Toyota 4Runner» (a
filter chip) and for «Borrar todo Filtros» (clear the filters) — the button's TEXT matched the irreversible-label
table. What a click does decides, not what it says: removing a chip, clearing filters, paging and navigating send
nothing of his and run, tainted worker or not; a submit that hands a form's data over, a payment form, a password and
a checkout page still ask. Variants in English and other domains (a flat, a flight) on purpose.
"""
from __future__ import annotations

import asyncio

import pytest

from widgets.navegador import click_gate as G


def _sig(**kw):
    base = {"name": "", "role": "button", "isSubmit": False, "inForm": False, "payment": False, "method": "",
            "targetUrl": "", "pageUrl": "https://listings.example/search?make=honda", "signals": "", "fields": 0}
    base.update(kw)
    return base


SENDS_NOTHING = [
    _sig(name="Remove Honda Civic"),                                         # a chip, outside any form
    _sig(name="Clear all filters", role="link"),
    _sig(name="Eliminar Toyota 4Runner"),
    _sig(name="Borrar todo Filtros", isSubmit=True, inForm=True, method="get", signals="q price_max km_max"),
    _sig(name="Delete this filter", isSubmit=True, inForm=True, method="get", signals="rooms city"),
    _sig(name="Next page", role="link"),
]


@pytest.mark.parametrize("sig", SENDS_NOTHING, ids=lambda s: s["name"])
def test_a_click_that_sends_nothing_is_not_stopped(sig):
    assert G.decide(sig) == (False, ""), sig["name"]


@pytest.mark.parametrize("sig", [
    _sig(name="Delete account", isSubmit=True, inForm=True, method="post", signals="confirm"),
    _sig(name="Eliminar cuenta", isSubmit=True, inForm=True, signals="confirm"),    # method unread → sends (closed)
    _sig(name="Continue", isSubmit=True, inForm=True, method="post", signals="cc-number cvv"),
    _sig(name="Sign in", isSubmit=True, inForm=True, method="post", payment=True),
    _sig(name="Continue", pageUrl="https://air.example/booking/confirm"),
], ids=["delete-account", "method-unread", "payment-form", "password", "checkout-page"])
def test_an_act_that_leaves_still_asks(sig):
    assert G.decide(sig)[0] is True


class _Handle:
    def __init__(self, sig):
        self._sig = sig

    async def evaluate(self, _js):
        return dict(self._sig)


def test_a_tainted_worker_still_runs_a_chip_and_asks_for_a_submit_that_hands_his_identity(monkeypatch):
    """Decision 8 (browser workers are always tainted) holds for acts that LEAVE only."""
    from nucleo import on_his_behalf
    monkeypatch.setattr(G, "_tainted_submit", lambda task_id, sig: "it read pages since your last yes — send it?")
    monkeypatch.setattr(on_his_behalf, "form_question", lambda task_id, sig: "")
    monkeypatch.setattr(G, "needs_facts", lambda sig: [])
    asked: list[str] = []

    async def confirm(q):
        asked.append(q)
        return False

    for sig in SENDS_NOTHING:
        ok, why = asyncio.run(G.may_act(None, _Handle(sig), confirm=confirm, task_id="t1"))
        assert ok and why == "", (sig["name"], why)
    assert asked == [], f"a click that sends nothing asked him: {asked}"
    form = _sig(name="Send request", isSubmit=True, inForm=True, method="post", signals="email tel name")
    ok, _why = asyncio.run(G.may_act(None, _Handle(form), confirm=confirm, task_id="t1"))
    assert not ok and asked, "a submit that hands his identity over, after stranger pages, must ask"
