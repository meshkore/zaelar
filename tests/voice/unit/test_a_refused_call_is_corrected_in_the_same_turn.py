"""Demo pass 2026-09-28 — a data-op the card REFUSED gets one corrected re-call while the turn is still his.

S3: «open the one that's the best deal» reached `results:detail` with nothing the sheet could match (its badge
says «Best value»); C4: «move it half an hour later» reached `move_meeting` with field names it did not read. Both
refusals were true and both went to a note for the NEXT turn: silence now, an apology stapled to an unrelated
answer later — and in C4 the next order («send Ethan a telegram») was spent re-sending the move.

The bounds are the safety of a second model call: the SAME action on the SAME card (so the same gate the refused
call already passed), a DIFFERENT payload, nothing when the model still cannot tell — and both channels share it.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import act_repair, data_ops


class _Client:
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


REFUSED = {"ok": False, "error": "no encuentro ese resultado en la hoja (pasa el title o index 1-based)"}


def _retry(res, answer, client, dispatched):
    client.answer = answer

    async def _dispatch(w, a, p):
        dispatched.append((w, a, p))
        return {"ok": True}
    return asyncio.run(data_ops.corrected_retry("results::94c49b-3", "detail", {}, res,
                                                "open the one that's the best deal", _dispatch))


def test_the_refusal_and_the_card_reach_the_model_and_the_corrected_call_runs(client):
    ran = []
    got = _retry(REFUSED, [("widget_data", {"widget_id": "results", "action": "detail",
                                             "payload": {"index": 1}})], client, ran)
    assert got == ({"index": 1}, {"ok": True})
    assert ran == [("results::94c49b-3", "detail", {"index": 1})], "the corrected call runs on the SAME card"
    sys = client.calls[0]["messages"][0]["content"]
    assert "no encuentro ese resultado" in sys, "the model must see WHY the card refused"
    assert [t["function"]["name"] for t in client.calls[0]["tools"]] == ["widget_data"]


@pytest.mark.parametrize("answer", [
    [],                                                                                       # still cannot tell
    [("widget_data", {"widget_id": "results", "action": "clear", "payload": {"x": 1}})],      # another action
    [("widget_data", {"widget_id": "agenda", "action": "detail", "payload": {"index": 1}})],  # another card
    [("widget_data", {"widget_id": "results", "action": "detail", "payload": {}})],           # the same call
])
def test_anything_but_a_different_payload_for_the_same_call_is_nothing(client, answer):
    ran = []
    assert _retry(REFUSED, answer, client, ran) is None
    assert ran == []


def test_a_success_or_a_pool_timeout_never_costs_a_pass(client):
    ran = []
    assert _retry({"ok": True}, [], client, ran) is None
    assert _retry({"error": "widget 'results' timed out after 8s"}, [], client, ran) is None
    assert client.calls == [], "no model call on a turn that did not fail"


def test_both_channels_share_the_seam():
    """V2-252: a rule installed in one of two branches is half a fix."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    assert "corrected_retry(" in (root / "nucleo/flash/data_ops.py").read_text("utf-8").split(
        "async def dispatch_and_report(")[1], "the voice path lost the retry"
    assert "_rg.corrected_retry(" in (root / "nucleo/flash/widget_data_turn.py").read_text("utf-8"), \
        "the text channel lost the retry"


def test_the_pass_refuses_to_run_without_his_words(client):
    assert asyncio.run(act_repair.call_for_refusal("", "results", "detail", {}, "x")) is None
    assert client.calls == []
