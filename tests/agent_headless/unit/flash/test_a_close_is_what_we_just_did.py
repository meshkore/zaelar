"""A canvas gesture of his turn is «what we just did» — a correction of it is the card's, never the errand's (V2-831
T-02c).

Measured 2026-10-28: «close all» spared the Document; «i said all» came next while the Dexter errand ran. The redo
question (`corrects_last`) is built from «what we just did», and the who-acted-last rule (`stop.last_act_owner`) from
his turns' last act — both read `done_ops`, which held DATA ops only. A close left nothing there: the redo question
was not even asked, and a correction of the close could be read as the running errand's.

The mechanism: every gesture that leaves nothing to point at (close, minimise, full screen, arrange) of HIS turn is
recorded by the one canvas door (`canvas.apply` → `done_ops.gesture`), and a bulk close records itself as ONE gesture
with what it closed and what it kept. A show is not one (what it opened is on screen); a background trace never is.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import done_ops
from nucleo.flash import bulk_close, hard_turn, redo_decision
from voice import trace

OPEN = ["documento", "navegador", "mensajeria"]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    done_ops.reset()
    bulk_close.reset()
    from nucleo.acts import canvas_turn
    from memory import api as memory
    monkeypatch.setattr(canvas_turn, "request_of", lambda brief=None, text=None, **k: {
        "text": text or "", "turn_credit": True, "last_reply": "", "verdict": {"canvas": ("close", 0.9)}})
    monkeypatch.setattr(bulk_close, "_open_instances", lambda: list(OPEN))
    monkeypatch.setattr(memory, "write", lambda *a, **k: None)
    yield
    done_ops.reset()
    bulk_close.reset()


def _emit(*a, **k):
    return None


@pytest.mark.parametrize("said", ["close everything you don't need", "cierra lo que no necesites"])
def test_a_close_that_kept_a_card_is_what_we_just_did(said):
    trace.begin("edit the draft", origin="turno")
    done_ops.note("documento", "show", {"body": "draft"})          # the Document is the card in use
    trace.begin(said, origin="turno")
    asyncio.run(hard_turn.handle(said, "close", _emit))
    op = redo_decision.last_op()
    assert op and op["action"] == "close" and op["wid"] == "canvas", op
    assert op["payload"].get("kept") == "documento" and "mensajeria" in op["payload"].get("closed", "")
    q = redo_decision.question()
    assert q and "canvas:close" in q["instructions"] and "kept=documento" in q["instructions"]


def test_the_close_is_his_last_act_after_the_errand_he_commissioned(monkeypatch):
    """«i said all» while an errand runs: the last thing his turns acted on is the canvas, so `corrects_last` makes
    the correction the card's — the errand is not steered with it."""
    from nucleo import dispatch
    from nucleo.request import stop
    errand_turn = trace.begin("find where Dexter season 2 streams", origin="turno")
    rec = type("R", (), {"trace_id": errand_turn, "injects": [], "sheet": ""})()
    monkeypatch.setattr(dispatch, "resolve_sessions", lambda q="": ["w-1"])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: rec)
    trace.begin("close all", origin="turno")
    asyncio.run(hard_turn.handle("close all", "close", _emit))
    assert stop.last_act_owner() == "card"


def test_a_show_and_a_background_gesture_are_not_his_act():
    trace.begin("open the calendar", origin="turno")
    done_ops.gesture("show", "agenda")
    trace.begin("hourly digest", origin="cron")
    done_ops.gesture("close", "agenda")
    assert done_ops.his_last() == {}
