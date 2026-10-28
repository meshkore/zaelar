"""An ORDER beside a searched fact is carried out (V2-781 T515, 2026-10-03).

Measured on the pair `find-a-future-release-and-remind-me__us`: «Can you set a reminder for the premiere day?» — the
model searched the date again, and the search's answer pass, which has no tools, said «I can't actually set
reminders myself, but I've got the date for you: … October 30, 2026». The brief had read `request_type=order`,
`wants_words=act`, `catalog_widget=agenda` (0.91). `scheduled_jobs` stayed empty. The sibling of
`call_after_read` (full20 C5) now runs after a search too: one bounded pass on the card the brief names.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import act_repair

DENIAL = ("I can't actually set reminders myself, but I've got the date for you: Dexter: Resurrection season 2 "
          "premieres Friday, October 30, 2026 on Paramount+. Anything else you need?")
CALL = ("widget_data", {"widget_id": "agenda", "action": "add_meeting",
                        "payload": {"title": "Dexter: Resurrection S2 premiere", "date": "2026-10-30"}})


class _Model:
    def __init__(self, calls):
        self.calls, self.seen = calls, []

    async def complete(self, messages, **kw):
        self.seen.append(messages)
        for name, args in self.calls:
            kw["on_tool_call"](name, args)


@pytest.fixture
def brief(monkeypatch):
    """A brief that reads like the measured one; `set(**verdicts)` changes what it says."""
    from nucleo.flash import build_decision as bd, turn_brief as tb
    said = {tb.REQUEST_KEY: "order", tb.WORDS_KEY: "act"}
    monkeypatch.setattr(tb, "read", lambda b, k, d="", min_confidence=None: (said[k], {"used": True})
                        if k in said else (d, None))
    monkeypatch.setattr(bd, "named_card", lambda b: "agenda")
    return said


@pytest.fixture
def model(monkeypatch):
    import nucleo.flash.fast_client as fc
    from nucleo.flash import widget_read
    monkeypatch.setattr(widget_read, "read", lambda wid, *a, **k: "")
    holder = {}

    def use(calls):
        holder["m"] = _Model(calls)
        monkeypatch.setattr(fc, "FastClient", lambda: holder["m"])
        return holder["m"]
    return use


def test_the_order_card_needs_a_sure_order_or_a_refused_act(brief):
    from nucleo.flash import turn_brief as tb
    assert act_repair.order_card_after_search({"x": 1}, "It premieres October 30.") == "agenda"
    brief[tb.WORDS_KEY] = "tell"                    # the ES twin read `tell` on the same order
    assert act_repair.order_card_after_search({"x": 1}, "Se estrena el 30 de octubre.") == "agenda"
    brief[tb.REQUEST_KEY] = "question"
    assert act_repair.order_card_after_search({"x": 1}, "Se estrena el 30 de octubre.") == "", \
        "a question answered with its fact never reaches here"
    assert act_repair.order_card_after_search(
        {"x": 1}, "Se estrena el 30 de octubre. Eso sí, avisarte no puedo hacerlo por mi cuenta.") == "agenda"


def test_the_pass_takes_the_call_with_what_was_found(brief, model):
    m = model([CALL])
    got = asyncio.run(act_repair.call_after_search("Can you set a reminder for the premiere day?", DENIAL, {"x": 1}))
    assert got == {"widget_id": "agenda", "action": "add_meeting", "payload": CALL[1]["payload"]}
    assert "October 30, 2026" in m.seen[0][0]["content"], "what the search found travels to the pass"


def test_no_call_or_another_card_is_nothing(brief, model):
    model([])
    assert asyncio.run(act_repair.call_after_search("set a reminder", DENIAL, {"x": 1})) is None
    model([("widget_data", {"widget_id": "mensajeria", "action": "send_to", "payload": {}})])
    assert asyncio.run(act_repair.call_after_search("set a reminder", DENIAL, {"x": 1})) is None


def test_the_voice_runs_it_and_says_what_happened_after_the_refusal(brief, model):
    model([CALL])
    applied, sent, acted, done = [], [], {}, {"v": False}
    ran = asyncio.run(act_repair.voice_after_search(
        "Can you set a reminder for the premiere day?", DENIAL, {"x": 1}, None, window=[],
        apply=lambda *a: applied.append(a), send=sent.append, emit=lambda *a, **k: None, acted=acted, done=done))
    assert ran and applied == [("agenda", "add_meeting", CALL[1]["payload"])]
    assert acted.get("widget") is True and done["v"] is True
    assert sent, "a refusal that already streamed is followed by what happened"
