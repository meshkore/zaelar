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


def test_the_voice_schedules_it_for_a_repeated_view_or_a_lens_over_an_act():
    """…and for a lens the verdict overrules but cannot complete alone (full37 E2: «open it» → the model searched
    the archive, the verdict read `mensajeria:open` 0.85, and `open` needs the name only a model can write)."""
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    i = src.index('_repeat_repair["v"] = (_cd["card"], action_name, _dis)')
    head = src[i - 400:i]
    assert "repeats_last_view(brain._last_dataop, _cd[\"card\"], action_name, res.payload)" in head
    assert "or _data_ops.a_view_where_the_verdict_acts(_cd[\"card\"], action_name, _dis, _vw_words)" in head
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


def test_an_order_on_a_card_the_turn_never_touched_is_carried_out():
    """full23 C5: «send ethan a telegram with the new time» re-wrote the meeting on the agenda and the reply said «he's
    getting the update now» — nothing was sent. The order's card, untouched by the turn's ops, gets its call."""
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    assert "_missed = _direct_action.order_card_after_read(_brief, _op_text, next(iter(_ops_cards)))" in src
    assert "if _missed and _missed not in _ops_cards:" in src
    assert "call_after_read(_op_text, next(iter(_ops_cards)), _missed" in src


def test_an_answering_lens_yields_to_a_verdict_that_changes_the_screen():
    """full26 E2: «open it» → the model searched the archive again («nothing matching»), the verdict read
    `mensajeria:open` at 0.87. Both are lenses; the one that only answers in words yields when the turn wants an act."""
    from nucleo.flash import data_ops
    assert data_ops.a_view_where_the_verdict_acts("mensajeria", "search_archive", "open", "act")
    assert not data_ops.a_view_where_the_verdict_acts("mensajeria", "search_archive", "open", "tell")
    assert not data_ops.a_view_where_the_verdict_acts("mensajeria", "show_view", "open", "act"), "two plain lenses: the model's"
