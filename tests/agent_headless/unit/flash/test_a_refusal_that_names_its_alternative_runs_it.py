"""Node 2.596 — a card refusal that NAMES its alternatives (`redirect`) lets one same-turn pass run one of them.

`find-videos-on-a-topic-no-ai-slop` (ES, 2026-10-14): «Ponme el de Iván, el de José Manuel y el de Jaén» reached
`youtube:clear_list` over an empty queue. The refusal correction may only re-issue the SAME action, so even a true
refusal left him with nothing added. `nucleo/flash/refusal_redirect.py` offers the model ONLY the actions the card
named; anything else is dropped, and the seam both channels share (`data_ops.corrected_retry`) returns the action that
ran as a third element, which both callers unpack.

Disarm: `refusal_redirect.offered` returning [] → the first test goes red; an alternative outside `redirect` accepted
→ the second goes red; either caller unpacking two elements → the wiring test goes red.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import data_ops

REFUSED = {"ok": False, "error": "queue_empty", "redirect": ["add_results", "play_result"],
           "message": "La cola ya está vacía: no había nada que quitar."}
SAID = "Ponme el de Iván, el de José Manuel y el de Jaén"


class _Client:
    calls: list = []
    answer: list = []

    def __init__(self, *a, **k):
        pass

    async def complete(self, messages, *, spec=None, max_tokens=None, tools=None, on_tool_call=None,
                       no_thinking=False):
        _Client.calls.append({"messages": messages})
        for name, args in _Client.answer:
            on_tool_call(name, args)
        return ""


@pytest.fixture
def client(monkeypatch):
    from nucleo.flash import widget_read
    from nucleo.llm import fast_client
    monkeypatch.setattr(fast_client, "FastClient", _Client)
    monkeypatch.setattr(widget_read, "read", lambda wid: "1. Jaén · 3. José Manuel · 5. Iván\nCOLA: vacía")
    _Client.calls, _Client.answer = [], []
    return _Client


def _retry(res=REFUSED):
    ran = []

    async def _dispatch(w, a, p):
        ran.append((w, a, p))
        return {"ok": True, "added": ["x"]}
    return asyncio.run(data_ops.corrected_retry("youtube", "clear_list", {}, res, SAID, _dispatch)), ran


def test_the_alternative_his_words_ask_for_runs_and_names_itself(client):
    client.answer = [("widget_data", {"widget_id": "youtube", "action": "add_results", "payload": {"items": "5,3,1"}})]
    got, ran = _retry()
    assert ran == [("youtube", "add_results", {"items": "5,3,1"})]
    assert got == ({"items": "5,3,1"}, {"ok": True, "added": ["x"]}, "add_results")
    sys = client.calls[0]["messages"][0]["content"]
    assert "add_results" in sys and "La cola ya está vacía" in sys and "clear_search" not in sys, \
        "the pass sees the refusal and ONLY the actions the card named"


def test_an_action_the_card_did_not_name_never_runs(client, monkeypatch):
    client.answer = [("widget_data", {"widget_id": "youtube", "action": "clear_search", "payload": {}}),
                     ("widget_data", {"widget_id": "musica", "action": "add_results", "payload": {"items": "1"}})]
    from nucleo.flash import act_repair
    monkeypatch.setattr(act_repair, "call_for_refusal", lambda *a, **k: asyncio.sleep(0, None))
    got, ran = _retry()
    assert ran == [] and got is None


def test_a_refusal_without_redirect_keeps_todays_correction(client, monkeypatch):
    seen = []

    async def _fix(*a, **k):
        seen.append(a[2])
        return None
    from nucleo.flash import act_repair
    monkeypatch.setattr(act_repair, "call_for_refusal", _fix)
    got, ran = _retry({"ok": False, "error": "item_not_found", "message": "No encuentro ese vídeo en la lista."})
    assert got is None and seen == ["clear_list"] and not client.calls
