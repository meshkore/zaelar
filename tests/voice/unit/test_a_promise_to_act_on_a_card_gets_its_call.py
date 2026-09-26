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

from nucleo.flash import act_repair

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
    from nucleo.flash import fast_client
    monkeypatch.setattr(fast_client, "FastClient", _Client)
    _Client.calls, _Client.answer = [], []
    return _Client


def _run(*a, **k):
    return asyncio.run(act_repair.call_for_promise(*a, **k))


def test_the_promised_call_comes_back_and_the_pass_is_offered_ONE_tool(client):
    client.answer = [("widget_data", {"widget_id": "archivos", "action": "torrent_search",
                                      "payload": {"query": "Sherlock serie"}})]
    got = _run("Busca en torrent la serie Sherlock",
               "Voy a por la serie Sherlock en torrent y te enseño el catálogo", "archivos")
    assert got == {"widget_id": "archivos", "action": "torrent_search", "payload": {"query": "Sherlock serie"}}
    tools = client.calls[0]["tools"]
    assert [t["function"]["name"] for t in tools] == ["widget_data"], "the repair must offer ONE tool, no more"
    assert "torrent_search" in client.calls[0]["messages"][0]["content"], "the card's actions were not shown"


@pytest.mark.parametrize("answer", [
    [],                                                                                   # still no call
    [("widget_data", {"widget_id": "youtube", "action": "search", "payload": {"q": "x"}})],   # another card
    [("widget_data", {"widget_id": "archivos", "action": "format_disk", "payload": {}})],     # undeclared
    [("escalate_to_slowbrain", {"request": "x"})],                                         # not the tool
])
def test_anything_but_a_declared_action_of_the_named_card_is_nothing(client, answer):
    client.answer = answer
    assert _run("Busca en torrent la serie Sherlock", "Voy a por ello", "archivos") is None


def test_no_named_card_no_model_call(client):
    assert _run("hola", "Voy", "") is None and not client.calls


def test_both_channels_ask_for_the_call_before_the_promise_backstop_spends_a_worker():
    prov = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    repair = prov.index("_act_repair.call_for_promise(_op_text, spoken_text, _ar_wid, spec=spec)")
    backstop = prov.index('emit("brain", "🧭 escalada por backstop (prometió crear/gestionar sin escalar)"')
    assert repair < backstop, "the worker backstop runs before the repair — the promise becomes minutes of worker"
    assert '_bd_ar.named_card(_brief)' in prov, "the card must come from the turn's own verdict"
    probe = (ENGINE / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    # V2-770: the text channel asks with the operator's OWN words (not the turn text with notes glued on), and
    # first against the card its verdict names — then, with none named, lets the repair find one.
    assert "_act_repair.call_for_promise(operator_text, spoken, _ar_wid, spec=spec)" in probe
    assert "_act_repair.probe_call_for_promise(operator_text, spoken, spec)" in probe


def test_the_escalate_tool_says_a_torrent_is_not_an_errand():
    from nucleo.flash import router_catalog as rc
    desc = next(t for t in rc.TOOLS if t["function"]["name"] == "escalate_to_slowbrain")["function"]["description"]
    no = desc.split("NO:")[1]
    assert "TORRENTS" in no and "archivos:torrent_search" in no


def test_the_pass_sees_the_card_so_a_relative_order_can_become_a_call(client, monkeypatch):
    """V2-773 audit (demo, C4): «Move it 30 minutes later» → the turn said «It's now at 2:00 PM, running until
    2:45» with NO call. The main turn had the agenda digest (13:30–14:15) and computed the hour; this pass had
    only his words, so it could not, and returned None in silence. Now it reads the same card."""
    from nucleo.flash import widget_read
    monkeypatch.setattr(widget_read, "read", lambda wid: "citas próximas (1):\n  · 2026-09-27 13:30 «Catch up with Ethan»")
    seen = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: seen.append((a, k)))
    _Client.answer = [("widget_data", {"widget_id": "agenda", "action": "move_meeting",
                                       "payload": {"title": "Catch up with Ethan", "newTime": "14:00"}})]
    got = _run("Move it 30 minutes later.", "It's now at 2:00 PM, running until 2:45.", "agenda")
    assert got == {"widget_id": "agenda", "action": "move_meeting",
                   "payload": {"title": "Catch up with Ethan", "newTime": "14:00"}}
    sys_prompt = _Client.calls[-1]["messages"][0]["content"]
    assert "13:30 «Catch up with Ethan»" in sys_prompt, "the card's own rows ride the pass"
    assert "AFIRMASTE" in sys_prompt, "a claim of completion is repaired like a promise"
    # …and a pass that gives no call SAYS so on the timeline
    _Client.answer = []
    assert _run("Move it 30 minutes later.", "Done.", "agenda") is None
    assert any("segunda pasada no dio llamada" in str(a) for a, k in seen), seen


def _run_cr(*a, **k):
    return asyncio.run(act_repair.call_or_read_for_commission(*a, **k))


def test_a_commission_that_names_a_card_is_read_or_called_before_it_costs_a_worker(client, monkeypatch):
    """V2-773 final pass (C1): «Find me a free 45-minute slot tomorrow afternoon» went to a Brain Worker while
    the agenda — named by the catalogue verdict — held the whole answer. One pass with the card in front."""
    from nucleo.flash import widget_read
    monkeypatch.setattr(widget_read, "read", lambda wid: "citas próximas (3): …")
    _Client.answer = [("read_widget", {"widget_id": "agenda", "question": "What is free on 2026-09-27 between 12:00 and 18:00?"})]
    got = _run_cr("Find me a free 45-minute slot tomorrow afternoon to talk with Ethan.", "Find a free slot…", "agenda")
    assert got == {"kind": "read", "widget_id": "agenda", "question": "What is free on 2026-09-27 between 12:00 and 18:00?"}
    offered = [t["function"]["name"] for t in _Client.calls[-1]["tools"]]
    assert offered == ["widget_data", "read_widget"], offered
    assert "citas próximas (3)" in _Client.calls[-1]["messages"][0]["content"], "the card rides the pass"
    _Client.answer = [("widget_data", {"widget_id": "agenda", "action": "add_meeting", "payload": {"title": "x", "date": "2026-09-27"}})]
    got = _run_cr("Put a meeting tomorrow", "…", "agenda")
    assert got and got["kind"] == "call" and got["action"] == "add_meeting"
    _Client.answer = []
    assert _run_cr("Book me a table for two", "book a table", "agenda") is None, "nothing called → the worker keeps the errand"
    _Client.answer = [("read_widget", {"widget_id": "contactos", "question": "?"})]
    assert _run_cr("x", "x", "agenda") is None, "another card's call is not this card's answer"
    assert widget_read.can_answer("agenda") and not widget_read.can_answer("no-such-widget")
