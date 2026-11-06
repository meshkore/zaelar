"""An errand the model did not commission is opened by the brief's verdict, never by his words (V2-857 phase 8, 2.1618).

Before: the close's «irreversible backstop» read his sentence through the money vocabulary (`danger.is_dangerous`, 23
regexes) and, when the model had not escalated, made the sentence an errand. Since phase 4 the errand's class is the
brief's verdict alone, so the only thing that rail still did was OPEN an errand the turn had not commissioned — a
judgement of intent from words. The brief already asks it: `escalate_or_inline` (does this turn commission background
work?) and `errand_class` (what would it do in the world?). A sure «escalate» routes the request to its task before
the model is trusted (`route_by_verdict`, CRIT-E27), and the errand carries the class the brief read. No question was
added (K9: nothing new is paid per turn).

Disarm: `route_by_verdict.sure_escalate` returning False — the paid verdict commissions nothing and the model's
inline call runs instead.
"""
from __future__ import annotations

import asyncio
import inspect
import threading
import time
from types import SimpleNamespace

import pytest

from nucleo import danger
from nucleo.acts import errand
from nucleo.turn import brief as tb
from nucleo.turn import pipeline_errands as PE
from nucleo.turn import route_by_verdict as R

ORDERS = {"es": "Paga la factura de la luz antes del día 5", "en": "Pay the electricity bill before the 5th"}


def _brief(escalate=None, conf=0.0, cls=None, cls_conf=0.0):
    ev = threading.Event()
    ev.set()
    res = {"_call_id": "t"}
    if escalate:
        res[tb.ESCALATE_KEY] = {"choice": escalate, "confidence": conf, "probs": {}}
    if cls:
        res[errand.CLASS_KEY] = {"choice": cls, "confidence": cls_conf, "probs": {}}
    return {"event": ev, "turn_id": "t", "result": res}


def _launch(text, brief, escalate_req, monkeypatch):
    """Drive the close's errand launch with the turn's state; returns the errands it started."""
    started = []
    esc = SimpleNamespace(
        escalate_to_slowbrain=lambda req, context=None: started.append((req, dict(context or {}))) or True,
        done_when_from_brief=lambda _b: None, class_verdict=errand.class_verdict)
    router = SimpleNamespace(create_widget_request=lambda _t: "", looks_like_create_widget=lambda _r: False)
    from nucleo import surfaces
    from nucleo.request import ending
    motor = SimpleNamespace(_surfaces_mod=surfaces, _similar_pending=lambda *_a: False)
    for mod, name, fn in ((PE._his_spec, "carry", lambda *_a, **_k: None), (PE._sbe, "routed", lambda *_a, **_k: None),
                          (PE._sbe, "each_line", lambda *_a, **_k: ""), (PE._reply, "say_started", lambda *_a, **_k: None),
                          (ending, "close_turn", lambda *_a, **_k: None), (ending, "only_held", lambda: False)):
        monkeypatch.setattr(mod, name, fn)
    speech = SimpleNamespace(sanitize=lambda s, **_k: s)
    asyncio.run(PE.launch_the_errands(
        motor=motor, send=lambda _s: None, speech=speech, emit=lambda *a, **k: None, brain=SimpleNamespace(),
        _brief=brief, _op_text=text, _escalate_mod=esc, _prev_pending=[], _router=router, _did_act=True,
        _acted_elsewhere=True, acted={"widget": False}, escalate_req=escalate_req, spoken_text="", worker_acted={"v": None}))
    return started


def _turn(text, brief):
    """The model answers with an inline reminder; its call crosses the verdict's gate. Returns (ran, req, events)."""
    ran, events, req = [], [], {"v": None, "more": [], "surface": {}}
    call = R.gate_calls(lambda n, a: ran.append(n) or "ran", brief=brief, escalate_req=req, operator_text=text,
                        emit=lambda *a, **k: events.append((a, k)), t0=time.monotonic(), wait=0.0)
    call("add_reminder", {"title": text})
    return ran, req, events


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("brief", [None, _brief("handle_inline", 0.9), _brief("escalate", 0.3)],
                         ids=["no-brief", "inline", "unsure"])
def test_his_words_alone_open_no_errand(lang, brief, monkeypatch):
    text = ORDERS[lang]
    assert danger.is_dangerous(text), "premise: the money vocabulary would have opened this one"
    req = {"v": None, "more": [], "surface": {}}
    assert _launch(text, brief, req, monkeypatch) == [], "the words opened an errand the turn did not commission"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_sure_escalate_verdict_opens_it_with_the_class_the_brief_read(lang, monkeypatch):
    text = ORDERS[lang]
    brief = _brief("escalate", 0.8, "moves_money", 0.9)
    ran, req, events = _turn(text, brief)
    assert ran == [] and req["v"] == text and req["routed"], "the inline reminder ran under a sure escalate"
    started = _launch(text, brief, req, monkeypatch)
    assert [s[0] for s in started] == [text]
    assert started[0][1]["errand_class"]["choice"] == "moves_money"
    assert errand.class_of(started[0][1]["errand_class"], text) == "moves_money"
    (args, kw), = [e for e in events if "sure escalate" in e[0][1]]
    extra = kw["extra"]
    assert extra["verdict"] == "escalate" and extra["confidence"] == 0.8 and extra["source"] == "call:add_reminder"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_disarmed_the_paid_verdict_commissions_nothing(lang, monkeypatch):
    monkeypatch.setattr(R, "sure_escalate", lambda _b: False)
    text = ORDERS[lang]
    brief = _brief("escalate", 0.8, "moves_money", 0.9)
    ran, req, _ = _turn(text, brief)
    assert ran == ["add_reminder"] and req["v"] is None
    assert _launch(text, brief, req, monkeypatch) == []


def test_the_close_reads_no_word_vocabulary_to_open_an_errand():
    src = inspect.getsource(PE)
    assert "danger" not in src and "is_dangerous" not in src and "about_a_past_act" not in src
    assert not hasattr(danger, "about_a_past_act"), "its only reader was the rail that went"
