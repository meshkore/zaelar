"""A clear order to stop the running errand stops it on the first turn, in any wording (V2-807 T-14).

«Para esa tarea inmediatamente» got «no toco nada» and no stop; «entonces, para inmediatamente esa tarea que está en
marcha» got the model's `stop_worker` VETOED by the context-bleed guard, because the word table that guard read did
not list that word order. Only a bare «Páralo» on the third turn stopped it. The table had been widened once already
(V2-585), and widening it again is the next phrasing's bug.

Now the turn's brief asks, while an errand runs, whether THIS turn orders it stopped (`stop_decision`). A sure
verdict decides both doors — the tool gate (may the model's call run?) and the settle backstop (repair a turn whose
model called nothing). With no sure verdict, the grammar keeps today's path. The guard keeps its real purpose: a
sure «keep» refuses a stop dragged in from an earlier turn, and answering a worker still beats killing it.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from nucleo.request import stop as sd
from nucleo.flash import tool_executor_calls as _calls
from nucleo.turn import brief as _tb

#: Stop orders in several languages and word orders — the grammar below is told it read NONE of them.
STOP_BANK = [
    "Para esa tarea inmediatamente",
    "Entonces, para inmediatamente esa tarea que está en marcha",
    "esa tarea que tienes en marcha, la quiero parada ya",
    "Okay, kill that errand right now please",
    "whatever you are running in the background, I want it gone",
    "arrête tout de suite cette tâche",
    "今動いているタスクを止めて",
    "Hör sofort mit dieser Aufgabe auf",
]


def _brief(choice: str | None, confidence: float = 0.95):
    ev = threading.Event()
    ev.set()
    result = {} if choice is None else {sd.KEY: {"choice": choice, "confidence": confidence}}
    return {"event": ev, "turn_id": "t-1", "open_ids": [], "result": result}


def _gate(text: str, *, brief, grammar: bool, answered: bool = False, monkeypatch) -> list:
    from nucleo import dispatch
    killed: list = []
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: killed.append(w) or ["1"])
    acted = {"v": "answer" if answered else None}
    _calls._t_stop_worker(args={"which": "the running errand"}, _norm_nfkd=lambda s: s.lower(),
                          _say=lambda: SimpleNamespace(stop_which_worker="which?"),
                          _says_stop=lambda t: grammar, clarify={}, emit=lambda *a, **k: None, text=text,
                          worker_acted=acted, brief=brief, prior="")
    return killed


@pytest.mark.parametrize("text", STOP_BANK)
def test_a_sure_stop_verdict_lets_the_models_call_run_whatever_the_wording(text, monkeypatch):
    assert _gate(text, brief=_brief("stop"), grammar=False, monkeypatch=monkeypatch) == ["the running errand"]


@pytest.mark.parametrize("text", STOP_BANK)
def test_a_turn_that_ordered_a_stop_and_called_nothing_is_repaired(text, monkeypatch):
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: ["t9"])
    assert sd.repair(_brief("stop"), text, escalating=False, grammar=lambda: False) == ["t9"]
    # an escalation the model started does not hide the order: «para eso y búscame otra cosa» is both
    assert sd.repair(_brief("stop"), text, escalating=True, grammar=lambda: False) == ["t9"]


def test_context_bleed_still_never_kills(monkeypatch):
    """2026-08-14: a complaint two turns back, dragged forward by the model. A sure «keep» refuses the call even
    where the word table would have let it through."""
    complaint = "los dos navegadores no se tenían que haber abierto"
    assert _gate(complaint, brief=_brief("keep"), grammar=True, monkeypatch=monkeypatch) == []
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: ["t9"])
    assert sd.repair(_brief("keep"), complaint, escalating=False, grammar=lambda: True) == []


def test_answering_a_worker_still_beats_killing_it(monkeypatch):
    """b70a45d0: the turn answered the worker AND called stop. Even with a sure stop verdict, the answer wins."""
    assert _gate("Sí, autorizado, y para", brief=_brief("stop"), grammar=True, answered=True,
                 monkeypatch=monkeypatch) == []


@pytest.mark.parametrize("brief,label", [
    (None, "no brief"),
    ({"event": threading.Event(), "turn_id": "t", "open_ids": [], "result": None}, "in flight"),
    (_brief(None), "not asked (no errand when the brief fired)"),
    (_brief("stop", confidence=0.2), "unsure"),
])
def test_without_a_sure_verdict_the_grammar_keeps_todays_path(brief, label, monkeypatch):
    assert _gate("para todas las tareas", brief=brief, grammar=True, monkeypatch=monkeypatch), label
    assert _gate("no era para ti", brief=brief, grammar=False, monkeypatch=monkeypatch) == [], label
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: ["t9"])
    assert sd.repair(brief, "x", escalating=True, grammar=lambda: True) == [], label   # today: escalation wins
    assert sd.repair(brief, "x", escalating=False, grammar=lambda: True) == ["t9"], label


def test_no_errand_running_stops_nothing(monkeypatch):
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "has_active", lambda: False)
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: pytest.fail("cancelled with nothing running"))
    assert sd.repair(_brief("stop"), "para", escalating=False, grammar=lambda: True) == []


def test_the_question_is_asked_only_while_an_errand_runs(monkeypatch):
    from nucleo import jev
    monkeypatch.setattr(jev, "enabled", lambda: False, raising=False)
    with_worker = _tb.build("para esa tarea", has_workers=True, last_reply="¿La paro?")
    assert sd.KEY in with_worker and "¿La paro?" in with_worker[sd.KEY]["instructions"]
    assert set(with_worker[sd.KEY]["criteria"]) == {"stop", "stop_all", "replace", "steer", "settled", "keep"}   # V2-820; refactor2710-06: stop_all; T-29: settled
    assert sd.KEY not in _tb.build("para esa tarea", has_workers=False)


def _settle(text: str, *, brief, grammar: bool, monkeypatch) -> tuple[list, dict, list]:
    """Drive the voice turn's settle step — the backstop door — on a turn whose model called nothing.

    Returns (what was cancelled, `worker_acted`, what was said)."""
    import asyncio
    from nucleo import dispatch
    from nucleo.flash import post_stream_settle
    killed: list = []
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: killed.append(w) or ["t9"])
    said: list = []
    acted = {"v": None}
    asyncio.run(post_stream_settle.settle_what_is_pending(
        _ans=None, _ask_waiting=False, _auth_pending=False, _brief=brief,
        _dialog=SimpleNamespace(sanitize_reply=lambda s: s), _filler_audio=SimpleNamespace(played_recently=lambda: False),
        _langs=None, _prev_pending=[], _r=None, _resolve_confirm=lambda yes: None,
        _router=SimpleNamespace(looks_like_stop_work=lambda t: grammar, operator_words=lambda o, t: o),
        _shown_ids=set(), acted={"widget": False}, aside={"v": False},
        brain=SimpleNamespace(_window=[], _last_spoken=""), clarify={"msg": ""}, confirm_state={"handled": True},
        data_done={"v": None}, emit=lambda *a, **k: None, escalate_req={"v": None, "more": [], "surface": {}},
        had_pending_confirm=True, llm_metrics={}, music_req={"v": None}, operator_text=text, search_req={"v": None},
        send=said.append, speech=SimpleNamespace(sanitize=lambda s, drop_metadata=False: s), spoken_text="",
        style_fired={"v": False}, text=text, worker_acted=acted))
    return killed, acted, said


@pytest.mark.parametrize("text", [STOP_BANK[3], STOP_BANK[5]])
def test_the_settle_step_stops_the_errand_on_a_sure_verdict_its_grammar_missed(text, monkeypatch):
    """The voice turn's backstop door: the model called nothing, the word table read nothing, the verdict said stop —
    the errand stops and the stop is SAID (never a mute kill)."""
    killed, acted, said = _settle(text, brief=_brief("stop"), grammar=False, monkeypatch=monkeypatch)
    assert killed == [text] and acted["v"] == "stop", "his words name what is cancelled"
    assert said and said[0].strip(), "a kill is always announced"


def test_the_settle_step_refuses_a_stop_the_verdict_keeps(monkeypatch):
    killed, acted, _said = _settle("los dos navegadores no se tenían que haber abierto", brief=_brief("keep"),
                                   grammar=True, monkeypatch=monkeypatch)
    assert killed == [] and acted["v"] is None


def test_the_disarm_a_settle_step_that_skips_the_verdict_misses_the_stop(monkeypatch):
    """Disarm: the settle door asks the grammar alone (the verdict unread) → the same sure stop stops nothing."""
    from nucleo.flash import post_stream_settle
    real = sd.repair
    monkeypatch.setattr(post_stream_settle._stop_decision, "repair",
                        lambda brief, text, **kw: real(None, text, **kw))
    assert post_stream_settle._stop_decision.repair is not real
    killed, acted, _said = _settle(STOP_BANK[3], brief=_brief("stop"), grammar=False, monkeypatch=monkeypatch)
    assert killed == [] and acted["v"] is None


def test_the_disarm_a_tool_gate_that_skips_the_verdict_vetoes_the_stop(monkeypatch):
    """Disarm: the tool gate reads the grammar alone → the model's call over a sure stop is vetoed."""
    real = sd.model_stop
    monkeypatch.setattr(sd, "model_stop", lambda brief, *, grammar: real(None, grammar=grammar))
    assert _gate(STOP_BANK[4], brief=_brief("stop"), grammar=False, monkeypatch=monkeypatch) == []
