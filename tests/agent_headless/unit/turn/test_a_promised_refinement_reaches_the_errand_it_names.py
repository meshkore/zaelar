"""A promised refinement reaches the errand it names — in both channels (node 2.439).

three-tasks-at-once (ES, 2026-10-11 02:04): «Vale, guay. Oye, ¿y al juego le puedes poner monedas?» → «Voy con
ello, le añado monedas para recoger y sumar puntos.» — and no call at all. Both promise backstops re-escalate only an
order that LOOKS like a web task, so a refinement of a running errand was promised out loud and dropped on the floor.

Bounded on the consequence, no wording table: when the reply promised an act and called nothing, his own words go to
the LIVE errand his sentence names most, through the injection `send_to_worker` uses. A parked errand is the
confirmation gate's (node 2.438 folds the words into it); a reply that asks him for a detail promised nothing.
"""
from __future__ import annotations

import asyncio
import time
import types

import pytest

from nucleo import dispatch
from nucleo import dispatch_confirm as dc
from nucleo.flash import reply_promise
from nucleo.turn import errands_of_a_turn as E

REPORT = {"id": "1", "request": "Hazme un informe sobre coches eléctricos para ciudad", "phase": "", "waiting_on": ""}
MONITOR = {"id": "3", "request": E.listing_errand({"query": "monitor de segunda mano barato"}), "phase": "",
           "waiting_on": ""}
GAME = {"id": "9", "request": "Crear un NUEVO widget de juego de plataformas tipo Super Mario", "phase": "",
        "waiting_on": ""}
HIS = "Vale, guay. Oye, ¿y al juego le puedes poner monedas? De esas que vas recogiendo por las plataformas."
PROMISE = "Voy con ello, le añado monedas para recoger y sumar puntos."


@pytest.fixture
def injected(monkeypatch):
    out = []
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [dict(REPORT), dict(MONITOR), dict(GAME)])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label=""))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    monkeypatch.setattr(dispatch, "inject_soon", lambda which, msg: out.append((which, msg)))
    monkeypatch.setattr(reply_promise, "promises_action", lambda r: r == PROMISE)
    return out


def test_a_promise_over_a_live_errand_routes_his_words_to_it(injected):
    assert E.promised_refinement(HIS, PROMISE) == "9"
    assert E.promised_refinement(HIS, "Vale, ¿cuántas monedas quieres por nivel?") == "", "no promise, no route"
    assert E.promised_refinement("Vale, gracias.", PROMISE) == "", "a sentence naming no errand routes nowhere"


def test_a_parked_errand_is_left_to_the_gate(injected, monkeypatch):
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [dict(REPORT), dict(MONITOR)])
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {"9": {"request": GAME["request"], "kind": "code", "context": {},
                                                       "trusted": True, "sheet": "", "ts": time.time()}})
    assert E.promised_refinement(HIS, PROMISE) == ""


def test_the_typed_channel_sends_it(injected):
    """Through the typed channel, which runs the voice turn: the model promises and calls nothing."""
    from tests.brain import harness as H
    case = {"id": "refine", "lang": "es", "phrase": HIS, "source": "test", "screen": {"open": []}, "expect": "talk",
            "model": {"say": PROMISE}}
    with H.Isolated("es") as iso:
        iso.seed(case)
        from nucleo.cli import turn
        try:
            asyncio.run(turn.run_turn(HIS, sid="refine", ingest=False, execute=True))
        finally:
            turn.reset("refine")
    assert injected == [("9", HIS)], injected


def test_the_voice_channel_sends_it(injected):
    from voice.engine.llm.providers import promise_backstop
    escalated = []
    promise_backstop.run(PROMISE, did_act=False, op_text=HIS, prev_pending=[], emit=lambda *a, **k: None,
                         escalate=lambda *a, **k: escalated.append(a), similar_pending=lambda *a: False)
    assert injected == [("9", HIS)] and not escalated
