"""V2-764 — the model PROMISED to act on a card and called nothing: one pass asks it for the call.

Measured on the live engine with a clean window per phrase: «Busca en torrent la serie Sherlock» → «Voy a por la
serie Sherlock en torrent y te enseño el catálogo en cuanto lo tenga» and NO tool; «Hazme una lista de torrents de
documentales de la NASA» → the same. The turn's own verdict named the card (`archivos`), the action existed
(`torrent_search`), the model even said which one it meant. With the repair wired, the same battery went from
promises to calls (see the initiative's table).

These pin the repair's BOUNDS, which are the whole safety of a second model call: only the card the verdict
names, only an action that card declares, nothing when the model still calls nothing — and it runs BEFORE the
promise backstop that would otherwise have spent a worker on the turn.
"""
from __future__ import annotations


import asyncio
from pathlib import Path

import pytest

from nucleo.acts import repair_of_a_view

ENGINE = Path(__file__).resolve().parents[3]


class _Client:
    """A FastClient whose `complete` answers with the tool calls it is given — the real signature."""
    calls: list = []
    answer: list = []

    def __init__(self, *a, **k):
        pass

    async def complete(self, messages, *, spec=None, max_tokens=None, tools=None, on_tool_call=None,
                       no_thinking=False):
        _Client.calls.append({"messages": messages, "tools": tools})
        for name, args in _Client.answer:
            on_tool_call(name, args)
        return ""


@pytest.fixture
def client(monkeypatch):
    from nucleo.llm import fast_client
    monkeypatch.setattr(fast_client, "FastClient", _Client)
    _Client.calls, _Client.answer = [], []
    return _Client


def test_the_escalate_tool_says_a_torrent_is_not_an_errand():
    from nucleo.flash import router_catalog as rc
    desc = next(t for t in rc.TOOLS if t["function"]["name"] == "escalate_to_slowbrain")["function"]["description"]
    no = desc.split("NO:")[1]
    assert "TORRENTS" in no and "archivos:torrent_search" in no


def _run_cr(*a, **k):
    return asyncio.run(repair_of_a_view.call_or_read_for_commission(*a, **k))


def test_a_commission_that_names_a_card_is_read_or_called_before_it_costs_a_worker(client, monkeypatch):
    """V2-773 final pass (C1): «Find me a free 45-minute slot tomorrow afternoon» went to a Brain Worker while
    the agenda — named by the catalogue verdict — held the whole answer. One pass with the card in front."""
    from nucleo.flash import widget_read
    monkeypatch.setattr(widget_read, "read", lambda wid: "citas próximas (3): …")
    _Client.answer = [("read_widget", {"widget_id": "agenda", "question": "What is free on 2026-09-27 between 12:00 and 18:00?"})]
    got = _run_cr("Find me a free 45-minute slot tomorrow afternoon to talk with Rowan.", "Find a free slot…", "agenda")
    assert got == {"kind": "read", "widget_id": "agenda", "question": "What is free on 2026-09-27 between 12:00 and 18:00?"}
    offered = [t["function"]["name"] for t in _Client.calls[-1]["tools"]]
    assert offered == ["widget_data", "read_widget"], offered
    assert "citas próximas (3)" in _Client.calls[-1]["messages"][0]["content"], "the card rides the pass"
    # demo v4, C5: the pass sent `contact: "@northfunddemo"` — a handle from memory, misspelt — and the card
    # answered «no tengo a @northfunddemo en el directorio»; the contact is the NAME he said.
    assert "person's NAME" in _Client.calls[-1]["messages"][0]["content"]
    _Client.answer = [("widget_data", {"widget_id": "agenda", "action": "add_meeting", "payload": {"title": "x", "date": "2026-09-27"}})]
    got = _run_cr("Put a meeting tomorrow", "…", "agenda")
    assert got and got["kind"] == "call" and got["action"] == "add_meeting"
    _Client.answer = []
    assert _run_cr("Book me a table for two", "book a table", "agenda") is None, "nothing called → the worker keeps the errand"
    _Client.answer = [("read_widget", {"widget_id": "contactos", "question": "?"})]
    assert _run_cr("x", "x", "agenda") is None, "another card's call is not this card's answer"
    assert widget_read.can_answer("agenda") and not widget_read.can_answer("no-such-widget")


def test_a_card_that_cannot_answer_still_takes_the_call(client, monkeypatch):
    """Coordination block (K1): «Message Rowan on Telegram» went to a Brain Worker — the messaging card cannot
    answer questions, so the pass was never offered to it. Any named card may take the CALL; only one that
    can answer is offered the read."""
    from nucleo.flash import widget_read
    monkeypatch.setattr(widget_read, "read", lambda wid: "")
    monkeypatch.setattr(widget_read, "can_answer", lambda wid: wid == "agenda")
    _Client.answer = [("widget_data", {"widget_id": "mensajeria", "action": "send_to",
                                       "payload": {"contact": "Rowan", "channel": "telegram", "text": "16:30"}})]
    got = _run_cr("Message Rowan on Telegram and tell him the new meeting time.", "send Rowan…", "mensajeria")
    assert got and got["kind"] == "call" and got["action"] == "send_to", got
    assert [t["function"]["name"] for t in _Client.calls[-1]["tools"]] == ["widget_data"], "no read for a card that cannot answer"
