"""An order whose act IS a memory write owes no «I haven't done it», and a turn he did not originate owes nothing
(node 2.936).

Demo sandbox 2026-10-29 (build 86, Jev on): the INIT's «Your name is Johnny…» and «Remember my interests…» were read
as orders (request_type=order), no tool ran, and the turn ended «I haven't done it — I couldn't carry it out from
here.» — while the memory door (`memory.ingest`, fired by the turn in the background) was still filing his words: it
wrote the assistant's name and nine preference rows two seconds AFTER the line. And the session's kickoff — OUR
greeting prompt, which Jev also read as an order — ended «Hi, I'm Zaelar… What's your name? I haven't done it…».

The mechanism: the memory door declares, per turn, what it changed (`reply.memory_began` / `memory_settled`); the
turn's acts door (`reply.after_acts`) waits for it inside its own budget ONLY when the brief owes an order; the honest
line reads that outcome. The kickoff is a datum of the trace (`trace.is_kickoff`), read by `reply.owes_an_act`.
Nothing here reads the reply or his words.

Disarm: without `memory_settled` at the door, or without the wait in `after_acts`, the memory cases go red; without
the kickoff check in `owes_an_act`, the greeting case goes red; waiting on every turn turns the «owes nothing» case red.
"""
from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from nucleo.memory_agent import ingest as I
from nucleo.turn import brief as tb
from nucleo.turn import promise_kept as pk
from nucleo.turn import reply as R
from voice import trace

LINE = "I haven't done it."


def _brief(kind: str = "order", escalate: str = "handle_inline") -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {
        tb.REQUEST_KEY: {"choice": kind, "confidence": 0.9},
        tb.ESCALATE_KEY: {"choice": escalate, "confidence": 0.95},
        tb.WORDS_KEY: {"choice": "act", "confidence": 0.9}}}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(R, "_MEMORY", {})
    monkeypatch.setattr(R, "_ASKED", {})
    monkeypatch.setattr(pk, "_state_holds", lambda open_ids=None: False)
    monkeypatch.setattr(pk, "_not_kept_line", lambda: LINE)


def _door_returns(monkeypatch, result: dict, delay: float = 0.3):
    """The distiller is a model: the door's own body runs, only what the distiller filed is given."""
    async def locked(text, *, role="operator"):
        await asyncio.sleep(delay)
        return dict(result)
    monkeypatch.setattr(I, "_ingest_utterance_locked", locked)
    monkeypatch.setattr(I, "_HOME_LOOP", None)


async def _turn(text: str, brief: dict, *, timeout: float = R.WAIT_S) -> str:
    """One turn as the voice turn runs it: the brief joined to the trace, the memory door fired in the background
    (`turn_admit`), the reply streamed, the acts door, then the honest line."""
    trace.begin(text, origin="turno")
    tb.remember_for_the_turn(brief)
    task = asyncio.get_running_loop().create_task(I.ingest_utterance(text, role="operator", channel="typed"))
    await asyncio.sleep(0)
    said = "Got it."
    speech = SimpleNamespace(sanitize=lambda s, drop_metadata=True: s)
    said = await R.after_acts((), said, lambda s: None, speech, timeout=timeout)
    line = pk.honest_line(said, {}, acted=False, brief=brief)
    await task
    return line


@pytest.mark.parametrize("text,result", [
    ("Your name is Johnny. When I say Johnny, I am talking to you.", {"source": "llm", "atoms": 1}),
    ("A partir de ahora te llamas Johnny.", {"source": "llm", "atoms": 1}),
    ("Remember my interests: Formula 1, basketball, hiking.", {"source": "llm", "atoms": 9}),
    ("Recuerda que mi perro se llama Pixel.", {"source": "llm+profile", "atoms": 2}),
    ("Forget that I live in Madrid.", {"source": "forget", "atoms": 0, "forgot": 1}),
])
def test_an_order_whose_act_was_a_memory_write_owes_nothing(text, result, monkeypatch):
    _door_returns(monkeypatch, result)
    assert asyncio.run(_turn(text, _brief())) == ""


