"""Every second pass asks the ONE reader of «canvas gesture or inner op» (demo sandbox 2026-10-29, C6).

«close the calendar and the messages» read canvas=close 1.00 and `agenda:close_meeting` 0.50. The first pass refused
the inner op (`verdict_card.canvas_yields`), as M4/R4 had taught it. Then the promise repair's refused-verdict pass
asked the model for `close_meeting` (it closes a meeting's DETAIL, not the card) and ran it. «Calendar's closed» was
said over a card that stayed open. Now every second pass calls `verdict_card.inner_op_may_run`, the function the first
pass calls (through `act_repair.canvas_holds_the_turn`), before it asks the model. An inner order as sure as the
gesture still runs.

The names question is the other half of C6: a single choice could not say «a card on screen AND something that is
not», so a mixed sentence read `elsewhere` and vetoed the model's own close of the card on screen. Its criterion now
declares the mixed case (`brief_screen.names_question`).

Disarm: make `act_repair.canvas_holds_the_turn` answer False (a repair that bypasses the reader). The door tests and
the real-turn tests go red with `data-op agenda:close_meeting`, the sandbox's own event.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from nucleo.flash import act_repair, verdict_card
from nucleo.turn import brief as tb, brief_screen

C6 = {"en": "close the calendar and the messages", "es": "cierra la agenda y los mensajes"}
INNER = {"en": "close that meeting", "es": "cierra esa reunión"}


def _brief(open_ids, **answers) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": list(open_ids),
            "result": {k: {"choice": c, "confidence": p, "probs": {c: p}} for k, (c, p) in answers.items()}}


def _close(action: str, conf: float, card: str = "agenda", open_ids=("agenda", "results")) -> dict:
    return _brief(open_ids, **{tb.CANVAS_KEY: ("close", 1.0), tb.TARGET_KEY: (f"{card}:{action}", conf),
                               tb.REQUEST_KEY: ("order", 0.9)})


class _Model:
    """The second pass's model: it always answers with the inner op, as the sandbox's did."""
    def __init__(self, card: str, action: str):
        self.card, self.action, self.asked = card, action, 0

    async def complete(self, messages, **kw):
        self.asked += 1
        kw["on_tool_call"]("widget_data", {"widget_id": self.card, "action": self.action, "payload": {}})
        return ""


@pytest.fixture
def model(monkeypatch):
    import nucleo.llm.fast_client as fc
    from nucleo.flash import widget_read
    monkeypatch.setattr(widget_read, "read", lambda wid: "")    # never the real card's data
    holder = {}

    def use(card, action):
        holder["m"] = _Model(card, action)
        monkeypatch.setattr(fc, "FastClient", lambda: holder["m"])
        return holder["m"]
    return use


# ── the reader ────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_reader_keeps_a_sure_close_over_an_unsure_inner_op(lang):
    assert verdict_card.inner_op_may_run(_close("close_meeting", 0.5), C6[lang], builds_payload=True) is False
    assert verdict_card.inner_op_may_run(_close("close_meeting", 0.97), INNER[lang], builds_payload=True) is True
    no_gesture = _brief(("agenda",), **{tb.TARGET_KEY: ("agenda:close_meeting", 0.5)})
    assert verdict_card.inner_op_may_run(no_gesture, INNER[lang]) is True


def test_a_write_the_close_verb_stands_for_is_left_to_the_pass_that_builds_its_payload():
    b = _close("cancel_meeting", 0.71)                          # «quita el piano entero»: a removal read as «close»
    assert verdict_card.inner_op_may_run(b, "quita el piano entero", builds_payload=True) is True
    assert verdict_card.inner_op_may_run(b, "quita el piano entero") is False
    assert verdict_card.canvas_yields(b) is False, "the bare data rung asks the same reader and guesses no payload"


# ── the second-pass doors ─────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_promise_repair_runs_no_inner_op_under_a_sure_close(model, lang):
    m = model("agenda", "close_meeting")
    got = asyncio.run(act_repair.call_for_promise_or_order(C6[lang], "Calendar's closed.", "agenda", "close_meeting",
                                                           brief=_close("close_meeting", 0.5)))
    assert got is None and m.asked == 0, (got, m.asked)


@pytest.mark.parametrize("lang,said", [("en", "close my mail"), ("es", "cierra el correo")])
def test_another_card_the_same(model, lang, said):
    """The messaging card declares a `close` view (back to the chat list): a sure canvas close is the CARD's."""
    m = model("mensajeria", "close")
    b = _close("close", 0.55, card="mensajeria", open_ids=("mensajeria",))
    got = asyncio.run(act_repair.call_for_promise_or_order(said, "Done.", "mensajeria", "close", brief=b))
    assert got is None and m.asked == 0


@pytest.mark.parametrize("lang", ["en", "es"])
def test_a_real_inner_op_still_runs(model, lang):
    m = model("agenda", "close_meeting")
    got = asyncio.run(act_repair.call_for_promise_or_order(INNER[lang], "Closed.", "agenda", "close_meeting",
                                                           brief=_close("close_meeting", 0.97)))
    assert got == {"widget_id": "agenda", "action": "close_meeting", "payload": {}} and m.asked == 1


