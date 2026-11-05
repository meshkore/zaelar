"""A request the door refuses is never answered as started (V2-852 T21, V2-854 F4, I4).

Measured on his engine (2026-11-05 15:31): with the agent stopped (⏻) a typed search got «I'm running that search
now» while `dispatch` logged the escalation REFUSED — the listener read the switch after the turn had spoken. The
errand door (`nucleo/acts/errand.escalate_to_slowbrain`, the one portal) reads `runstate.blocks_new_work` itself:
no id, no row, nothing on the bus, and its outcome — `cannot`, in his language — is the line the turn's mouth says.
"""
from __future__ import annotations

import pytest

from memory import db as memdb
from nucleo import runstate
from nucleo.acts import errand
from nucleo.circuit import verdict as V
from nucleo.turn import mouth, reply
from voice import trace

REQUESTS = {
    "en": "find me a used estate car, 2021 or 2022, under 120,000 km",
    "es": "búscame un piso de alquiler en Valencia con dos habitaciones",
}


@pytest.fixture
def door(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    memdb.reset_db()
    errand.reset()
    state = {"bus": [], "born": [], "stopped": True}
    monkeypatch.setattr(errand, "_emit_bus", lambda topic, payload: state["bus"].append((topic, payload)))
    monkeypatch.setattr("nucleo.turn.flow_door.at_the_portal", lambda req, ctx: True)
    monkeypatch.setattr("nucleo.consequence.passes", lambda *a, **k: True)
    monkeypatch.setattr("nucleo.acts.surface_owner.errand_born", lambda *a, **k: None)
    monkeypatch.setattr("nucleo.circuit.ledger.born", lambda tid, req, ctx: state["born"].append(req) or f"row-{tid}")
    monkeypatch.setattr(runstate, "blocks_new_work", lambda **k: state["stopped"])
    yield state
    trace.adopt("")
    reply.taken()
    errand.rows_settled()


@pytest.mark.parametrize("lang", ["en", "es"])
def test_a_stopped_agent_refuses_at_the_portal_and_says_so(door, monkeypatch, lang):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    trace.adopt(f"T21-{lang}")
    mouth.open_for()
    tid = errand.escalate_to_slowbrain(REQUESTS[lang], context={"src": "voice"})
    assert tid == 0, "a stopped agent gave the request an id"
    assert not [t for t, _p in door["bus"] if t == "escalate.requested"], "the escalation reached the bus"
    assert not door["born"], "a row was born for work that never starts"
    lines = reply.taken()
    assert len(lines) == 1 and lines[0].verdict == V.CANNOT.name, lines
    said = lines[0].said
    assert said and REQUESTS[lang][:40] in said, f"the line does not name what was not started: {said!r}"
    assert "⏻" in said
    assert ("parado" in said) == (lang == "es"), "the line is not in his language"
    mouth.close("", lambda _t: None, type("S", (), {"sanitize": staticmethod(lambda t, **k: t)}))


def test_a_running_agent_still_opens_the_errand(door):
    door["stopped"] = False
    trace.adopt("T21-run")
    tid = errand.escalate_to_slowbrain(REQUESTS["en"], context={"src": "voice"})
    assert tid and [t for t, _p in door["bus"] if t == "escalate.requested"]
    assert door["born"] == [REQUESTS["en"]]
    assert not reply.taken(), "a started errand said a refusal"


def test_the_start_line_is_only_said_for_an_errand_that_started():
    """The turn's silent-start line («I'm on it») is a start's line: the close says it only when the door gave an id."""
    import inspect
    from nucleo.turn import pipeline_errands
    src = inspect.getsource(pipeline_errands.launch_the_errands)
    head, _sep, rest = src.partition("_started = _escalate_mod.escalate_to_slowbrain(")
    assert _sep, "the main launch no longer keeps the door's answer"
    gate = rest.split("_reply.say_started(", 1)[0]
    assert "if _started" in gate, "«I'm on it» is said whatever the door answered"