@pytest.mark.parametrize("text,result", [
    ("Book me a table at Botín tomorrow at nine.", {"source": "net", "atoms": 1}),       # the request's raw copy
    ("Mándale el informe a Rowan por correo.", {"source": "discard-llm", "atoms": 0}),
    # V2-834 T23 — agenda-appointment-lifecycle__us: «it's cancelled» over nothing, the `request` pill counted as the act
    ("you know what, cancel it, I'll call them myself", {"source": "llm", "atoms": 1, "asks": 1}),
])
def test_an_order_where_nothing_ran_is_still_said_undone(text, result, monkeypatch):
    _door_returns(monkeypatch, result)
    assert asyncio.run(_turn(text, _brief())) == LINE


def test_a_memory_write_never_keeps_an_errand(monkeypatch):
    _door_returns(monkeypatch, {"source": "llm", "atoms": 3})
    assert asyncio.run(_turn("Find me a hotel in Seville and remember I like quiet rooms.",
                             _brief(escalate="escalate"))) == LINE


async def _acts_door_time(text: str, brief: dict, timeout: float) -> float:
    """How long the acts door held the turn while this turn's memory door was still filing."""
    trace.begin(text, origin="turno")
    tb.remember_for_the_turn(brief)
    task = asyncio.get_running_loop().create_task(I.ingest_utterance(text))
    await asyncio.sleep(0)
    t0 = time.monotonic()
    await R.after_acts((), "Got it.", lambda s: None, SimpleNamespace(sanitize=lambda s, **k: s), timeout=timeout)
    spent = time.monotonic() - t0
    await task
    return spent


@pytest.mark.parametrize("text", ["I love basketball.", "Me encanta el baloncesto."])
def test_a_turn_that_owes_nothing_does_not_wait_for_memory(text, monkeypatch):
    _door_returns(monkeypatch, {"source": "llm", "atoms": 1}, delay=1.5)
    assert asyncio.run(_acts_door_time(text, _brief(kind="comment"), timeout=R.WAIT_S)) < 0.5


def test_the_wait_stays_inside_the_acts_budget(monkeypatch):
    _door_returns(monkeypatch, {"source": "llm", "atoms": 1}, delay=1.5)
    assert asyncio.run(_acts_door_time("Remember my interests: sailing.", _brief(), timeout=0.3)) < 0.8


@pytest.mark.parametrize("prompt", [
    "I just connected. FIRST turn — SHORT and warm. If you do NOT know me yet, introduce yourself and ask my name.",
    "Me acabo de conectar. PRIMER turno: saluda corto y pregúntame cómo me llamo.",
])
def test_the_kickoff_is_not_his_order_and_owes_nothing(prompt, monkeypatch):
    _door_returns(monkeypatch, {"source": "discard", "atoms": 0})

    async def run():
        trace.begin(prompt, origin="kickoff")
        line_kickoff = pk.honest_line("Hi, I'm Zaelar. What's your name?", {}, acted=False, brief=_brief())
        trace.begin("Book me a table at Botín.", origin="turno")       # his next turn is his again
        line_his = pk.honest_line("On it.", {}, acted=False, brief=_brief())
        return line_kickoff, line_his
    assert asyncio.run(run()) == ("", LINE)


CANNOT = {"kind": pk.CANNOT, "reason": "no_action"}


async def _cannot_turn(text: str, brief: dict) -> str:
    """The same turn, but the repair pass declared `cannot_do` (pass 10 on v3.107, INIT «contact <friend> via Telegram»,
    «Remember these future responsibilities»: «nothing on that card can do it» over a memory write)."""
    trace.begin(text, origin="turno")
    tb.remember_for_the_turn(brief)
    task = asyncio.get_running_loop().create_task(I.ingest_utterance(text, role="operator", channel="typed"))
    await asyncio.sleep(0)
    speech = SimpleNamespace(sanitize=lambda s, drop_metadata=True: s)
    said = await R.after_acts((), "Got it.", lambda s: None, speech)
    line = pk.honest_line(said, dict(CANNOT), acted=False, brief=brief)
    await task
    return line


@pytest.mark.parametrize("kind", ["order", "comment"])
def test_a_cannot_over_an_order_whose_act_was_the_memory_write_says_nothing(monkeypatch, kind):
    monkeypatch.setattr(pk, "_not_kept_line", lambda key="": "nothing on that card can do it")
    _door_returns(monkeypatch, {"source": "llm", "atoms": 4})
    line = asyncio.run(_cannot_turn("Remember these future responsibilities: insurance renewal on March 12.", _brief(kind)))
    assert line == "", f"the act was the memory write: {line!r}"


