"""With no stop verdict, a live errand stops only on the model's own `stop_worker` call — never on his words (V2-857
phase 8, 2.1621).

Before: when the brief's `stop_errand` verdict was missing (brief off, failed, in flight, unsure), two word lists
decided. `_says_stop` (a regex in the tool executor) VETOED the model's `stop_worker` unless his words said stop —
so «whatever you are running, I want it gone» was refused as context bleed — and `looks_like_stop_work` STOPPED an
errand in a turn whose model had called nothing. Operator's decision (2026-11-06): «basta el modelo». Both fallbacks
went; a sure «keep» verdict is what refuses a dragged-in stop.

`hard_turn.is_worker_stop` still reads `looks_like_stop_work`, on purpose: it runs before any model on the hard
interrupt, and it only decides whether the turn goes on to the model or ends as a hush — it stops nothing itself.

Disarm: `stop.model_stop` vetoing a call with no verdict — the model's stop no longer runs.
"""
from __future__ import annotations

import asyncio
import inspect
import threading
from types import SimpleNamespace

import pytest

from nucleo.flash import hard_turn, tool_executor_calls as _calls, tool_executor_widget, post_stream_settle
from nucleo.request import stop as sd

#: Orders no word list reads as a stop, and a turn that is no stop at all — the model alone decides.
ORDERS = {"es": "esa cosa que tienes en marcha, la quiero fuera ya", "en": "whatever you are running, I want it gone"}
NOT_ORDERS = {"es": "para todas las tareas", "en": "stop the browser task"}


def _brief(choice=None, conf=0.95):
    ev = threading.Event()
    ev.set()
    res = {} if choice is None else {sd.KEY: {"choice": choice, "confidence": conf}}
    return {"event": ev, "turn_id": "t", "open_ids": [], "result": res}


NO_VERDICT = [None, {"event": threading.Event(), "turn_id": "t", "open_ids": [], "result": None},
              _brief(None), _brief(sd.STOP, 0.2)]
NO_VERDICT_IDS = ["no-brief", "in-flight", "not-asked", "unsure"]


def _model_calls_stop(text, brief, monkeypatch):
    """The model called `stop_worker`; returns (what was cancelled, the events)."""
    from nucleo import dispatch
    killed, events = [], []
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: killed.append(w) or ["t1"])
    _calls._t_stop_worker(args={"which": "the running errand"}, _norm_nfkd=lambda s: s.lower(),
                          _say=lambda: SimpleNamespace(stop_which_worker="which?", stop_doubt="?"), clarify={},
                          emit=lambda *a, **k: events.append((a, k)), text=text, worker_acted={"v": None}, brief=brief)
    return killed, events


def _model_called_nothing(text, brief, monkeypatch):
    """The voice turn's settle step over a turn whose model called nothing; returns (cancelled, events)."""
    from nucleo import dispatch
    killed, events = [], []
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: killed.append(w) or ["t9"])
    asyncio.run(post_stream_settle.settle_what_is_pending(
        _ans=None, _ask_waiting=False, _auth_pending=False, _brief=brief,
        _dialog=SimpleNamespace(sanitize_reply=lambda s: s), _filler_audio=SimpleNamespace(played_recently=lambda: False),
        _langs=None, _prev_pending=[], _r=None, _resolve_confirm=lambda yes: None,
        _router=SimpleNamespace(operator_words=lambda o, t: o), _shown_ids=set(), acted={"widget": False},
        aside={"v": False}, brain=SimpleNamespace(_window=[], _last_spoken=""), clarify={"msg": ""},
        confirm_state={"handled": True}, data_done={"v": None}, emit=lambda *a, **k: events.append((a, k)),
        escalate_req={"v": None, "more": [], "surface": {}}, had_pending_confirm=True, llm_metrics={},
        music_req={"v": None}, operator_text=text, search_req={"v": None}, send=lambda s: None,
        speech=SimpleNamespace(sanitize=lambda s, drop_metadata=False: s), spoken_text="", style_fired={"v": False},
        text=text, worker_acted={"v": None}))
    return killed, events


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("brief", NO_VERDICT, ids=NO_VERDICT_IDS)
def test_with_no_verdict_the_models_call_stops_whatever_his_words(lang, brief, monkeypatch):
    killed, events = _model_calls_stop(ORDERS[lang], brief, monkeypatch)
    assert killed == ["the running errand"], "a word list vetoed the model's stop"
    (_a, kw), = [e for e in events if e[0][1] == "🛑 stop worker"]
    assert kw["extra"]["source"] == "call:stop_worker" and "verdict" in kw["extra"] and "confidence" in kw["extra"]


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("brief", NO_VERDICT, ids=NO_VERDICT_IDS)
def test_with_no_verdict_his_words_alone_stop_nothing(lang, brief, monkeypatch):
    assert _model_called_nothing(NOT_ORDERS[lang], brief, monkeypatch)[0] == [], "his words stopped an errand"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_sure_verdict_still_decides_both_ways(lang, monkeypatch):
    killed, events = _model_called_nothing(ORDERS[lang], _brief(sd.STOP), monkeypatch)
    assert killed == [ORDERS[lang]]
    (_a, kw), = [e for e in events if "stop verdict" in e[0][1]]
    assert (kw["extra"]["verdict"], kw["extra"]["confidence"], kw["extra"]["source"]) == ("stop", 0.95, "verdict")
    killed, events = _model_calls_stop(NOT_ORDERS[lang], _brief(sd.KEEP), monkeypatch)
    assert killed == [], "a sure «keep» refuses the dragged-in stop"
    (_a, kw), = [e for e in events if "vetoed" in e[0][1]]
    assert (kw["extra"]["verdict"], kw["extra"]["source"]) == ("keep", "call:stop_worker")


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_hard_interrupt_reading_stops_nothing_by_itself(lang, monkeypatch):
    """Kept on purpose: it only says «go on to the model»; the errand keeps running until a call or a verdict stops it."""
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: pytest.fail("the hard interrupt cancelled an errand"))
    text = {"es": "para la búsqueda", "en": "stop the worker"}[lang]
    assert hard_turn.is_worker_stop(text, "stop")
    assert asyncio.run(hard_turn.handle(text, "stop", lambda *a, **k: None)) == text


@pytest.mark.parametrize("lang", ["es", "en"])
def test_disarmed_a_word_veto_without_a_verdict_refuses_the_models_stop(lang, monkeypatch):
    real = sd.model_stop
    monkeypatch.setattr(sd, "model_stop", lambda b: "veto" if sd.verdict(b) is None else real(b))
    assert _model_calls_stop(ORDERS[lang], None, monkeypatch)[0] == []


def test_no_stop_decision_reads_a_word_list():
    assert not hasattr(tool_executor_widget, "_says_stop") or "_says_stop" not in inspect.getsource(tool_executor_widget)
    for mod in (_calls, post_stream_settle, sd):
        src = inspect.getsource(mod)
        assert "_says_stop" not in src and "looks_like_stop_work" not in src and "grammar=" not in src, mod.__name__
