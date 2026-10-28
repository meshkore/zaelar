"""What the agent said on its own enters the brain's window at its next prompt (node 3.110).

Manual session 7850de3f (2026-09-30): the INIT list finished in three minutes and said «I've finished your list»
out loud through `proactive.notify`, which never wrote the brain's own window. An hour later the window still
ended in «I'm on them and I'll let you know when I'm done», and the model said «it's all still running in the
background», then «I'm kicking it off now properly» with nothing behind it.
"""
import asyncio

import pytest

from nucleo.flash import dialog
from voice import proactive


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    dialog._SPOKEN.clear()
    yield
    dialog._SPOKEN.clear()


def test_a_spoken_delivery_is_our_next_turn_in_the_window(monkeypatch):
    said = []
    monkeypatch.setattr(proactive, "_speaker", lambda text: said.append(text))
    monkeypatch.setattr(proactive, "_wait_turn", lambda ticket, wait: True)

    async def _quiet(left):
        return True
    monkeypatch.setattr(proactive, "_wait_for_quiet", _quiet)
    assert asyncio.run(proactive.notify("lista", "I've finished your list: 26 of 26 done.", opens_window=False))
    window = [{"role": "user", "content": "DEMO INITIALIZATION …"},
              {"role": "assistant", "content": "Got it — I'm on them and I'll let you know when I'm done."}]
    dialog.drain_spoken(window)
    assert window[-1] == {"role": "assistant", "content": "I've finished your list: 26 of 26 done."}
    dialog.drain_spoken(window)
    assert len(window) == 3, "drained once, never twice"


def test_nothing_said_adds_nothing():
    window = []
    dialog.drain_spoken(window)
    assert window == []


# ── V2-778 F2-21: both channels hear it (the operator's decision, 2026-10-02) ──────────────────────────────

def test_the_voice_and_a_chat_session_each_get_the_line_once():
    """What was said out loud belongs to the conversation on BOTH channels: draining it into one must not take
    it from the other (before, the first consumer emptied the list)."""
    chat = []
    dialog.drain_spoken(chat, channel="text:a")          # the chat session exists before the line is said
    dialog.note_spoken("I've finished your list: 26 of 26 done.")
    voice = []
    dialog.drain_spoken(voice)
    dialog.drain_spoken(chat, channel="text:a")
    assert voice[-1]["content"] == chat[-1]["content"] == "I've finished your list: 26 of 26 done."
    dialog.drain_spoken(voice)
    dialog.drain_spoken(chat, channel="text:a")
    assert len(voice) == 1 and len(chat) == 1, "each channel once, never twice"


def test_a_chat_session_opened_after_the_line_does_not_inherit_it():
    dialog.note_spoken("Your errand is done.")
    late = []
    dialog.drain_spoken(late, channel="text:late")
    assert late == [], "a line said before this conversation existed is not part of it"


# ── demo pass 135: a report that crossed his exchange about another card goes ahead of it ──────────────────

def _his_turn(card: str = "") -> None:
    from nucleo import canvas_focus as cf
    cf.note("transcript", "said", role="user")
    if card:
        cf.note("widget", "show", extra={"id": card, "src": "flash"})


def test_a_report_on_another_card_that_crossed_his_order_goes_ahead_of_it():
    """«show me a red ferari f40» → «I'll pull up the F40» → the monitors' first rows → «cool, show me a few more
    of those»: with the report last, «those» became the monitors (live bench 1/5 → 5/5 with it ahead)."""
    from nucleo import canvas_focus as cf
    cf._reset()
    try:
        _his_turn("imagenes")
        window = [{"role": "user", "content": "show me a red ferari f40"},
                  {"role": "assistant", "content": "I'll pull up the F40 for you now."}]
        dialog.drain_spoken(window, channel="text:cross")   # the conversation exists before the line is said
        dialog.note_spoken("The first monitors are in.", about="results::t1")
        _his_turn()                                       # his next words arrive; the prompt drains
        dialog.drain_spoken(window, channel="text:cross")
        assert [m["content"] for m in window] == ["The first monitors are in.", "show me a red ferari f40",
                                                  "I'll pull up the F40 for you now."]
    finally:
        cf._reset()


def test_a_report_on_the_card_he_was_on_or_on_no_card_stays_last():
    from nucleo import canvas_focus as cf
    for card, about in (("results::t1", "results::t1"), ("imagenes", "")):
        cf._reset()
        _his_turn(card)
        window = [{"role": "user", "content": "find me monitors"}, {"role": "assistant", "content": "On it."}]
        dialog.drain_spoken(window, channel=f"text:{card}{about}")
        dialog.note_spoken("The first monitors are in.", about=about)
        _his_turn()
        dialog.drain_spoken(window, channel=f"text:{card}{about}")
        assert window[-1]["content"] == "The first monitors are in.", (card, about)
    cf._reset()


def test_a_report_long_after_his_order_stays_last(monkeypatch):
    from nucleo import canvas_focus as cf
    cf._reset()
    _his_turn("imagenes")
    cf._state["t_cur"] -= cf.CROSSING_S + 5               # his order was a while ago
    window = [{"role": "user", "content": "show me a red ferari f40"}, {"role": "assistant", "content": "Here."}]
    dialog.drain_spoken(window, channel="text:late-report")
    dialog.note_spoken("The first monitors are in.", about="results::t1")
    _his_turn()
    dialog.drain_spoken(window, channel="text:late-report")
    assert window[-1]["content"] == "The first monitors are in."
    cf._reset()