def test_a_cannot_with_nothing_filed_is_still_said(monkeypatch):
    monkeypatch.setattr(pk, "_not_kept_line", lambda key="": "nothing on that card can do it")
    _door_returns(monkeypatch, {"source": "net", "atoms": 1}, delay=0.0)     # only the raw copy of a request
    line = asyncio.run(_cannot_turn("Send the invoice to Quinn.", _brief("order")))
    assert line == "nothing on that card can do it"


# ── V2-831 audit A10: the memory door is the act only for an order aimed at no card ─────────────────────────────────
def _aimed(key: str, choice: str) -> dict:
    b = _brief()
    b["result"][key] = {"choice": choice, "confidence": 0.9}
    return b


@pytest.mark.parametrize("text,key,choice", [
    ("My dentist is Dr Rowan, move the appointment to five.", tb.CATALOG_KEY, "agenda"),
    ("Mi dentista es la doctora Quinn; pasa la cita a las cinco.", tb.TARGET_KEY, "agenda:move_meeting"),
])
def test_a_fact_filed_beside_an_order_at_a_card_is_not_its_act(text, key, choice, monkeypatch):
    """The distiller files a fact from EVERY admitted sentence; a fact filed from the same sentence as an order aimed
    at a card is not that order's act — nothing moved, so «not done» is still owed."""
    _door_returns(monkeypatch, {"source": "llm", "atoms": 1})
    assert asyncio.run(_turn(text, _aimed(key, choice))) == LINE


def test_a_reason_that_says_nothing_stays_silent_while_memory_files(monkeypatch):
    """`awaits_his_yes` says nothing; with the memory door still filing it became the generic «not done» later."""
    monkeypatch.setattr(pk, "_not_kept_line", lambda key="": "" if key == "promise_cannot_awaits_his_yes" else LINE)
    said: list = []
    from nucleo.flash import follow_up_pass
    monkeypatch.setattr(follow_up_pass, "deliver", said.append)
    _door_returns(monkeypatch, {"source": "discard", "atoms": 0}, delay=0.3)

    async def run():
        trace.begin("Shall I book it?", origin="turno")
        b = _brief()
        tb.remember_for_the_turn(b)
        task = asyncio.get_running_loop().create_task(I.ingest_utterance("Book the table at nine"))
        await asyncio.sleep(0)
        line = pk.honest_line("Shall I book it?", {"kind": pk.CANNOT, "reason": "awaits_his_yes"}, acted=False, brief=b)
        await task
        await asyncio.gather(*list(pk._LATE))
        return line
    assert asyncio.run(run()) == "" and said == []


def test_a_memory_door_still_filing_at_the_bound_claims_nothing(monkeypatch):
    monkeypatch.setattr(pk, "MEMORY_WAIT_S", 0.2)
    said: list = []
    from nucleo.flash import follow_up_pass
    monkeypatch.setattr(follow_up_pass, "deliver", said.append)
    _door_returns(monkeypatch, {"source": "llm", "atoms": 0}, delay=1.0)

    async def run():
        trace.begin("Remember my interests: sailing.", origin="turno")
        b = _brief()
        tb.remember_for_the_turn(b)
        task = asyncio.get_running_loop().create_task(I.ingest_utterance("Remember my interests: sailing."))
        await asyncio.sleep(0)
        line = pk.honest_line("Got it.", {}, acted=False, brief=b)
        await asyncio.gather(*list(pk._LATE))
        await task
        return line
    assert asyncio.run(run()) == "" and said == [], said


def test_the_door_counts_the_request_atoms_it_filed(monkeypatch):
    """The distiller's declared `kind="request"` («no sabes si se hizo») rides out of the door as `asks`."""
    from nucleo.memory_agent import ingest_steps as S
    atoms = [{"kind": "request", "text": "cancel the car service"}, {"kind": "fact", "text": "he will call them"}]

    async def gate(**kw):
        return {"_is_corr": False, "atoms": atoms, "st": {}, "t": kw["text"], "text": kw["text"]}

    async def file(**kw):
        return None, {"source": "llm", "atoms": 2}
    monkeypatch.setattr(S, "gate_the_utterance", gate)
    monkeypatch.setattr(S, "file_the_atoms", file)
    out = asyncio.run(I._ingest_utterance_locked("cancel it, I'll call them myself"))
    assert out["asks"] == 1 and I.changed(out) == 1
