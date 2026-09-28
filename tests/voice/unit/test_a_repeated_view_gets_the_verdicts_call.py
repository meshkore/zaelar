"""full20 E3 (demo pass 2026-09-28): «send the invoice to andrew, tell him we're already trying inworld and he should
book it» over the open Inworld receipt — the model's only call was `open` (what was already on screen), the verdict
read `mensajeria:forward`. A forward needs a note only a model can write, so the verdict could not complete it and
the turn did nothing. One repair pass asks for the verdict's call."""
import asyncio
import pathlib

import pytest

from nucleo.flash import act_repair

ENGINE = pathlib.Path(__file__).resolve().parents[3]


class _Model:
    def __init__(self, calls):
        self.calls, self.seen = calls, []

    async def complete(self, messages, **kw):
        self.seen.append(messages)
        for name, args in self.calls:
            kw["on_tool_call"](name, args)


@pytest.fixture
def model(monkeypatch):
    import nucleo.flash.fast_client as fc
    holder = {}

    def use(calls):
        holder["m"] = _Model(calls)
        monkeypatch.setattr(fc, "FastClient", lambda: holder["m"])
        return holder["m"]
    return use


def _run(**kw):
    return asyncio.run(act_repair.call_for_repeated_view("send the invoice to andrew", "mensajeria", "open",
                                                         "forward", **kw))


def test_the_verdicts_call_is_taken(model):
    m = model([("widget_data", {"widget_id": "mensajeria", "action": "forward",
                                "payload": {"contact": "Andrew", "text": "We're trying Inworld — book it."}})])
    got = _run()
    assert got == {"widget_id": "mensajeria", "action": "forward",
                   "payload": {"contact": "Andrew", "text": "We're trying Inworld — book it."}}
    assert "`forward`" in m.seen[0][0]["content"] and "`open`" in m.seen[0][0]["content"]


def test_any_other_call_is_not_taken(model):
    model([("widget_data", {"widget_id": "mensajeria", "action": "reply", "payload": {"text": "hi"}})])
    assert _run() is None
    model([])
    assert _run() is None


def test_the_voice_schedules_it_only_for_a_repeated_view():
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    assert "if _data_ops.repeats_last_view(brain._last_dataop, _cd[\"card\"], action_name, res.payload):" in src
    assert "_repeat_repair[\"v\"] = (_cd[\"card\"], action_name, _dis)" in src
    assert "call_for_repeated_view(_op_text, _rv_card, _rv_seen, _rv_act" in src


def test_a_read_for_an_order_on_another_card_carries_the_order_out(model, monkeypatch):
    """full20 C5: «send ethan a telegram with the new time» read the agenda for the time, and the read's words-only
    pass said «I can't send a Telegram — I don't have any messaging tool»."""
    from nucleo.flash import widget_read
    monkeypatch.setattr(widget_read, "read", lambda wid, *a, **k: "Catch up with Ethan · 16:30" if wid == "agenda" else "")
    m = model([("widget_data", {"widget_id": "mensajeria", "action": "send_to",
                                "payload": {"contact": "Ethan", "text": "Moved to 16:30"}})])
    got = asyncio.run(act_repair.call_after_read("send ethan a telegram with the new time", "agenda", "mensajeria"))
    assert got == {"widget_id": "mensajeria", "action": "send_to", "payload": {"contact": "Ethan", "text": "Moved to 16:30"}}
    assert "16:30" in m.seen[0][0]["content"], "what was read travels to the pass"


def test_the_order_card_is_the_other_card_his_words_name(monkeypatch):
    from nucleo.flash import direct_action as da
    from nucleo.flash import turn_brief as tb
    monkeypatch.setattr(tb, "read", lambda b, k, d="", min_confidence=0.0: ("order", {"used": True}) if k == tb.REQUEST_KEY else (d, None))
    assert da.order_card_after_read({"x": 1}, "send ethan a telegram with the new time", "agenda") == "mensajeria"
    assert da.order_card_after_read({"x": 1}, "what time is it tomorrow in my calendar", "agenda") == ""


def test_the_voice_read_path_uses_it():
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    assert "_order_card = _direct_action.order_card_after_read(_brief, _op_text, _rw)" in src
    assert "call_after_read(_op_text, _rw, _order_card" in src
