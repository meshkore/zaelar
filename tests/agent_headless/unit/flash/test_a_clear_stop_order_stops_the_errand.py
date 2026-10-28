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
from nucleo.flash import turn_brief as _tb

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
    assert set(with_worker[sd.KEY]["criteria"]) == {"stop", "replace", "steer", "keep"}   # V2-820
    assert sd.KEY not in _tb.build("para esa tarea", has_workers=False)


def test_both_doors_read_the_verdict():
    """The wiring: the tool gate and the settle backstop ask `stop_decision`."""
    import inspect
    from nucleo.flash import post_stream_settle
    assert "_stop_decision.model_stop(brief" in inspect.getsource(_calls._t_stop_worker)
    assert "_stop_decision.repair(" in inspect.getsource(post_stream_settle.settle_what_is_pending)
