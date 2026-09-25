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
