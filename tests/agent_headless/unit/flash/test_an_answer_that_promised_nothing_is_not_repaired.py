"""An answer that promised nothing is never repaired into an act (V2-781 T529, pair 16).

«and the day after the dinner, do I have anything?» → «The day after the dinner is Friday the 16th, and you've got
nothing on it.» — right, and `reply_promise=none (1.00)`. The promise repair ran anyway (the catalogue named the
agenda), made `show_day`, blanked the answer and spoke «Done. Right now it holds: …». A repair is for a promise
without a call, or a refusal of an act the card declares — never for a reply that promised nothing.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import act_repair as A, reply_promise as RP


@pytest.fixture
def spy(monkeypatch):
    calls = []

    async def _cfp(*a, **k):
        calls.append(a)
        return {"widget_id": "agenda", "action": "show_day", "payload": {"day": "2026-10-16"}}
    monkeypatch.setattr(A, "call_for_promise", _cfp)
    return calls


def _run(reply, verdict, kind="question"):
    import unittest.mock as m
    from nucleo.flash import turn_brief as TB
    with m.patch.object(RP, "verdict", lambda r: verdict), \
            m.patch.object(TB, "read", lambda b, key, d="", **k: (kind, {"confidence": 1.0})):
        return asyncio.run(A.call_for_promise_or_order("do I have anything on the 16th?", reply, "agenda",
                                                       brief=object()))


def test_a_sure_none_is_left_as_it_was(spy):
    assert _run("The 16th is free, you've got nothing on it.", "none") is None and spy == []


def test_a_promise_or_an_unread_verdict_still_repairs(spy):
    assert _run("I'll pull up that day.", "act")
    assert _run("I'll pull up that day.", None)


def test_a_refusal_still_reaches_the_verdict(spy):
    assert _run("I can't send it myself.", "none")


def test_a_claim_on_an_order_is_still_repaired(spy):
    """«none» also reads a report of something done («Hecho.»); over an ORDER that claim with no call is repaired."""
    assert _run("Hecho.", "none", kind="order")


def test_the_text_channel_hands_the_brief():
    assert "brief=_tbrief) if _ar_wid" in open("nucleo/flash/probe_mirrors.py", encoding="utf-8").read()
