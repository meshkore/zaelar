"""full20 E3 (demo pass 2026-09-28): «send the invoice to quinn, tell him we're already trying inworld and he should
book it» over the open Inworld invoice — the model's only call was `open` (what was already on screen), the verdict
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
    import nucleo.llm.fast_client as fc
    holder = {}

    def use(calls):
        holder["m"] = _Model(calls)
        monkeypatch.setattr(fc, "FastClient", lambda: holder["m"])
        return holder["m"]
    return use


def _run(**kw):
    return asyncio.run(act_repair.call_for_repeated_view("send the invoice to quinn", "mensajeria", "open",
                                                         "forward", **kw))


def test_the_verdicts_call_is_taken(model):
    m = model([("widget_data", {"widget_id": "mensajeria", "action": "forward",
                                "payload": {"contact": "Quinn", "text": "We're trying Inworld — book it."}})])
    got = _run()
    assert got == {"widget_id": "mensajeria", "action": "forward",
                   "payload": {"contact": "Quinn", "text": "We're trying Inworld — book it."}}
    assert "`forward`" in m.seen[0][0]["content"] and "`open`" in m.seen[0][0]["content"]


def test_any_other_call_is_not_taken(model):
    model([("widget_data", {"widget_id": "mensajeria", "action": "reply", "payload": {"text": "hi"}})])
    assert _run() is None
    model([])
    assert _run() is None


def _voice_turn(phrase: str, open_ids, brief: dict, tools: list):
    """One turn through the voice turn itself (the bank harness: the real `run_turn`, a recorded model, the recorded
    brief, every consequence door dry). The second passes are spied on by the `repairs` fixture."""
    from tests.brain import harness as H
    case = {"id": "repair-pass", "lang": "en", "phrase": phrase, "source": "node 2.121",
            "screen": {"open": list(open_ids)}, "model": {"say": "", "tools": tools}, "expect": "talk", "brief": brief}
    try:
        out = H.run_case(case)
    finally:
        from nucleo import canvas_closes, canvas_focus, done_ops
        from nucleo.flash import bulk_close, canvas_license
        canvas_focus._reset()
        done_ops.reset()
        bulk_close.reset()
        canvas_closes._reset_for_tests()
        canvas_license._RECENT_CLOSES.clear()
    assert not out.error, out.error
    return out


@pytest.fixture
def repairs(monkeypatch):
    """The second passes the turn asks for, recorded (each answers nothing, as the bank's model does)."""
    seen = {"repeated": [], "after_read": [], "after_lookup": []}

    async def repeated(operator_text, widget_id, repeated_action, verdict, *a, **k):
        seen["repeated"].append((widget_id, repeated_action, verdict))

    async def after_read(operator_text, read_widget, widget_id, *a, **k):
        seen["after_read"].append((read_widget, widget_id))
    real_after = act_repair.after_a_read

    async def after_lookup(brief, operator_text, read_widget, *a, **k):
        seen["after_lookup"].append(read_widget)
        return await real_after(brief, operator_text, read_widget, *a, **k)
    monkeypatch.setattr(act_repair, "call_for_repeated_view", repeated)
    monkeypatch.setattr(act_repair, "call_after_read", after_read)
    monkeypatch.setattr(act_repair, "after_a_read", after_lookup)
    return seen


#: full37 E2 / full26 E2: «open it» → the model searched the archive again, the verdict read `mensajeria:open`.
_LENS = ("open it", ["mensajeria"],
         {"screen_action": ["mensajeria:open", 0.87], "wants_words": ["act", 0.9], "request_type": ["order", 0.9]},
         [{"name": "widget_data", "args": {"widget_id": "mensajeria", "action": "search_archive",
                                           "payload": {"query": "inworld"}}}])


def test_the_voice_schedules_it_for_a_repeated_view_or_a_lens_over_an_act(repairs):
    """…and for a lens the verdict overrules but cannot complete alone (full37 E2: «open it» → the model searched
    the archive, the verdict read `mensajeria:open` 0.85, and `open` needs the name only a model can write)."""
    _voice_turn(*_LENS)
    assert repairs["repeated"] == [("mensajeria", "search_archive", "open")], repairs


def test_the_disarm_a_lens_that_never_yields_schedules_no_pass(repairs, monkeypatch):
    from nucleo.flash import data_ops
    monkeypatch.setattr(data_ops, "a_view_where_the_verdict_acts", lambda *a, **k: False)
    assert not data_ops.a_view_where_the_verdict_acts("mensajeria", "search_archive", "open", "act"), "landed"
    _voice_turn(*_LENS)
    assert repairs["repeated"] == [], "the lens's verdict is never asked for — the turn ends on the model's search"


def test_a_read_for_an_order_on_another_card_carries_the_order_out(model, monkeypatch):
    """full20 C5: «send rowan a telegram with the new time» read the agenda for the time, and the read's words-only
    pass said «I can't send a Telegram — I don't have any messaging tool»."""
    from nucleo.flash import widget_read
    monkeypatch.setattr(widget_read, "read", lambda wid, *a, **k: "Catch up with Rowan · 16:30" if wid == "agenda" else "")
    m = model([("widget_data", {"widget_id": "mensajeria", "action": "send_to",
                                "payload": {"contact": "Rowan", "text": "Moved to 16:30"}})])
    # The verdict of that turn put the order on the messaging card; a send the pass composes needs it (demo sandbox
    # 2026-10-28: the same pass mailed Quinn over a «save my contacts» order — `send_backed_by_verdict`).
    import threading
    from nucleo.turn import brief as _tb
    ev = threading.Event(); ev.set()
    brief = {"event": ev, "turn_id": "t", "open_ids": [], "result": {_tb.CATALOG_KEY: {"choice": "mensajeria", "confidence": 0.95}}}
    got = asyncio.run(act_repair.call_after_read("send rowan a telegram with the new time", "agenda", "mensajeria", brief=brief))
    assert got == {"widget_id": "mensajeria", "action": "send_to", "payload": {"contact": "Rowan", "text": "Moved to 16:30"}}
    assert "16:30" in m.seen[0][0]["content"], "what was read travels to the pass"


def test_the_order_card_is_the_other_card_his_words_name(monkeypatch):
    from nucleo.flash import direct_action as da
    from nucleo.turn import brief as tb
    monkeypatch.setattr(tb, "read", lambda b, k, d="", min_confidence=0.0: ("order", {"used": True}) if k == tb.REQUEST_KEY else (d, None))
    assert da.order_card_after_read({"x": 1}, "send rowan a telegram with the new time", "agenda") == "mensajeria"
    assert da.order_card_after_read({"x": 1}, "what time is it tomorrow in my calendar", "agenda") == ""


#: full20 C5, the time on the agenda and the order on the messages — read by an ORDER brief.
_ORDER_ELSEWHERE = "send rowan a telegram with the new time"
_ORDER = {"request_type": ["order", 0.95]}


def test_the_voice_read_path_uses_it(repairs):
    """V2-781 T518: one door for both channels — the voice read lane hands the read to `after_a_read`, which carries
    the order out on the card his words name (`order_card_after_read` → `call_after_read`)."""
    _voice_turn(_ORDER_ELSEWHERE, ["agenda", "mensajeria"], _ORDER,
                [{"name": "read_widget", "args": {"widget_id": "agenda"}}])
    assert repairs["after_lookup"] == ["agenda"], repairs
    assert repairs["after_read"] == [("agenda", "mensajeria")], repairs


def test_an_order_on_a_card_the_turn_never_touched_is_carried_out(repairs):
    """full23 C5: «send rowan a telegram with the new time» re-wrote the meeting on the agenda and the reply said «he's
    getting the update now» — nothing was sent. The order's card, untouched by the turn's ops, gets its call."""
    _voice_turn(_ORDER_ELSEWHERE, ["agenda", "mensajeria"], _ORDER,
                [{"name": "widget_data", "args": {"widget_id": "agenda", "action": "show_day",
                                                  "payload": {"date": "tomorrow"}}}])
    assert repairs["after_read"] == [("agenda", "mensajeria")], repairs


def test_the_disarm_no_order_card_after_a_read_carries_nothing_out(repairs, monkeypatch):
    """`order_card_after_read` answering "" (the reader of his words off): neither the read lane nor the op lane
    reaches the second pass — the order on the messages is dropped, as in full20/full23 C5."""
    from nucleo.flash import direct_action as da
    monkeypatch.setattr(da, "order_card_after_read", lambda *a, **k: "")
    assert da.order_card_after_read({}, _ORDER_ELSEWHERE, "agenda") == "", "landed"
    _voice_turn(_ORDER_ELSEWHERE, ["agenda", "mensajeria"], _ORDER,
                [{"name": "read_widget", "args": {"widget_id": "agenda"}}])
    _voice_turn(_ORDER_ELSEWHERE, ["agenda", "mensajeria"], _ORDER,
                [{"name": "widget_data", "args": {"widget_id": "agenda", "action": "show_day",
                                                  "payload": {"date": "tomorrow"}}}])
    assert repairs["after_read"] == [], repairs


def test_an_answering_lens_yields_to_a_verdict_that_changes_the_screen():
    """full26 E2: «open it» → the model searched the archive again («nothing matching»), the verdict read
    `mensajeria:open` at 0.87. Both are lenses; the one that only answers in words yields when the turn wants an act."""
    from nucleo.flash import data_ops
    assert data_ops.a_view_where_the_verdict_acts("mensajeria", "search_archive", "open", "act")
    assert not data_ops.a_view_where_the_verdict_acts("mensajeria", "search_archive", "open", "tell")
    assert not data_ops.a_view_where_the_verdict_acts("mensajeria", "show_view", "open", "act"), "two plain lenses: the model's"


def test_a_lens_that_does_not_answer_yields_to_the_one_that_does_when_he_asks():
    """Pass 119, C2: «find me a free 45 minutes tomorrow afternoon…» — the verdict read `agenda:find_free` (an
    `output.answer` lens), the model called `show_day`, a plain lens that answers nothing, and the slot was never
    found: «book it» then had no time and the whole C block fell. When the turn wants WORDS, the lens that answers is
    what he asked; the mirror of the clause above."""
    from nucleo.flash import data_ops
    assert data_ops.a_view_where_the_verdict_acts("agenda", "show_day", "find_free", "tell")
    assert not data_ops.a_view_where_the_verdict_acts("agenda", "find_free", "show_day", "tell"), "the answer stays"
    assert not data_ops.a_view_where_the_verdict_acts("agenda", "show_day", "show_week", "tell"), "two plain lenses"
