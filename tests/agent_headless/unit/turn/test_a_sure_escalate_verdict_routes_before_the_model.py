"""A SURE «escalate» verdict routes the request to its task before the model is trusted (V2-851 F5, CRIT-E27).

Battery C9 «the send waits for his consent», measured before this: the brief's `escalate_or_inline` flipped to
escalate at 0.52-0.62 and Flash still answered inline and sent. Now the one pipeline reads the verdict where the
model's output is held anyway — its first word (the Hold) and each call it makes (`route_by_verdict.gate_calls`) — and
under a sure «escalate» (≥ the licence) the inline call, tags and words do not run; the request is the commission the
close launches through the errand portal (`flow_of.route`), and the turn's one line is the start line. Not a re-run:
nothing calls the model again. Disarm: `sure_escalate` returning False → red.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from nucleo.flash import follow_up_pass as FP
from nucleo.turn import brief as tb
from nucleo.turn import route_by_verdict as R

ORDER = "Contéstale a Raquel lo que te dije del correo"


def _brief(choice=None, conf=0.0, ready=True):
    ev = threading.Event()
    if ready:
        ev.set()
    res = {"_call_id": "t", tb.ESCALATE_KEY: {"choice": choice, "confidence": conf, "probs": {}}} if choice else {}
    return {"event": ev, "turn_id": "t", "result": res if ready else None}


def _gate(brief, wait=0.0):
    ran, events, req = [], [], {"v": None, "more": [], "surface": {}}
    call = R.gate_calls(lambda n, a: ran.append(n) or "ran", brief=brief, escalate_req=req, operator_text=ORDER,
                        emit=lambda *a, **k: events.append(a), t0=__import__("time").monotonic(), wait=wait)
    return call, ran, req, events


@pytest.mark.parametrize("conf", [0.52, 0.62, 0.95])
def test_a_sure_escalate_runs_no_inline_call_and_routes_the_request(conf):
    call, ran, req, events = _gate(_brief("escalate", conf))
    assert call("reply_message", {"text": "Hola Raquel"}) is None and ran == []
    assert req["v"] == ORDER and req["routed"] and any("sure escalate" in e[1] for e in events)
    call("escalate_to_slowbrain", {"request": "x"})
    assert ran == ["escalate_to_slowbrain"], "the commission itself still runs"


@pytest.mark.parametrize("choice,conf", [("handle_inline", 0.9), ("escalate", 0.4), (None, 0.0)])
def test_an_inline_unsure_or_absent_verdict_lets_the_model_act(choice, conf):
    call, ran, req, _ = _gate(_brief(choice, conf))
    assert call("reply_message", {}) == "ran" and ran == ["reply_message"] and req["v"] is None


def test_a_brief_in_flight_is_waited_for_at_most_the_route_wait():
    late = _brief(ready=False)

    def _land():
        __import__("time").sleep(0.1)
        late["result"] = {"_call_id": "t", tb.ESCALATE_KEY: {"choice": "escalate", "confidence": 0.6, "probs": {}}}
        late["event"].set()
    threading.Thread(target=_land, daemon=True).start()
    call, ran, req, _ = _gate(late, wait=2.0)
    assert call("reply_message", {}) is None and ran == [] and req["v"] == ORDER


def _hold(brief, pieces=("Ya le he contestado a Raquel.",), route_wait=0.0):
    sent, events = [], []
    h = FP.Hold(brief, sent.append, route_wait_s=route_wait)
    for p in pieces:
        h.say(p)
    asyncio.run(h.release([], (), lambda *a, **k: events.append(a)))
    return h, sent, events


def test_the_models_words_are_not_said_under_a_sure_escalate():
    h, sent, events = _hold(_brief("escalate", 0.6))
    assert sent == [] and h.routed and any("routed to its task" in e[1] for e in events)


def test_the_words_are_said_under_an_inline_verdict():
    h, sent, _ = _hold(_brief("handle_inline", 0.9))
    assert "".join(sent) == "Ya le he contestado a Raquel." and not h.routed


def test_words_wait_for_a_brief_that_lands_inside_the_wait():
    late = _brief(ready=False)
    sent = []
    h = FP.Hold(late, sent.append, route_wait_s=2.0)
    h.say("Ya le he ")
    assert sent == [] and h.routed is None
    late["result"] = {"_call_id": "t", tb.ESCALATE_KEY: {"choice": "escalate", "confidence": 0.55, "probs": {}}}
    late["event"].set()
    h.say("contestado.")
    asyncio.run(h.release([], (), lambda *a, **k: None))
    assert sent == [] and h.routed


def test_the_pipeline_wires_the_route_and_runs_no_model_for_it():
    import inspect
    src = open("nucleo/turn/pipeline.py", encoding="utf-8").read()
    assert "_route.gate_calls(_tx.on_tool_call" in src and "_route.route(req[\"escalate_req\"]" in src
    assert "_route.sure_escalate(_brief) else _tx.tag_emit" in src, "an inline tag does not run either"
    assert "route_wait_s=_route.wait_s()" in open("nucleo/turn/pipeline_stream.py", encoding="utf-8").read()
    mod = inspect.getsource(R)
    assert "FastClient" not in mod and "choose_sync" not in mod and "ask_many" not in mod


# ── a routed commission is final at the close (battery C9, 2026-11-05) ─────────────────────────────────────────
def _close(req, monkeypatch):
    """Drive the close's act chain over a turn whose request a sure verdict routed; returns the card acts tried."""
    from types import SimpleNamespace

    from nucleo.flash import post_stream as pst, post_stream_acts, router as _router
    tried = []

    def _rung(escalate_req, **k):       # the third rung as measured: the brief's card act, the commission cleared
        tried.append("take_rung")
        escalate_req["v"] = None
        return True
    monkeypatch.setattr(pst._direct_action, "take_rung", _rung)

    async def _nothing(*a, **k):
        return None
    asyncio.run(post_stream_acts.complete_the_acts(
        _apply_widget_data=lambda *a: tried.append("card_act"), _brief=_brief("escalate", 0.7), _data_ops_hechas=[],
        _has_workers=False, _prompt_mod=None, _repeat_repair={"v": None}, _router=_router,
        _show_guard_target=lambda *a: None, _tag_emit=lambda *a, **k: None, _tool_fired=set(), _turn_op_tasks=[],
        acted={"widget": False}, brain=SimpleNamespace(_window=[], _last_action=None, _last_spoken="", _turn_calls=[]),
        canvas_h=None, clarify={"msg": ""}, data_done={"v": None}, emit=lambda *a, **k: None, escalate_req=req,
        images_req={"v": None}, listing_req={"v": None}, music_req={"v": None}, operator_text=ORDER,
        read_req={"v": None}, recall_req={"v": None}, reopen_req={"v": None}, reveal_req={"v": None},
        search_req={"v": None}, send=lambda s: None, speak=_nothing, spec=None,
        speech=SimpleNamespace(sanitize=lambda s, drop_metadata=False: s), spoken=[], text=ORDER,
        worker_acted={"v": None}))
    return tried


def test_a_routed_commission_is_never_swapped_for_a_card_act_at_the_close(monkeypatch):
    """C9 measured: the verdict routed «answer that mail» and the third rung then ran the messaging card's `reply`
    inline — no worker, no read of his mail, no consent asked. A routed request stays the turn's commission."""
    req = {"v": None, "more": [], "surface": {}}
    R.route(req, ORDER, lambda *a, **k: None, why="verdict")
    assert R.owns(req)
    assert _close(req, monkeypatch) == [] and req["v"] == ORDER, "the routed commission reaches its task"


def test_disarmed_an_unrouted_commission_is_what_the_third_rung_may_swap(monkeypatch):
    """RED proof: the same commission without the router's mark goes to the card act — what C9 measured."""
    req = {"v": ORDER, "more": [], "surface": {}}
    assert _close(req, monkeypatch) == ["take_rung"] and req["v"] is None
