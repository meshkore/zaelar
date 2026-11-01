"""A close's follow-up question never blocks the voice loop (V2-831 audit A2).

The class: two closed questions a close may need — which cards on screen he names (`brief_screen.named_to_close`,
T-19 R4c) and whether a bulk close takes the card in use too (`bulk_close`, Z2) — were asked with the BLOCKING Jev
call from readers that run on the voice event loop (the hard interrupt, the canvas lanes, the close guards). Each
first read froze the loop for the whole round trip, up to Jev's timeout, while the turn waited on nothing.

The mechanism: a sure close's follow-ups ride the brief's own background trip (`jev.ask_many(after=…)` →
`brief_screen.ride_the_brief`), so on a live turn every reader reads them; the hard interrupt, which may have no brief,
awaits its question in a thread. A reader on the loop never asks: with no answer the verdict stands.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from nucleo import done_ops, jev
from nucleo.flash import bulk_close, hard_turn
from nucleo.turn import brief as tb, brief_screen

OPEN = ["agenda", "documento", "mensajeria"]
CLOSES = {"en": "close the calendar and the messages", "es": "cierra la agenda y los mensajes"}
BULK = {"en": "clear the screen", "es": "despeja la pantalla"}


@pytest.fixture
def jev_calls(monkeypatch):
    """Jev answers: the turn brief (a sure close, names «elsewhere»), the close pick (the agenda) and the scope (every
    card). Each call records the thread it ran on and takes a measurable while, like a real round trip."""
    calls: list[tuple[str, str]] = []

    def fake(state, questions, *, question_id="brief", **k):
        calls.append((question_id, threading.current_thread().name))
        time.sleep(0.25)
        if question_id == "turn-brief":
            return {tb.CANVAS_KEY: {"choice": "close", "confidence": 1.0, "probs": {"close": 1.0}},
                    tb.NAMES_KEY: {"choice": "elsewhere", "confidence": 0.8, "probs": {"elsewhere": 0.8}}}
        if question_id == "close_pick":
            return {key: {"choice": "named" if "agenda" in q["instructions"].lower() else "not_named", "confidence": 0.9,
                          "probs": {"named": 0.9 if "agenda" in q["instructions"].lower() else 0.1}}
                    for key, q in questions.items()}
        return {"scope": {"choice": "every_card", "confidence": 0.9, "probs": {"every_card": 0.9}}}

    monkeypatch.setattr(jev, "enabled", lambda: True)
    monkeypatch.setattr(jev, "choose_many_sync", fake)
    monkeypatch.setattr(tb, "build", lambda text, **kw: {tb.CANVAS_KEY: {}, tb.NAMES_KEY: {}})
    done_ops.reset()
    bulk_close.reset()
    done_ops.note("documento", "show", {"body": "draft"})        # the Document is the card in use
    yield calls
    done_ops.reset()
    bulk_close.reset()


async def _loop_ticks_while(fn) -> tuple[object, int]:
    """Run `fn` (a coroutine factory) beside a 10 ms ticker; a blocked loop stops the ticker."""
    ticks = 0

    async def _tick():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1
    t = asyncio.ensure_future(_tick())
    try:
        return await fn(), ticks
    finally:
        t.cancel()


@pytest.mark.parametrize("lang", ["en", "es"])
def test_a_live_brief_carries_the_follow_ups_and_the_loop_only_reads_them(jev_calls, lang):
    handle = tb.ask(CLOSES[lang], open_ids=OPEN)
    assert handle["event"].wait(3), "the brief never landed"
    asked = [q for q, _ in jev_calls]
    assert asked == ["turn-brief", "close_pick", "close_scope"], asked
    assert all(th != threading.main_thread().name for _, th in jev_calls), "a follow-up ran on the caller's thread"

    async def _read():
        return brief_screen.named_to_close(handle), brief_screen.names_elsewhere(handle)
    (picks, elsewhere), _ = asyncio.run(_loop_ticks_while(_read))
    assert picks == ["agenda"] and elsewhere is False
    assert len(jev_calls) == 3, "a reader on the loop asked Jev again"


def test_a_reader_on_the_loop_never_asks(jev_calls):
    ev = threading.Event()
    ev.set()
    bare = {"event": ev, "judged": CLOSES["en"], "open_ids": OPEN,
            "result": {tb.CANVAS_KEY: {"choice": "close", "confidence": 1.0, "probs": {"close": 1.0}},
                       tb.NAMES_KEY: {"choice": "elsewhere", "confidence": 0.9, "probs": {"elsewhere": 0.9}}}}

    async def _read():
        return brief_screen.named_to_close(bare), bulk_close.spare_for(OPEN, BULK["en"], brief=bare)
    (picks, spare), ticks = asyncio.run(_loop_ticks_while(_read))
    assert jev_calls == [] and picks == [], "the loop asked a blocking verdict"
    assert spare == ["documento"], "with no answer the verdict stands: the card in use is spared"


@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_hard_interrupt_asks_its_scope_off_the_loop(jev_calls, monkeypatch, lang):
    from nucleo.acts import canvas_turn
    from memory import api as memory
    monkeypatch.setattr(canvas_turn, "request_of", lambda brief=None, text=None, **k: {
        "text": text or "", "turn_credit": True, "last_reply": "", "verdict": {"canvas": ("close", 0.9)}})
    monkeypatch.setattr(bulk_close, "_open_instances", lambda: list(OPEN))
    monkeypatch.setattr(memory, "write", lambda *a, **k: None)
    events: list = []

    def emit(kind, action, text=None, role=None, extra=None):
        events.append((kind, action, dict(extra or {})))

    async def _close():
        return await hard_turn.handle(BULK[lang], "close", emit)
    _, ticks = asyncio.run(_loop_ticks_while(_close))
    assert [q for q, _ in jev_calls] == ["close_scope"]
    assert jev_calls[0][1] != threading.main_thread().name, "the scope question ran on the voice loop"
    assert ticks >= 10, f"the loop stood still during the round trip ({ticks} ticks in 250 ms)"
    closed = [e[2].get("id", "*ALL*") for e in events if e[0] == "widget" and e[1] == "close"]
    assert closed == ["*ALL*"], "his «every card» answer closes the card in use too"