def test_the_other_second_passes_ask_the_same_reader(model, monkeypatch):
    m = model("agenda", "close_meeting")
    b = _close("close_meeting", 0.5)
    monkeypatch.setattr(act_repair, "order_card_after_search", lambda brief, answer="": "agenda")
    runs = [act_repair.call_for_repeated_view(C6["en"], "agenda", "open_meeting", "close_meeting", brief=b),
            act_repair.call_after_read(C6["en"], "results", "agenda", brief=b),
            act_repair.call_after_search(C6["en"], "It is on Tuesday.", b)]
    assert [asyncio.run(r) for r in runs] == [None, None, None] and m.asked == 0


# ── the real turn (the bank's headless voice turn), with the sandbox's own verdicts ─────────────────────────────
def _turn(lang: str, names: tuple, tools: list, open_ids: list, phrase: str = ""):
    from tests.brain import harness
    case = {"id": f"c6-{lang}-{names[0]}", "lang": lang, "phrase": phrase or C6[lang], "source": "demo sandbox 2026-10-29 C6",
            "screen": {"open": open_ids}, "model": {"say": "Calendar's closed.", "tools": tools},
            "brief": {"canvas": ["close", 1.0], "screen_action": ["agenda:close_meeting", 0.5],
                      "names_a_card": list(names), "request_type": ["order", 0.9]},
            "expect": "close agenda", "forbid": ["data-op"]}
    return harness.run_case(case)


@pytest.fixture
def second_pass_answers_the_inner_op(monkeypatch):
    from tests.brain import harness

    async def complete(self, messages, spec=None, *a, **kw):
        harness.RecordedModel.consulted = True
        if kw.get("on_tool_call") and kw.get("tools"):
            kw["on_tool_call"]("widget_data", {"widget_id": "agenda", "action": "close_meeting", "payload": {}})
        return ""
    monkeypatch.setattr(harness.RecordedModel, "complete", complete)


_CLOSES = [{"name": "close_widget", "args": {"widget_id": "agenda"}},
           {"name": "close_widget", "args": {"widget_id": "mensajeria"}}]


@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_sandbox_turn_runs_no_inner_op(second_pass_answers_the_inner_op, lang):
    """The live verdicts: names_a_card=elsewhere 0.98. Since R4c the agenda his words name is on screen, so the
    verdict cannot veto its close (node 2.960): the card closes and no inner op runs."""
    out = _turn(lang, ("elsewhere", 0.98), _CLOSES, ["agenda", "results"])
    assert out.decision == "close agenda", (out.decision, out.also)
    assert not [d for d in out.all_decisions if d.startswith("data-op")], (out.decision, out.also)


@pytest.mark.parametrize("lang,said", [("en", "close it"), ("es", "ciérralo")])
def test_a_vetoed_close_reaches_the_repair_and_still_runs_no_inner_op(second_pass_answers_the_inner_op, lang, said):
    """A sure «elsewhere» over words that name no card vetoes the model's close; the repair is reached and asks the
    reader, which keeps the inner op out."""
    out = _turn(lang, ("elsewhere", 0.98), _CLOSES[:1], ["agenda", "results"], phrase=said)
    assert not [d for d in out.all_decisions if d.startswith("data-op")], (out.decision, out.also)
    assert any("canvas gesture owns the turn" in str(e.get("text")) for e in out.events)


@pytest.mark.parametrize("lang", ["en", "es"])
def test_with_the_card_on_screen_read_as_named_both_cards_close(second_pass_answers_the_inner_op, lang):
    """The names verdict the declared mixed criterion asks for: the model called nothing, both open cards close, and
    no inner op runs."""
    out = _turn(lang, ("on_screen", 0.95), [], ["agenda", "mensajeria"])
    assert out.decision == "close agenda" and "close mensajeria" in out.also, (out.decision, out.also)
    assert not [d for d in out.all_decisions if d.startswith("data-op")]


# ── the names question ────────────────────────────────────────────────────────────────────────────────────────
def test_the_names_question_declares_a_sentence_that_names_a_card_and_something_else():
    q = tb.names_question(["agenda", "results"])
    on, elsewhere = q["criteria"]["on_screen"], q["criteria"][brief_screen.NAMES_ELSEWHERE]
    assert "at least one" in on and "ALSO" in on, on
    assert elsewhere.startswith("NOTHING he names"), elsewhere


@pytest.mark.parametrize("names,closed", [(("on_screen", 0.95), True), (("elsewhere", 0.95), False)])
def test_the_veto_takes_only_a_close_where_nothing_named_is_on_screen(monkeypatch, names, closed):
    from nucleo.flash import show_target
    monkeypatch.setattr(tb, "of_this_turn", lambda: _brief(("agenda",), **{tb.NAMES_KEY: names}))
    monkeypatch.setattr(show_target, "close_target", lambda wid: wid)
    tags = []
    got = show_target.close_dispatch({"widget_id": "agenda"}, lambda *a, **k: tags.append(a), lambda *a, **k: None,
                                     text=C6["en"])
    assert bool(got) is closed and bool(tags) is closed
