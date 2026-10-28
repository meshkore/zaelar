"""A text the model can WRITE is written in one request, not by a Brain Worker (demo 2026-10-22).

«write me a one page summary of the bitcoin whitepaper, in a document»: the brief named `documento` at 1.00, the
commission pass with the card in front could only answer in 300 tokens — a page never fits in a tool argument — so
it called nothing and a worker spent 5.5 minutes and $0.52. The pass now may call `compose_into_card`; the text is
then written by ONE request and lands through the card's declared action. Any failure goes to the worker as before.
"""
from __future__ import annotations

import asyncio

from nucleo.flash import act_repair, card_commission, compose_rung

ORDER = "write me a one page summary of the bitcoin whitepaper, in a document"


def test_a_card_that_holds_prose_declares_where_the_text_goes():
    assert compose_rung.prose_action("documento") == "show"
    assert compose_rung.prose_action("agenda") == ""


def test_the_commission_pass_may_choose_to_write_it(monkeypatch):
    from nucleo.llm import fast_client
    offered: list = []

    async def _complete(self, msgs, *, on_tool_call=None, tools=None, **k):
        offered.extend(t["function"]["name"] for t in tools or [])
        on_tool_call("compose_into_card", {"widget_id": "documento", "title": "Bitcoin whitepaper — one page",
                                           "brief": "a one-page summary"})
    monkeypatch.setattr(fast_client.FastClient, "complete", _complete)
    got = asyncio.run(act_repair.call_or_read_for_commission(ORDER, "Write a one-page summary…", "documento"))
    assert compose_rung.TOOL_NAME in offered
    assert got == {"kind": "compose", "widget_id": "documento", "action": "show",
                   "title": "Bitcoin whitepaper — one page", "brief": "a one-page summary"}


def test_a_card_that_holds_no_prose_is_never_offered_the_tool(monkeypatch):
    from nucleo.llm import fast_client
    offered: list = []

    async def _complete(self, msgs, *, on_tool_call=None, tools=None, **k):
        offered.extend(t["function"]["name"] for t in tools or [])
    monkeypatch.setattr(fast_client.FastClient, "complete", _complete)
    asyncio.run(act_repair.call_or_read_for_commission("find me a free slot tomorrow", "find a slot", "agenda"))
    assert offered and compose_rung.TOOL_NAME not in offered


def test_the_turn_hands_the_writing_off_and_spends_no_worker(monkeypatch):
    got = {"kind": "compose", "widget_id": "documento", "action": "show", "title": "Bitcoin", "brief": "one page"}

    async def _decide(*a, **k):
        return got
    ran: list = []

    async def _run(g, **k):
        ran.append((g, k["commission"]))
    monkeypatch.setattr(card_commission, "commission_call", _decide)
    monkeypatch.setattr(compose_rung, "run", _run)
    req = {"v": "Write a one-page summary of the Bitcoin whitepaper", "more": []}

    async def go():
        r = await card_commission.before_worker(req, {"v": None}, brief=None, operator_text=ORDER, spec=None,
                                                emit=lambda *a, **k: None, present=lambda *a, **k: None,
                                                apply_widget_data=lambda *a: None)
        await asyncio.sleep(0)
        return r
    assert asyncio.run(go()) == "call"
    assert req["v"] is None, "the worker was still commissioned"
    assert ran == [(got, "Write a one-page summary of the Bitcoin whitepaper")]


def _wire_run(monkeypatch, body: str):
    from nucleo.flash import canvas_visibility, data_ops, escalate
    ops, escalated = [], []

    async def _compose(*a, **k):
        return body

    async def _dispatch(wid, action, payload, **k):
        ops.append((wid, action, payload))
        return {"ok": True}

    async def _tell(title):
        return None
    monkeypatch.setattr(compose_rung, "compose", _compose)
    monkeypatch.setattr(compose_rung, "_tell", _tell)
    monkeypatch.setattr(data_ops, "dispatch_and_report", _dispatch)
    monkeypatch.setattr(canvas_visibility, "present", lambda *a, **k: None)
    monkeypatch.setattr(escalate, "escalate_to_slowbrain", lambda req, **k: escalated.append(req) or 1)
    return ops, escalated


GOT = {"kind": "compose", "widget_id": "documento", "action": "show", "title": "Bitcoin", "brief": "one page"}


def test_the_text_lands_through_the_cards_declared_action(monkeypatch):
    ops, escalated = _wire_run(monkeypatch, "## The problem\nDouble spending…")
    assert asyncio.run(compose_rung.run(GOT, commission="c", operator_text=ORDER, spec=None)) is True
    assert ops == [("documento", "show", {"title": "Bitcoin", "body": "## The problem\nDouble spending…"})]
    assert not escalated


def test_nothing_written_goes_to_the_worker_as_before(monkeypatch):
    ops, escalated = _wire_run(monkeypatch, "")
    assert asyncio.run(compose_rung.run(GOT, commission="the commission", operator_text=ORDER, spec=None)) is False
    assert not ops and escalated == ["the commission"]
